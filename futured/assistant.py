"""
Страница AI ассистента
"""
import streamlit as st
from app.core.ai_utils import get_ai_assistant
from app.core.state_manager import StateManager
from app.core.ui_components import render_chat_interface


def render_assistant_page():
    st.header("🤖 AI Ассистент")
    st.markdown("💬 Задайте вопрос ассистенту...")

    messages = StateManager.get_messages()
    is_ai_thinking = StateManager.is_ai_thinking()

    def handle_message_sent(prompt: str):
        # Добавляем сообщение от пользователя
        StateManager.add_message("user", prompt)
        StateManager.set_ai_thinking(True)
        st.rerun()  # Перерисуем с индикатором ожидания

    def handle_clear_chat():
        StateManager.clear_messages()
        StateManager.set_ai_thinking(False)
        st.rerun()

    # Рендер чата (покажет индикатор ожидания)
    render_chat_interface(messages, is_ai_thinking, handle_message_sent, handle_clear_chat)

    # Если AI "думает", запускаем обработку
    if is_ai_thinking:
        try:
            last_user_msg = messages[-1]["content"]
            response = get_ai_assistant().generate_assistant_response(last_user_msg)
            StateManager.add_message("assistant", response)
        except Exception as e:
            response = "❌ Ошибка AI: Проверьте, что Ollama запущен."
            StateManager.add_message("assistant", response)

        StateManager.set_ai_thinking(False)
        st.rerun()  # Обновим интерфейс с новым ответом
