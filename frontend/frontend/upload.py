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
        import os
        backend_url = os.environ.get("BACKEND_URL", "http://fastapi-backend:8000")
        try:
            response = requests.post(f"{backend_url}/upload", data=data, files=files)
            st.session_state["upload_in_progress"] = False
            if response.ok:
                try:
                    result = response.json()
                except Exception as e:
                    st.error(f"后端返回内容解析失败: {e}\n原始内容: {response.text}")
                    return
                st.session_state["upload_success"] = True
                if "questionnaire" in result:
                    st.info(f"自动问卷抽取：{result['questionnaire']}")
                if "review" in result:
                    st.warning(f"审核结果：{result['review']}")
                # 自动刷新问卷和审核
                try:
                    session_id = st.session_state.get("session_id", "default")
                    resp = requests.get(f"{backend_url}/questionnaire?session_id={session_id}")
                    if resp.ok:
                        data = resp.json()
                        if "review" in data:
                            st.warning(f"最新审核结果：{data['review']}")
                        if "answers" in data:
                            st.info(f"最新问卷：{data['answers']}")
                    else:
                        st.error(f"问卷接口请求失败: {resp.status_code} {resp.text}")
                except Exception as e:
                    st.error(f"问卷接口异常: {e}")
                st.rerun()
            else:
                st.error(f"上传失败，请重试。后端返回: {response.status_code} {response.text}")
        except Exception as e:
            st.session_state["upload_in_progress"] = False
            st.error(f"上传请求异常: {e}")
