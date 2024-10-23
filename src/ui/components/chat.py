# src/ui/components/chat.py
import streamlit as st
from typing import Dict, Any
from ...tools.results import ToolResult
from datetime import datetime

def render_chat_message(message: Dict[str, Any]) -> None:
    """Render a chat message with proper formatting"""
    with st.chat_message(message["role"]):
        # Add timestamp
        timestamp = message.get("timestamp", datetime.now())
        st.caption(f"{timestamp.strftime('%I:%M %p')}")
        
        # Render content based on type
        content = message["content"]
        if isinstance(content, ToolResult):
            _render_tool_result(content)
        else:
            st.markdown(content)

def _render_tool_result(result: ToolResult) -> None:
    """Render a tool result with proper formatting"""
    if result.output:
        st.markdown(result.output)
    
    if result.error:
        st.error(result.error)
    
    if result.base64_image:
        st.image(result.base64_image)
        
        # Add download button for screenshot
        st.download_button(
            label="Download Screenshot",
            data=result.base64_image,
            file_name=f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            mime="image/png"
        )
    
    if result.system:
        st.info(result.system)