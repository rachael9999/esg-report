from services.update_questionnaire import update_from_chat
import os
from langchain_community.chat_models import ChatTongyi
from pydantic import SecretStr
from dotenv import load_dotenv
import uuid

from langchain_postgres.chat_message_histories import PostgresChatMessageHistory
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.tools import Tool
import psycopg
from fastapi.responses import StreamingResponse
import json

load_dotenv()
api_key = os.environ.get("DASHSCOPE_API_KEY")
if api_key is None or not isinstance(api_key, str) or not api_key.strip():
    raise ValueError("DASHSCOPE_API_KEY is missing. Please set it in the `.env` file.")


def build_agent(session_id):
    # 确保 session_id 是 UUID 字符串
    try:
        session_id = str(uuid.UUID(str(session_id)))
    except Exception:
        session_id = str(uuid.uuid4())

    llm = ChatTongyi(model="qwen-flash", api_key=SecretStr(str(api_key)))
    summarization_llm = ChatTongyi(model="qwen-flash", api_key=SecretStr(str(api_key)))
    # 工具：RAG 检索
    def rag_tool_func(input, session_id=None):
        from langchain_postgres.vectorstores import PGVector
        from langchain_community.embeddings import DashScopeEmbeddings
        import os
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        embeddings = DashScopeEmbeddings(model="text-embedding-v1", dashscope_api_key=api_key)
        vectorstore = PGVector(
            embeddings,
            connection=os.getenv("PGVECTOR_CONN", "postgresql://admin:admin@db:5432/esg_memory"),
            collection_name=f"session_{session_id}",
            use_jsonb=True
        )
        docs = vectorstore.similarity_search(input, k=2)
        if docs:
            return "\n\n".join([d.page_content for d in docs])
        return ""
    rag_tool = Tool(
        name="RAG检索",
        func=lambda input: rag_tool_func(input, session_id),
        description="根据用户问题检索相关文档片段"
    )
    tools = [rag_tool]
    pg_url = os.getenv("PGVECTOR_CONN", "postgresql://admin:admin@db:5432/esg_memory")
    # 创建 sync_connection
    sync_connection = psycopg.connect(pg_url)
    chat_history = PostgresChatMessageHistory(
        "chat_history",
        session_id,
        sync_connection=sync_connection
    )
    agent_executor = create_agent(
        model=llm,
        tools=tools,
        system_prompt="你是ESG问卷智能助手。请结合历史对话、问卷信息和文档片段，专业、简明地回答用户。",
        middleware=[SummarizationMiddleware(model=summarization_llm, trigger=("tokens", 4000), keep=("messages", 20))],
    )
    return agent_executor, chat_history


async def handle_chat(message, session_id):
    from chains.questionnaire_chain import get_questionnaire
    old_answers = get_questionnaire(session_id).get("answers", {}).copy()
    agent_executor, chat_history = build_agent(session_id)
    try:
        # 先用 agent_executor 检索和处理用户输入
        result = agent_executor.invoke({"input": message})
        rag_response = result['messages'][-1].content
    except Exception as e:
        rag_response = f"AI服务异常：{e}"
    chat_history.add_user_message(message)
    chat_history.add_ai_message(rag_response)
    update_from_chat(session_id, message)
    new_answers = get_questionnaire(session_id).get("answers", {}).copy()
    updated_fields = {k: v for k, v in new_answers.items() if old_answers.get(k) != v}
    update_msg = ""
    if updated_fields:
        update_lines = [f"{k}: {v}" for k, v in updated_fields.items()]
        update_msg = "问卷已更新：\n" + "\n".join(update_lines)

    # 拼接更智能的 LLM prompt，包含用户输入、RAG内容
    prompt = (
        "你是ESG问卷助手。请结合用户输入和RAG检索内容，用简洁自然的语言专业地回答用户问题。"
        f"\n用户输入：{message}\n"
        f"RAG检索内容：{rag_response}\n"
        "如有需要，可适当补充和总结，但无需列出字段名或缺失项。"
    )
    llm = ChatTongyi(model="qwen-flash", api_key=SecretStr(str(api_key)))
    ai_result = llm.invoke(prompt)
    if hasattr(ai_result, "content"):
        ai_response_str = ai_result.content.strip()
    else:
        ai_response_str = str(ai_result).strip()

    return {
        "response": ai_response_str,
        "update": update_msg if update_msg else None
    }