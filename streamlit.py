
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
import time

import streamlit as st
from anthropic import APIResponse
from anthropic.types import TextBlock, ToolUseBlock
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock
from streamlit.delta_generator import DeltaGenerator

from loop import DEFAULT_MODEL, sampling_loop
from tools.base import ToolResult
from tasks import PREDEFINED_TASKS, Task, verify_task_completion

# # Initialize hide_images checkbox
# st.checkbox("Hide screenshots", key="hide_images")

def derive_task_description(user_input: str) -> str:
    return user_input.strip().lower()

def get_sensitive_input(prompt: str) -> str:
    return st.text_input(prompt, type='password')

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
    .stApp[data-teststate=running] .stChatInput textarea,
    .stApp[data-test-script-state=running] .stChatInput textarea {
        display: none;
    }
    .stDeployButton {
        visibility: hidden;
    }
</style>
"""

WARNING_TEXT = "We Can Do It! is a tool that helps you collect tax documents"

def setup_state():
    """Initialize all session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "api_key" not in st.session_state:
        st.session_state.api_key = load_from_storage("api_key") or os.getenv("ANTHROPIC_API_KEY", "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")
    if "model" not in st.session_state:
        st.session_state.model = DEFAULT_MODEL
    if "auth_validated" not in st.session_state:
        st.session_state.auth_validated = False
    if "responses" not in st.session_state:
        st.session_state.responses = {}
    if "tools" not in st.session_state:
        st.session_state.tools = {}
    if "only_n_most_recent_images" not in st.session_state:
        st.session_state.only_n_most_recent_images = 10
    if "custom_system_prompt" not in st.session_state:
        st.session_state.custom_system_prompt = load_from_storage("system_prompt") or ""
    if "hide_images" not in st.session_state:
        st.session_state.hide_images = True
    if "current_task_index" not in st.session_state:
        st.session_state.current_task_index = -1
    if "workflow_running" not in st.session_state:
        st.session_state.workflow_running = False
    if "task_results" not in st.session_state:
        st.session_state.task_results = []

def load_from_storage(filename: str) -> str | None:
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
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        file_path = CONFIG_DIR / filename
        file_path.write_text(data)
        file_path.chmod(0o600)
    except Exception as e:
        st.write(f"Debug: Error saving {filename}: {e}")

def validate_auth(api_key: str | None):
    if not api_key:
        return "Enter your Anthropic API key in the sidebar to continue."
    return None

def _render_message(sender: Sender, message: str | BetaTextBlock | BetaToolUseBlock | ToolResult):
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
        elif isinstance(message, (BetaTextBlock, TextBlock)):
            st.write(message.text)
        elif isinstance(message, (BetaToolUseBlock, ToolUseBlock)):
            st.code(f"Tool Use: {message.name}\nInput: {message.input}")
        else:
            st.markdown(message)

def _tool_output_callback(tool_output: ToolResult, tool_id: str, tool_state: dict[str, ToolResult]):
    tool_state[tool_id] = tool_output
    _render_message(Sender.TOOL, tool_output)

def _api_response_callback(
    response: APIResponse[BetaMessage],
    tab: DeltaGenerator,
    response_state: dict[str, APIResponse[BetaMessage]],
):
    response_id = datetime.now().isoformat()
    response_state[response_id] = response
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

def start_automated_workflow():
    st.session_state.workflow_running = True
    st.session_state.current_task_index = 0
    st.session_state.task_results = []
    st.session_state.messages = []


