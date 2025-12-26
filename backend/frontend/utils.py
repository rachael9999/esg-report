# 公共方法和API请求封装

import uuid

def init_chat_sessions():
    import streamlit as st
    # Always try to load from backend
    import requests
    try:
        response = requests.get("http://fastapi-backend:8000/sessions", timeout=5)
        if response.ok:
            sessions = response.json()
            if sessions:
                st.session_state["chat_sessions"] = sessions
                if "session_id" not in st.session_state or st.session_state["session_id"] not in [s["id"] for s in sessions]:
                    st.session_state["session_id"] = sessions[0]["id"]
            else:
                # Create default if none
                session_id = str(uuid.uuid4())
                st.session_state["chat_sessions"] = [
                    {"id": session_id, "name": "默认会话"}
                ]
                st.session_state["session_id"] = session_id
        else:
            # Fallback
            if "chat_sessions" not in st.session_state:
                session_id = str(uuid.uuid4())
                st.session_state["chat_sessions"] = [
                    {"id": session_id, "name": "默认会话"}
                ]
                st.session_state["session_id"] = session_id
    except:
        # Fallback
        if "chat_sessions" not in st.session_state:
            session_id = str(uuid.uuid4())
            st.session_state["chat_sessions"] = [
                {"id": session_id, "name": "默认会话"}
            ]
            st.session_state["session_id"] = session_id
    return st.session_state["session_id"]

def call_api(endpoint, data=None, files=None, method="POST"):
    import requests
    url = f"http://fastapi-backend:8000{endpoint}"
    if method == "POST":
        return requests.post(url, data=data, files=files)
    elif method == "GET":
        return requests.get(url, params=data)
    else:
        raise ValueError("Unsupported method")
