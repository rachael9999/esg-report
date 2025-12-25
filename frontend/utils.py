# 公共方法和API请求封装

import uuid

def get_session_id():
    import streamlit as st
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())
    return st.session_state["session_id"]

def call_api(endpoint, data=None, files=None, method="POST"):
    import requests
    url = f"http://localhost:8000{endpoint}"
    if method == "POST":
        return requests.post(url, data=data, files=files)
    elif method == "GET":
        return requests.get(url, params=data)
    else:
        raise ValueError("Unsupported method")
