import streamlit as st

def chat_page():
    st.header("聊天与会话管理")
    session_id = st.session_state.get("session_id", "default")
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    # 聊天输入
    user_input = st.text_input("请输入消息", key="chat_input")
    if st.button("发送", key="send_btn") and user_input:
        import requests
        data = {"message": user_input, "session_id": session_id}
        response = requests.post("http://localhost:8000/chat", data=data)
        if response.ok:
            ai_response = response.json().get("response", "")
            st.session_state["chat_history"].append((user_input, ai_response))
            st.success("消息已发送，问卷已自动更新！")
        else:
            st.error("发送失败，请重试。")

    # 聊天历史展示
    st.subheader("历史消息")
    for user_msg, ai_msg in st.session_state["chat_history"]:
        st.markdown(f"**你：** {user_msg}")
        st.markdown(f"**AI：** {ai_msg}")
