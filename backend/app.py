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
    # 将rag_contexts和summary写入answers表
    from services.rag_service import save_answers
    answer_update = {"_rag_contexts": rag_contexts, "_summary": "\n\n".join(summary)}
    save_answers(session_id, answer_update, {}, {})
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

@app.post("/module_summary")
async def module_summary(session_id: str = Form(...), key: str = Form(None)):
    """Run module-level RAG summary on demand.
    key can be one of: quantitative_target, energy_measures, waste_measures, or omitted/"all" to run all.
    Returns detected modules, per-module measures, and a one-line summary for each requested key.
    """
    from services.rag_service import search_docs, run_module_level_rag, get_llm, _ai_to_text

    questions = {
        "quantitative_target": f"{session_id}: 政策中是否包含定量目标？输出目标数值与年份，如 减少排放20% by 2030",
        "energy_measures": f"{session_id}: 在减少能源消耗和温室气体排放方面，采取了哪些措施？",
        "waste_measures": f"{session_id}: 在废弃物与化学品管理方面，采取了哪些措施？",
    }

    if key is None or key == "all":
        keys = list(questions.keys())
    else:
        if key not in questions:
            return {"error": "invalid key"}
        keys = [key]

    # Attempt to determine company name from docs
    company_name = "该企业"
    try:
        docs_for_name = search_docs(session_id, "本文档提到的企业或公司名称是什么？", k=1)
        if docs_for_name:
            llm = get_llm()
            name_prompt = f"请从以下内容中提取企业或公司名称，只输出名称，不要解释。\n内容：{docs_for_name[0].page_content}"
            name_result = llm.invoke(name_prompt)
            extracted_name = _ai_to_text(name_result)
            if extracted_name and len(extracted_name) < 50:
                company_name = extracted_name
    except Exception:
        pass

    results = {}
    # Prepare to save to answers
    answer_update = {}
    answer_sources = {}
    answer_conflicts = {}

    for k in keys:
        q = questions[k]
        docs = search_docs(session_id, q, k=5)
        modules, module_details, summary = run_module_level_rag(session_id, k, company_name, docs)
        results[k] = {
            "modules": modules,
            "module_details": module_details,
            "summary": summary,
            "doc_snippets": [d.page_content[:300] for d in docs]
        }

        # Save structured fields into answer_update
        answer_update[f"{k}_modules"] = modules
        answer_update[f"{k}_module_details"] = module_details
        answer_update[f"{k}_module_summary"] = summary

        # Collect sources from docs
        try:
            from services.rag_service import format_source
            sources = sorted({format_source(d.metadata) for d in docs})
        except Exception:
            sources = []
        if sources:
            answer_sources[f"{k}_modules"] = sources

    # Persist to DB
    try:
        from services.rag_service import save_answers
        save_answers(session_id, answer_update, answer_sources, answer_conflicts)
        saved = True
    except Exception as e:
        print(f"Failed to save module summary: {e}")
        saved = False

    return {"session_id": session_id, "company_name": company_name, "results": results, "saved": saved}

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
    from db.db import get_conn
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_input, ai_response FROM chats WHERE session_id=%s ORDER BY created_at", (session_id,))
            rows = cur.fetchall()
    conn.close()
    return [{"user_input": row[0], "ai_response": row[1]} for row in rows]

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

@app.post("/vl_kpi_extract")
async def vl_kpi_extract(session_id: str = Form(...), key: str = Form(...)):
    """对指定KPI字段，针对RAG检索到的相关PDF页做VL图片数值抽取，返回第一个有效数值和ref。"""
    from services.rag_service import search_docs, run_vl_kpi_extraction
    docs = search_docs(session_id, key, k=3)
    vl_extraction = run_vl_kpi_extraction(docs, key)
    for ref, v in vl_extraction.items():
        try:
            vnum = float(str(v).replace("%", "").replace(",", "").strip())
            return {"value": vnum, "ref": ref}
        except Exception:
            continue
    return {"value": None, "ref": None}
