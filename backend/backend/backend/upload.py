import streamlit as st

def upload_page():
    st.header("文件上传")
    if st.session_state.get("upload_success", False):
        st.success("上传成功，问卷已自动更新！")
        if st.button("继续上传新文件"):
            st.session_state["upload_success"] = False
            st.rerun()
        return

    uploaded_files = st.file_uploader("选择文件上传", accept_multiple_files=True, key="upload_files")
    if uploaded_files:
        if st.session_state.get("upload_in_progress"):
            return
        st.session_state["upload_in_progress"] = True
        import requests
        files = [
            ("files", (uploaded_file.name, uploaded_file.getvalue()))
            for uploaded_file in uploaded_files
        ]
        session_id = st.session_state.get("session_id", "default")
        data = {"session_id": session_id}
        response = requests.post("http://fastapi-backend:8000/upload", data=data, files=files)
        st.session_state["upload_in_progress"] = False
        if response.ok:
            st.session_state["upload_success"] = True
            st.rerun()
        else:
            st.error(f"上传失败，请重试。后端返回: {response.status_code} {response.text}")
