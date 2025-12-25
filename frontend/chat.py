import streamlit as st

def chat_page():
    st.header("聊天与会话管理")
    session_id = st.session_state.get("session_id", "default")
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = {}
    history = st.session_state["chat_history"].setdefault(session_id, [])

    # Load history from DB if not loaded
    if not history:
        import requests
        response = requests.get(f"http://localhost:8000/chats?session_id={session_id}")
        if response.ok:
            chats = response.json()
            for chat in chats:
                history.append((chat["user_input"], chat["ai_response"], []))  # Add empty sources for old chats

    # 聊天输入
    user_input = st.text_input("请输入消息", key="chat_input")
    if st.button("发送", key="send_btn") and user_input:
        import requests
        data = {"message": user_input, "session_id": session_id}
        response = requests.post("http://localhost:8000/chat", data=data)
        if response.ok:
            data = response.json()
            ai_response = data.get("response", "")
            sources = data.get("sources", [])
            history.append((user_input, ai_response, sources))
            st.success("消息已发送，问卷已自动更新！")
        else:
            st.error("发送失败，请重试。")

    # 聊天历史展示
    st.subheader("历史消息")
    for item in history:
        if len(item) == 3:
            user_msg, ai_msg, sources = item
        else:
            user_msg, ai_msg = item
            sources = []
        st.markdown(f"**你：** {user_msg}")
        if sources:
            source_text = "; ".join(sources)
            st.markdown(f"**AI：** {ai_msg} <sup title='{source_text}'>[来源]</sup>", unsafe_allow_html=True)
        else:
            st.markdown(f"**AI：** {ai_msg}")
