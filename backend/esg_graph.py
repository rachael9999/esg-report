"""
LangGraph 节点与主流程定义
"""
from langgraph.graph import StateGraph, END
from langgraph.graph import node
from fastapi.responses import StreamingResponse

# 上传节点
@node
def upload_agent(state):
    """
    state: dict, 需包含 'files', 'session_id'
    """
    from services.update_questionnaire import update_from_document
    session_id = state.get('session_id')
    files = state.get('files')
    update_from_document(session_id, files)
    state['upload_done'] = True
    return state

# 问卷节点
@node
def questionnaire_agent(state):
    """
    state: dict, 需包含 'session_id'
    """
    from chains.questionnaire_chain import get_questionnaire
    session_id = state.get('session_id')
    result = get_questionnaire(session_id)
    state['questionnaire'] = result
    return state

# 聊天节点
@node
def chat_agent(state):
    """
    state: dict, 需包含 'message', 'session_id'
    """
    from chains.chat_chain import stream_chat
    message = state.get('message')
    session_id = state.get('session_id')
    for chunk in stream_chat(message, session_id):
        state['chat_response'] = chunk
        yield state  

# 数据库节点
@node
def review_agent(state):
    return state
    # 简单示例：如问卷有 scope1/2/3 且都为 None，则标记为需人工审核
    q = state.get('questionnaire', {}).get('answers', {})
    if all(q.get(k) in (None, '', 0) for k in ['scope1', 'scope2', 'scope3']):
        state['review'] = '需要人工审核：碳排放数据缺失'
    else:
        state['review'] = '自动审核通过'
    return state

# 构建主流程
def build_esg_graph():
    graph.add_node('upload', upload_agent)
    graph.add_node('questionnaire', questionnaire_agent)
    graph.add_node('chat', chat_agent)
    graph.add_node('review', review_agent)
    graph.add_node("db", db_node)
    # 上传后并行进入问卷抽取和聊天（如有 message）
    def upload_to_next(state):
        # 并行：如有 message，走问卷+聊天；否则只走问卷
        if state.get('message'):
            return ['questionnaire', 'chat']
        else:
            return ['questionnaire']
    graph.add_edge('upload', upload_to_next)
    # 问卷抽取后进入审核
    graph.add_edge('questionnaire', 'review')
    # 聊天结束直接结束
    graph.add_edge('chat', END)
    # 审核后结束
    graph.add_edge('review', END)
    graph.add_edge("questionnaire", "chat")
    graph.add_edge("chat", END)
    graph.add_edge("db", END)
    graph.set_entry_point("upload")
    return graph

app = FastAPI()
esg_graph = build_esg_graph()

@app.post("/upload")
async def upload(files: list[UploadFile] = File(...), session_id: str = Form(...)):
    # 保存上传文件到临时路径
    import os, tempfile
    file_paths = []
    for uploaded_file in files:
        filename = uploaded_file.filename or "unknown"
        safe_name = os.path.basename(filename)
        unique_name = f"{session_id}_{uuid.uuid4().hex}_{safe_name}"
        tmp_path = os.path.join(tempfile.gettempdir(), unique_name)
        with open(tmp_path, "wb") as f:
    state = {"session_id": session_id, "files": file_paths}
    result = esg_graph.run(state)
    # 清理临时文件
    for p in file_paths:
        try:
            os.remove(p)
        except Exception:
            pass
    return {"upload_done": result.get("upload_done", False)}

@app.get("/questionnaire")
async def get_questionnaire_api(request: Request):
    session_id = request.query_params.get("session_id")
    state = {"session_id": session_id}
    result = esg_graph.run(state)
    return result.get("questionnaire", {})

@app.post("/chat")
async def chat(message: str = Form(...), session_id: str = Form(...)):
    state = {"session_id": session_id, "message": message}
    result = esg_graph.run(state)
    return result.get("chat_response", {})

@app.post("/chat_stream")
async def chat_stream(message: str = Form(...), session_id: str = Form(...)):
    state = {"session_id": session_id, "message": message}
    def event_stream():
        # 只 yield chat_response，避免重复内容
        last = ""
        for s in esg_graph.run(state):
            chunk = s.get('chat_response', '')
            # 只推送新内容
            if chunk and chunk != last:
                yield chunk[len(last):]
                last = chunk
    return StreamingResponse(event_stream(), media_type="text/plain")


# 迁移原 app.py 其余 API 路由
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

def stream_chat(message, session_id):
    agent_executor, chat_history = build_agent(session_id)
    ai_response = ""
    for chunk in agent_executor.stream({"input": message}):
        content = getattr(chunk, "content", str(chunk))
        ai_response += content
        yield content
    # 保存历史
    from db.db import get_conn
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chats (session_id, user_input, ai_response) VALUES (%s, %s, %s)",
                (session_id, message, ai_response)
            )
    conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
