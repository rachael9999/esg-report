import streamlit as st

def chat_page():
    st.header("聊天与会话管理")
    session_id = st.session_state.get("session_id", "default")
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = {}

    # 每次都从后端拉取历史，保证刷新后历史不丢失
    import requests
    import os
    backend_url = os.environ.get("BACKEND_URL", "http://fastapi-backend:8000")
    response = requests.get(f"{backend_url}/chats?session_id={session_id}")
    history = []
    if response.ok:
        chats = response.json()
        for chat in chats:
            history.append((chat["user_input"], chat["ai_response"], []))
    st.session_state["chat_history"][session_id] = history

    # 聊天输入
    user_input = st.text_input("请输入消息", key="chat_input")
    if st.button("发送", key="send_btn") and user_input:
        import requests
        data = {"message": user_input, "session_id": session_id}
        import os
        backend_url = os.environ.get("BACKEND_URL", "http://fastapi-backend:8000")
        try:
            response = requests.post(f"{backend_url}/chat", data=data)
            if response.ok:
                try:
                    data = response.json()
                except Exception as e:
                    st.error(f"后端返回内容解析失败: {e}\n原始内容: {response.text}")
                    return
                ai_response = data.get("response", "")
                sources = data.get("sources", [])
                if "review" in data:
                    st.warning(f"审核结果：{data['review']}")
                if "questionnaire" in data:
                    st.info(f"最新问卷：{data['questionnaire']}")
                # 自动刷新问卷和审核
                try:
                    session_id = st.session_state.get("session_id", "default")
                    resp = requests.get(f"{backend_url}/questionnaire?session_id={session_id}")
                    if resp.ok:
                        data2 = resp.json()
                        if "review" in data2:
                            st.warning(f"最新审核结果：{data2['review']}")
                        if "answers" in data2:
                            st.info(f"最新问卷：{data2['answers']}")
                    else:
                        st.error(f"问卷接口请求失败: {resp.status_code} {resp.text}")
                except Exception as e:
                    st.error(f"问卷接口异常: {e}")
                history.append((user_input, ai_response, sources))
                st.success("消息已发送，问卷已自动更新！")
            else:
                st.error(f"发送失败，请重试。后端返回: {response.status_code} {response.text}")
        except Exception as e:
            st.error(f"聊天请求异常: {e}")

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
