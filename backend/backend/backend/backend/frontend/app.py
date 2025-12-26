import streamlit as st
import uuid
from questionnaire import questionnaire_page
from upload import upload_page
from chat import chat_page
from utils import init_chat_sessions

st.set_page_config(page_title="ESG AI 问卷系统", layout="wide")

# 初始化会话
init_chat_sessions()

def get_current_session_index(sessions, session_id):
    for idx, session in enumerate(sessions):
        if session["id"] == session_id:
            return idx
    return 0

# 侧边栏问卷
with st.sidebar:
    st.header("会话管理")
    sessions = st.session_state.get("chat_sessions", [])
    session_names = [session["name"] for session in sessions]
    current_session_id = st.session_state.get("session_id")
    current_index = get_current_session_index(sessions, current_session_id)
    selected_name = st.selectbox("选择会话", session_names, index=current_index)
    selected_session = next((s for s in sessions if s["name"] == selected_name), None)
    if selected_session and selected_session["id"] != current_session_id:
        st.session_state["session_id"] = selected_session["id"]
        st.rerun()

    with st.expander("新建会话"):
        new_name = st.text_input("会话名称", key="new_session_name")
        if st.button("创建会话", key="create_session_btn"):
            if new_name:
                import requests
                response = requests.post("http://fastapi-backend:8000/create_session", data={"name": new_name})
                if response.ok:
                    data = response.json()
                    new_session_id = data["session_id"]
                    st.session_state["chat_sessions"].append({"id": new_session_id, "name": new_name})
                    st.session_state["session_id"] = new_session_id
                    st.rerun()
                else:
                    st.error("创建会话失败")
            else:
                st.warning("请输入会话名称。")

    st.header("ESG 问卷填写")
    questionnaire_page()

# 主区tab：文件上传、聊天
tab1, tab2 = st.tabs(["文件上传", "聊天/会话"])

with tab1:
    upload_page()
with tab2:
    chat_page()
