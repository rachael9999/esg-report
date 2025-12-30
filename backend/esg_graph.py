"""
LangGraph 节点与主流程定义
"""
from langgraph.graph import StateGraph, END
from langgraph.graph import node
from fastapi.responses import StreamingResponse
from fastapi import FastAPI, UploadFile, File, Form, Request
import uuid
from db.db import get_conn
from chains.chat_chain import stream_chat as _stream_chat
from typing import TypedDict, List, Dict, Any
import os, tempfile

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
    # 简单示例：如问卷有 scope1/2/3 且都为 None，则标记为需人工审核
    q = state.get('questionnaire', {}).get('answers', {})
    if all(q.get(k) in (None, '', 0) for k in ['scope1', 'scope2', 'scope3']):
        state['review'] = '需要人工审核：碳排放数据缺失'
    else:
        state['review'] = '自动审核通过'
    return state

@node
def db_node(state):
    # 占位数据库节点，实际应实现读写数据库逻辑
    return state
# 构建主流程

class ESGState(TypedDict, total=False):
    session_id: str
    files: List[str]
    message: str
    upload_done: bool
    questionnaire: Dict[str, Any]
    chat_response: str
    review: str

def build_esg_graph():
    # 提供 state_schema，声明流程中会使用的状态字段，避免缺少参数错误
    graph = StateGraph(state_schema=ESGState)
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
    return graph

app = FastAPI()
esg_graph = build_esg_graph()

@app.post("/upload")
async def upload(files: list[UploadFile] = File(...), session_id: str = Form(...)):
    # 保存上传文件到临时路径
    
    file_paths = []
    for uploaded_file in files:
        filename = uploaded_file.filename or "unknown"
        safe_name = os.path.basename(filename)
        unique_name = f"{session_id}_{uuid.uuid4().hex}_{safe_name}"
        tmp_path = os.path.join(tempfile.gettempdir(), unique_name)
        contents = await uploaded_file.read()
        with open(tmp_path, "wb") as f:
            f.write(contents)
        file_paths.append(tmp_path)
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
    
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM sessions ORDER BY created_at DESC")
            rows = cur.fetchall()
    conn.close()
    return [{"id": row[0], "name": row[1]} for row in rows]

def stream_chat(message, session_id):
    
    for chunk in _stream_chat(message, session_id):
        yield chunk

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
