from fastapi import Request, FastAPI, UploadFile, Form, File
import psycopg2
import uuid
def ensure_questionnaire_exists():
    from db.db import get_conn
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM questionnaires WHERE id=1")
            if not cur.fetchone():
                cur.execute("INSERT INTO questionnaires (id, title, questions) VALUES (1, '默认问卷', '{}')")
    conn.close()


app = FastAPI()

# 在 FastAPI 启动时确保问卷存在
@app.on_event("startup")
def startup_event():
    ensure_questionnaire_exists()

@app.post("/upload")
async def upload(files: list[UploadFile] = File(...), session_id: str = Form(...)):
    file_paths = []
    import os
    for uploaded_file in files:
        filename = uploaded_file.filename if uploaded_file.filename is not None else "unknown"
        safe_name = os.path.basename(filename)
        unique_name = f"{session_id}_{uuid.uuid4().hex}_{safe_name}"
        file_path = f"/tmp/{unique_name}"
        with open(file_path, "wb") as f:
            f.write(await uploaded_file.read())
        file_paths.append(file_path)
    # RAG自动问卷更新
    from services.update_questionnaire import update_from_document
    update_from_document(session_id, file_paths)
    # 修改：收集RAG检索内容和summary
    rag_contexts = {}
    summary = []
    from langchain_community.embeddings import DashScopeEmbeddings
    from langchain_postgres.vectorstores import PGVector
    import os
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    kpi_questions = {
        "scope1": "企业的Scope 1（直接排放）是多少？",
        "scope2": "企业的Scope 2（能源间接排放）是多少？",
        "scope3": "企业的Scope 3（上下游其他间接排放）是多少？",
        "energy_total": "企业的总能耗是多少？",
        "renewable_ratio": "企业的可再生能源占比是多少？",
        "hazardous_waste": "企业的危险废弃物总量是多少？",
        "nonhazardous_waste": "企业的非危险废弃物总量是多少？",
        "recycled_waste": "企业的回收/再利用废弃物总量是多少？"
    }
    embeddings = DashScopeEmbeddings(model="text-embedding-v1", dashscope_api_key=api_key)
    vectorstore = PGVector(
        embeddings,
        connection=os.getenv("PGVECTOR_CONN", "postgresql://admin:admin@db:5432/esg_memory"),
        collection_name=f"session_{session_id}",
        use_jsonb=True
    )
    for key, question in kpi_questions.items():
        docs = vectorstore.similarity_search(question, k=1)
        if docs:
            rag_contexts[key] = docs[0].page_content
            summary.append(f"[{key}] {question}\n→ {docs[0].page_content[:200]}...")
        else:
            rag_contexts[key] = "未检索到相关内容"
            summary.append(f"[{key}] {question}\n→ 未检索到相关内容")
    for file_path in file_paths:
        os.remove(file_path)
    from chains.questionnaire_chain import get_questionnaire
    result = get_questionnaire(session_id)
    result["rag_contexts"] = rag_contexts
    result["summary"] = "\n\n".join(summary)
    return result

@app.post("/chat")
async def chat(message: str = Form(...), session_id: str = Form(...)):
    from chains.chat_chain import handle_chat
    response = await handle_chat(message, session_id)
    return response

@app.get("/questionnaire")
async def get_questionnaire_api(request: Request):
    session_id = request.query_params.get("session_id")
    if not session_id:
        return {"error": "session_id required"}
    from chains.questionnaire_chain import get_questionnaire
    return get_questionnaire(session_id)

@app.post("/create_session")
async def create_session(name: str = Form(...)):
    import uuid
    from db.db import get_conn
    session_id = str(uuid.uuid4())
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (id, session_token, name) VALUES (%s, %s, %s)",
                (session_id, session_id, name)
            )
    conn.close()
    return {"session_id": session_id}

@app.post("/update_answers")
async def update_answers(session_id: str = Form(...), answers: str = Form(...)):
    from db.db import get_conn
    import json
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, answers FROM answers WHERE session_id=%s ORDER BY created_at DESC LIMIT 1", (session_id,))
            row = cur.fetchone()
            if row:
                answer_id, existing = row
                if existing and isinstance(existing, str):
                    existing = json.loads(existing)
                source_data = {}
                conflict_data = {}
                if isinstance(existing, dict):
                    source_data = existing.get("_sources", {})
                    conflict_data = existing.get("_conflicts", {})
                updated = json.loads(answers)
                if isinstance(updated, dict):
                    updated["_sources"] = source_data
                    updated["_conflicts"] = conflict_data
                cur.execute("UPDATE answers SET answers=%s WHERE id=%s", (json.dumps(updated), answer_id))
            else:
                cur.execute("INSERT INTO answers (session_id, questionnaire_id, answers) VALUES (%s, %s, %s)", (session_id, 1, answers))
    conn.close()
    return {"status": "updated"}

@app.get("/chats")
async def get_chats(request: Request):
    session_id = request.query_params.get("session_id")
    if not session_id:
        return {"error": "session_id required"}
    import json
    from db.db import get_conn
    def parse_message(raw_message):
        message = raw_message
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                return {"type": "unknown", "content": message}
        if not isinstance(message, dict):
            return {"type": "unknown", "content": str(message)}
        data = message.get("data", {})
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {"content": data}
        content = None
        if isinstance(data, dict):
            content = data.get("content")
        if content is None:
            content = message.get("content")
        return {"type": message.get("type") or message.get("role"), "content": content}

    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT message FROM chat_history WHERE session_id=%s ORDER BY created_at", (session_id,))
            rows = cur.fetchall()
    conn.close()
    history = []
    pending_user = None
    for (message,) in rows:
        parsed = parse_message(message)
        msg_type = parsed.get("type")
        content = parsed.get("content") or ""
        if msg_type in ("human", "user"):
            pending_user = content
        elif msg_type in ("ai", "assistant"):
            if pending_user is None:
                pending_user = ""
            history.append({"user_input": pending_user, "ai_response": content})
            pending_user = None
    return history

@app.get("/sessions")
async def get_sessions():
    from db.db import get_conn
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM sessions ORDER BY created_at DESC")
            rows = cur.fetchall()
    conn.close()
    return [{"id": row[0], "name": row[1]} for row in rows]