async def process_next_task(http_logs_tab):
    """Process the next task in the workflow."""
    # Check if all tasks are completed
    if st.session_state.current_task_index >= len(PREDEFINED_TASKS):
        st.session_state.workflow_running = False
        st.success("All tasks completed!")
        return

    # Get current task and initialize
    current_task = PREDEFINED_TASKS[st.session_state.current_task_index]
    if not hasattr(current_task, 'start_time') or not current_task.start_time:
        current_task.start_time = time.time()

    # Initialize state variables if they don't exist
    if 'awaiting_user_confirmation' not in st.session_state:
        st.session_state.awaiting_user_confirmation = False
    if 'user_confirmation_message' not in st.session_state:
        st.session_state.user_confirmation_message = ""

    # Handle E*TRADE verification code flow
    if (current_task.description.lower().find("etrade") != -1 and 
        not getattr(current_task, 'verification_requested', False)):
        
        # Start E*TRADE task to request verification code
        messages = [{"role": "user", "content": current_task.description}]
        try:
            result_messages = await sampling_loop(
                messages=messages,
                system_prompt_suffix="",
                output_callback=partial(_render_message, Sender.BOT),
                tool_output_callback=partial(_tool_output_callback, tool_state=st.session_state.tools),
                api_response_callback=partial(
                    _api_response_callback, 
                    tab=http_logs_tab,
                    response_state=st.session_state.responses
                ),
                api_key=st.session_state.api_key,
                task_description=current_task.description
            )
            
            st.session_state.messages.extend(result_messages)
            
            # Check if verification code was requested
            last_messages = " ".join(str(msg.get("content", "")) for msg in result_messages[-3:]).lower()
            if any(phrase in last_messages for phrase in ["verification code", "send code", "security code"]):
                current_task.verification_requested = True
                st.info("Please wait for the verification code to be sent, then enter it below.")
                
                # Create verification code input interface
                col1, col2 = st.columns([3, 1])
                with col1:
                    verification_code = st.text_input(
                        "Enter verification code:",
                        key="verification_code_input",
                        help="Enter the 6-digit code that was just sent to you",
                        max_chars=6
                    )
                with col2:
                    if st.button("Submit Code", key="submit_verification_code"):
                        if verification_code and len(verification_code) == 6 and verification_code.isdigit():
                            st.session_state.verification_code = verification_code
                            st.rerun()
                        else:
                            st.error("Please enter a valid 6-digit code")
                return
            
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            st.session_state.workflow_running = False
            return

    # Handle required credentials
    for cred in current_task.required_credentials:
        if cred not in st.session_state:
            if cred == "verification_code" and not getattr(current_task, 'verification_requested', False):
                continue
            if cred == "verification_code" and getattr(current_task, 'verification_requested', False):
                # Create verification code input interface
                col1, col2 = st.columns([3, 1])
                with col1:
                    verification_code = st.text_input(
                        "Enter verification code:",
                        key="verification_code_input",
                        help="Enter the 6-digit code that was just sent to you",
                        max_chars=6
                    )
                with col2:
                    if st.button("Submit Code", key="submit_verification_code"):
                        if verification_code and len(verification_code) == 6 and verification_code.isdigit():
                            st.session_state.verification_code = verification_code
                            st.rerun()
                        else:
                            st.error("Please enter a valid 6-digit code")
                return
            st.text_input(
                f"Please enter {cred}:", 
                key=cred, 
                type="password" if "password" in cred else "default"
            )
            return

    # Execute task
    messages = [{"role": "user", "content": current_task.description}]
    if "verification_code" in st.session_state:
        messages.append({
            "role": "user", 
            "content": f"The verification code is: {st.session_state.verification_code}"
        })

    try:
        result_messages = await sampling_loop(
            messages=messages,
            system_prompt_suffix="",
            output_callback=partial(_render_message, Sender.BOT),
            tool_output_callback=partial(_tool_output_callback, tool_state=st.session_state.tools),
            api_response_callback=partial(
                _api_response_callback, 
                tab=http_logs_tab,
                response_state=st.session_state.responses
            ),
            api_key=st.session_state.api_key,
            task_description=current_task.description
        )
        
        st.session_state.messages.extend(result_messages)

        # Check for task completion or need for user input
        if verify_task_completion(current_task):
            # Task completed successfully with downloaded files
            st.session_state.task_results.append({
                "task": current_task.description,
                "status": "completed",
                "file": current_task.downloaded_file
            })
            # Clean up states
            if "verification_code" in st.session_state:
                del st.session_state.verification_code
            if "verification_code_input" in st.session_state:
                del st.session_state.verification_code_input
            st.session_state.current_task_index += 1
            st.session_state.awaiting_user_confirmation = False
            st.rerun()
        else:
            # Check if we need user confirmation
            last_messages = " ".join(str(msg.get("content", "")) for msg in result_messages[-3:]).lower()
            if any(phrase in last_messages for phrase in [
                "no documents were", "no tax documents", "couldn't find", 
                "no forms available", "would you like me to", "anything else",
                "is there anything else", "to summarize", "successfully logged"
            ]):
                st.session_state.awaiting_user_confirmation = True
                
                # Get the last message from the assistant
                for msg in reversed(result_messages):
                    if isinstance(msg.get("content"), list):
                        for content in msg.get("content"):
                            if content.get("type") == "text":
                                st.session_state.user_confirmation_message = content.get("text", "")
                                break
                        if st.session_state.user_confirmation_message:
                            break
                
                # Show user confirmation interface
                st.info("Please confirm the status of this task:")
                st.write(st.session_state.user_confirmation_message)
                
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    user_input = st.text_area(
                        "Additional information (optional)",
                        help="Provide any additional information if needed",
                        key="user_confirmation_input"
                    )
                with col2:
                    if st.button("Confirm & Continue", key="confirm_task"):
                        if user_input:
                            st.session_state.messages.append({
                                "role": "user",
                                "content": [{"type": "text", "text": user_input}]
                            })
                        
                        st.session_state.task_results.append({
                            "task": current_task.description,
                            "status": "completed (no documents)",
                            "file": "No documents available"
                        })
                        st.session_state.current_task_index += 1
                        st.session_state.awaiting_user_confirmation = False
                        st.rerun()
                with col3:
                    if st.button("Retry Task", key="retry_task"):
                        st.session_state.awaiting_user_confirmation = False
                        st.rerun()
                
                return
            
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        st.session_state.workflow_running = False


async def main():
    setup_state()

    st.markdown(STREAMLIT_STYLE, unsafe_allow_html=True)
    st.title("Tax Document Collection Assistant")

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
            help="Additional instructions to append to the system prompt.",
            on_change=lambda: save_to_storage("system_prompt", st.session_state.custom_system_prompt),
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

    with chat:
        if not st.session_state.workflow_running:
            if st.button("Start Tax Document Collection", type="primary"):
                start_automated_workflow()
                st.rerun() 

        if st.session_state.workflow_running:
            st.info(f"Processing task {st.session_state.current_task_index + 1} of {len(PREDEFINED_TASKS)}")
            await process_next_task(http_logs)

        if st.session_state.task_results:
            st.subheader("Completed Tasks")
            for result in st.session_state.task_results:
                st.write(f"✓ {result['status']}: {result.get('file', 'No file downloaded')}")

        for message in st.session_state.messages:
            if isinstance(message["content"], str):
                _render_message(message["role"], message["content"])
            elif isinstance(message["content"], list):
                for block in message["content"]:
                    if isinstance(block, dict) and block["type"] == "tool_result":
                        _render_message(
                            Sender.TOOL, st.session_state.tools[block["tool_use_id"]]
                        )
                    else:
                        _render_message(
                            message["role"],
                            cast(BetaTextBlock | BetaToolUseBlock, block),
                        )

if __name__ == "__main__":
    asyncio.run(main())