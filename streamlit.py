"""
Entrypoint for streamlit, see https://docs.streamlit.io/
"""

import asyncio
import base64
import os
from datetime import datetime
from functools import partial
from pathlib import PosixPath
from typing import cast
from enum import Enum


import streamlit as st
from anthropic import APIResponse
from anthropic.types import TextBlock, ToolUseBlock
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock
from streamlit.delta_generator import DeltaGenerator

from loop import DEFAULT_MODEL, sampling_loop
from tools.base import ToolResult

"""
Entrypoint for streamlit, see https://docs.streamlit.io/
"""



# Custom StrEnum implementation for Python < 3.11
class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value

class Sender(StrEnum):
    USER = "user"
    BOT = "assistant"
    TOOL = "tool"

CONFIG_DIR = PosixPath("~/.anthropic").expanduser()
API_KEY_FILE = CONFIG_DIR / "api_key"
STREAMLIT_STYLE = """
<style>
    /* Hide chat input while agent loop is running */
    .stApp[data-teststate=running] .stChatInput textarea,
    .stApp[data-test-script-state=running] .stChatInput textarea {
        display: none;
    }
     /* Hide the streamlit deploy button */
    .stDeployButton {
        visibility: hidden;
    }
</style>
"""

WARNING_TEXT = "⚠️ Security Alert: Never provide access to sensitive accounts or data, as malicious web content can hijack Claude's behavior"

