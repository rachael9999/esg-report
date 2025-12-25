import streamlit as st
from questionnaire import questionnaire_page
from upload import upload_page
from chat import chat_page
from utils import get_session_id

st.set_page_config(page_title="ESG AI 问卷系统", layout="wide")

# 初始化 session_id
get_session_id()

# 侧边栏问卷
with st.sidebar:
    st.header("ESG 问卷填写")
    questionnaire_page()

# 主区tab：文件上传、聊天
tab1, tab2 = st.tabs(["文件上传", "聊天/会话"])

with tab1:
    upload_page()
with tab2:
    chat_page()
