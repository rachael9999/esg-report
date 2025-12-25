import streamlit as st

def upload_page():
    st.header("文件上传")
    uploaded_file = st.file_uploader("选择文件上传")
    if uploaded_file:
        import requests
        files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
        # session_id 可从 st.session_state 获取或生成
        session_id = st.session_state.get("session_id", "default")
        data = {"session_id": session_id}
        response = requests.post("http://localhost:8000/upload", data=data, files=files)
        if response.ok:
            st.success("上传成功，问卷已自动更新！")
        else:
            st.error(f"上传失败，请重试。后端返回: {response.status_code} {response.text}")