def setup_state():
    """Initialize all session state variables."""
    # Initialize default values if they don't exist
    defaults = {
        "messages": [],
        "api_key": load_from_storage("api_key") or os.getenv("ANTHROPIC_API_KEY", ""),
        "model": DEFAULT_MODEL,
        "auth_validated": False,
        "responses": {},
        "tools": {},
        "only_n_most_recent_images": 10,
        "custom_system_prompt": load_from_storage("system_prompt") or "",
        "hide_images": False,
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

def validate_auth(api_key: str | None):
    """Validate that the Anthropic API key is present."""
    if not api_key:
        return "Enter your Anthropic API key in the sidebar to continue."
    return None

def load_from_storage(filename: str) -> str | None:
    """Load data from a file in the storage directory."""
    try:
        file_path = CONFIG_DIR / filename
        if file_path.exists():
            data = file_path.read_text().strip()
            if data:
                return data
    except Exception as e:
        st.write(f"Debug: Error loading {filename}: {e}")
    return None

def save_to_storage(filename: str, data: str) -> None:
    """Save data to a file in the storage directory."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        file_path = CONFIG_DIR / filename
        file_path.write_text(data)
        # Ensure only user can read/write the file
        file_path.chmod(0o600)
    except Exception as e:
        st.write(f"Debug: Error saving {filename}: {e}")

def _render_api_response(
    response: APIResponse[BetaMessage],
    response_id: str,
    tab: DeltaGenerator
):
    """Render an API response to a streamlit tab"""
    with tab:
        with st.expander(f"Request/Response ({response_id})"):
            newline = "\n\n"
            st.markdown(
                f"`{response.http_request.method} {response.http_request.url}`{newline}{newline.join(f'`{k}: {v}`' for k, v in response.http_request.headers.items())}"
            )
            st.json(response.http_request.read().decode())
            st.markdown(
                f"`{response.http_response.status_code}`{newline}{newline.join(f'`{k}: {v}`' for k, v in response.headers.items())}"
            )
            st.json(response.http_response.text)

def _render_message(
    sender: Sender,
    message: str | BetaTextBlock | BetaToolUseBlock | ToolResult,
):
    """Convert input from the user or output from the agent to a streamlit message."""
    # streamlit's hotreloading breaks isinstance checks, so we need to check for class names
    is_tool_result = not isinstance(message, str) and (
        isinstance(message, ToolResult)
        or message.__class__.__name__ == "ToolResult"
        or message.__class__.__name__ == "CLIResult"
    )
    if not message or (
        is_tool_result
        and st.session_state.hide_images
        and not hasattr(message, "error")
        and not hasattr(message, "output")
    ):
        return
    with st.chat_message(sender):
        if is_tool_result:
            message = cast(ToolResult, message)
            if message.output:
                if message.__class__.__name__ == "CLIResult":
                    st.code(message.output)
                else:
                    st.markdown(message.output)
            if message.error:
                st.error(message.error)
            if message.base64_image and not st.session_state.hide_images:
                st.image(base64.b64decode(message.base64_image))
        elif isinstance(message, BetaTextBlock) or isinstance(message, TextBlock):
            st.write(message.text)
        elif isinstance(message, BetaToolUseBlock) or isinstance(message, ToolUseBlock):
            st.code(f"Tool Use: {message.name}\nInput: {message.input}")
        else:
            st.markdown(message)

def _tool_output_callback(
    tool_output: ToolResult, tool_id: str, tool_state: dict[str, ToolResult]
):
    """Handle a tool output by storing it to state and rendering it."""
    tool_state[tool_id] = tool_output
    _render_message(Sender.TOOL, tool_output)

def _api_response_callback(
    response: APIResponse[BetaMessage],
    tab: DeltaGenerator,
    response_state: dict[str, APIResponse[BetaMessage]],
):
    """Handle an API response by storing it to state and rendering it."""
    response_id = datetime.now().isoformat()
    response_state[response_id] = response
    _render_api_response(response, response_id, tab)

async def main():
    """Render loop for streamlit"""
    setup_state()

    st.markdown(STREAMLIT_STYLE, unsafe_allow_html=True)

    st.title("Claude Computer Use Demo")

    if not os.getenv("HIDE_WARNING", False):
        st.warning(WARNING_TEXT)

    with st.sidebar:
        st.text_input("Model", key="model")
        st.text_input(
            "Anthropic API Key",
            type="password",
            key="api_key",
            on_change=lambda: save_to_storage("api_key", st.session_state.api_key),
        )

        st.number_input(
            "Only send N most recent images",
            min_value=0,
            key="only_n_most_recent_images",
            help="To decrease the total tokens sent, remove older screenshots from the conversation",
        )
        st.text_area(
            "Custom System Prompt Suffix",
            key="custom_system_prompt",
            help="Additional instructions to append to the system prompt. see computer_use_demo/loop.py for the base system prompt.",
            on_change=lambda: save_to_storage(
                "system_prompt", st.session_state.custom_system_prompt
            ),
        )
        st.checkbox("Hide screenshots", key="hide_images")

        if st.button("Reset", type="primary"):
            st.session_state.clear()
            setup_state()

    if not st.session_state.auth_validated:
        if auth_error := validate_auth(st.session_state.api_key):
            st.warning(f"Please resolve the following auth issue:\n\n{auth_error}")
            return
        else:
            st.session_state.auth_validated = True

    chat, http_logs = st.tabs(["Chat", "HTTP Exchange Logs"])
    new_message = st.chat_input(
        "Type a message to send to Claude to control the computer..."
    )

    with chat:
        # render past chats
        for message in st.session_state.messages:
            if isinstance(message["content"], str):
                _render_message(message["role"], message["content"])
            elif isinstance(message["content"], list):
                for block in message["content"]:
                    # the tool result we send back to the Anthropic API isn't sufficient to render all details,
                    # so we store the tool use responses
                    if isinstance(block, dict) and block["type"] == "tool_result":
                        _render_message(
                            Sender.TOOL, st.session_state.tools[block["tool_use_id"]]
                        )
                    else:
                        _render_message(
                            message["role"],
                            cast(BetaTextBlock | BetaToolUseBlock, block),
                        )

        # Handle new message
        if new_message:
            # Add user message to state
            st.session_state.messages.append(
                {
                    "role": "user",
                    "content": [{"type": "text", "text": new_message}],
                }
            )
            _render_message(Sender.USER, new_message)

            # Get Claude's response
            with st.spinner("Running Agent..."):
                st.session_state.messages = await sampling_loop(
                    system_prompt_suffix=st.session_state.custom_system_prompt,
                    model=st.session_state.model,
                    messages=st.session_state.messages,
                    output_callback=partial(_render_message, Sender.BOT),
                    tool_output_callback=partial(
                        _tool_output_callback, tool_state=st.session_state.tools
                    ),
                    api_response_callback=partial(
                        _api_response_callback,
                        tab=http_logs,
                        response_state=st.session_state.responses,
                    ),
                    api_key=st.session_state.api_key,
                    only_n_most_recent_images=st.session_state.only_n_most_recent_images,
                )

if __name__ == "__main__":
    asyncio.run(main())