from services.update_questionnaire import update_from_chat
from db.db import get_conn
import os
from langchain_community.chat_models import ChatTongyi
from pydantic import SecretStr
from dotenv import load_dotenv

load_dotenv()
# Ensure the DASHSCOPE_API_KEY is loaded
api_key = os.environ.get("DASHSCOPE_API_KEY")
if not api_key:
    raise ValueError("DASHSCOPE_API_KEY is missing. Please set it in the `.env` file.")

llm = ChatTongyi(model="qwen-flash", api_key=SecretStr(api_key))

def get_ai_response(message, session_id):
    # 调用 ChatTongyi 获取 AI 回复
    try:
        response = llm.invoke(message)
        return response
    except Exception as e:
        return f"AI服务异常：{e}"

async def handle_chat(message, session_id):
    # 1. 检索问卷answers
    from chains.questionnaire_chain import get_questionnaire
    answers = get_questionnaire(session_id).get("answers", {})

    # 1.5 获取最近5条历史聊天内容，拼接为多轮上下文
    chat_history = []
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_input, ai_response FROM chats WHERE session_id=%s ORDER BY id DESC LIMIT 5",
                (session_id,)
            )
            rows = cur.fetchall()
            # 倒序排列，最早的在前
            for row in reversed(rows):
                chat_history.append({"user": row[0], "ai": row[1]})
    conn.close()

    # 2. RAG文档检索
    from langchain_postgres.vectorstores import PGVector
    from langchain_community.embeddings import DashScopeEmbeddings
    import os
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    rag_result = ""
    sources = []
    try:
        embeddings = DashScopeEmbeddings(model="text-embedding-v1", dashscope_api_key=api_key)
        vectorstore = PGVector(
            connection_string=os.getenv("PGVECTOR_CONN", "postgresql+psycopg2://admin:admin@db:5432/postgres"),
            embedding_function=embeddings,
            collection_name=f"session_{session_id}",
            use_jsonb_metadata=True
        )
        docs = vectorstore.similarity_search(message, k=2)
        sources = []
        if docs:
            rag_result = "\n\n".join([d.page_content for d in docs])
            for d in docs:
                source = d.metadata.get('source', 'Unknown')
                if '/' in source or '\\' in source:
                    source = source.split('/')[-1].split('\\')[-1]
                page = d.metadata.get('page', 'N/A')
                sources.append(f"{source}: 页 {page}")
        else:
            rag_result = ""
    except Exception:
        pass


    # 3. 组织AI prompt，融合历史对话、问卷和RAG，并在最前面加“本轮目标”
    history_str = ""
    if chat_history:
        for idx, turn in enumerate(chat_history):
            history_str += f"\n[用户]{turn['user']}\n[AI]{turn['ai']}\n"
    # 概括本轮目标
    goal_str = f"本轮目标：请聚焦于用户最新问题“{message}”，确保回答紧扣本轮需求，不被历史上下文干扰。"
    prompt = (
        goal_str +
        "\n你是ESG问卷智能助手。请结合历史对话、问卷信息和文档片段，专业、简明地回答用户。"
        f"\n\n【历史对话】:{history_str}\n\n用户问题：{message}\n\n【问卷已知信息】：{answers}\n\n【相关文档片段】：{rag_result}"
    )
    ai_response = get_ai_response(prompt, session_id)
    if hasattr(ai_response, "content"):
        ai_response_str = ai_response.content
    else:
        ai_response_str = str(ai_response)

    # 聊天记录存储到 Postgres
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (id, session_token) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                (session_id, session_id)
            )
            cur.execute(
                "INSERT INTO chats (session_id, user_input, ai_response) VALUES (%s, %s, %s)",
                (session_id, message, ai_response_str)
            )
    conn.close()

    # 自动更新问卷
    update_from_chat(session_id, message)
    return {"response": ai_response_str, "sources": sources}
