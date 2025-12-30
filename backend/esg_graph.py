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
