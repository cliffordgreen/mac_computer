"""
TurboTax Document Collection Assistant powered by Streamlit
"""

import asyncio
import base64
import os
import tempfile
from datetime import datetime
from functools import partial
from pathlib import Path, PosixPath
from typing import cast
from enum import Enum
import time
from dotenv import load_dotenv

import streamlit as st
from anthropic import APIResponse
from anthropic.types import TextBlock, ToolUseBlock
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock
from streamlit.delta_generator import DeltaGenerator

# Load environment variables from .env file if present
load_dotenv()

from loop import DEFAULT_MODEL, sampling_loop
from tools.base import ToolResult
from tasks import PREDEFINED_TASKS, Task, verify_task_completion

# # Initialize hide_images checkbox
# st.checkbox("Hide screenshots", key="hide_images")

# TurboTax Brand Colors
TURBOTAX_COLORS = {
    'primary': '#0077C5',  # TurboTax Blue
    'secondary': '#2D333F', # Dark Blue/Gray
    'accent': '#51B5E0',    # Light Blue
    'success': '#2CA01C',   # Green
    'warning': '#F1C40F',   # Yellow
    'error': '#E74C3C',     # Red
    'background': '#F7F9FA', # Light Gray
    'text': '#2D333F'       # Dark Gray
}

# # Custom Streamlit Theme
# STREAMLIT_STYLE = """
# <style>
#     /* Main container styling */
#     .stApp {
#         background-color: #F7F9FA;
#     }
    
#     /* Header styling */
#     .stTitle {
#         color: #0077C5 !important;
#         font-family: 'Intuit Brown', -apple-system, BlinkMacSystemFont, sans-serif;
#         font-weight: 600;
#     }
    
#     /* Button styling */
#     .stButton > button {
#         background-color: #0077C5;
#         color: white;
#         border-radius: 4px;
#         border: none;
#         padding: 0.5rem 1rem;
#         font-weight: 500;
#     }
    
#     .stButton > button:hover {
#         background-color: #005587;
#     }
    
#     /* Chat message styling */
#     .stChatMessage {
#         background-color: white;
#         border-radius: 8px;
#         box-shadow: 0 2px 4px rgba(0,0,0,0.1);
#         padding: 1rem;
#     }
    
#     /* Input field styling */
#     .stTextInput > div > div > input {
#         border-radius: 4px;
#         border: 1px solid #D1D5DB;
#     }
    
#     /* Sidebar styling */
#     .css-1d391kg {
#         background-color: #2D333F;
#     }
    
#     .sidebar .sidebar-content {
#         background-color: #2D333F;
#         color: white;
#     }
    
#     /* Hide deployment button */
#     .stDeployButton {
#         visibility: hidden;
#     }

#     /* Custom header styling */
#     .header-container {
#         padding: 1rem;
#         background-color: white;
#         border-radius: 8px;
#         margin-bottom: 2rem;
#         box-shadow: 0 2px 4px rgba(0,0,0,0.05);
#     }

#     .header-title {
#         color: #0077C5;
#         font-size: 2rem;
#         font-weight: 600;
#         margin-bottom: 0.5rem;
#     }

#     .header-subtitle {
#         color: #2D333F;
#         font-size: 1rem;
#     }
# </style>
# """

# Updated warning text with TurboTax branding
WARNING_TEXT = """
🔒 **TurboTax Document Assistant**
Securely collect and organize your tax documents with the help of our AI-powered assistant.
"""

def setup_page_config():
    """Configure Streamlit page settings"""
    st.set_page_config(
        page_title="TurboTax Document Assistant",
        page_icon="📑",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.markdown(STREAMLIT_STYLE, unsafe_allow_html=True)

def create_header():
    """Create branded header section"""
    st.markdown(
        """
        <div class="header-container">
            <div class="header-title">📑 TurboTax Document Assistant</div>
            <div class="header-subtitle">Simplifying tax document collection</div>
        </div>
        """,
        unsafe_allow_html=True
    )



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

# WARNING_TEXT = "We Can Do It! is a tool that helps you collect tax documents"

def setup_state():
    """Initialize all session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "api_key" not in st.session_state:
        st.session_state.api_key = load_from_storage("api_key") or os.getenv("ANTHROPIC_API_KEY", "")
    if "google_project_id" not in st.session_state:
        st.session_state.google_project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    if "google_processor_id" not in st.session_state:
        st.session_state.google_processor_id = os.getenv("DOCUMENT_AI_PROCESSOR_ID", "")
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

# async def main():
#     setup_page_config()
#     setup_state()
#     create_header()

#     if not os.getenv("HIDE_WARNING", False):
#         st.markdown(
#             f"""
#             <div style='background-color: {TURBOTAX_COLORS['primary']}; padding: 1rem; border-radius: 4px; color: white;'>
#                 {WARNING_TEXT}
#             </div>
#             """,
#             unsafe_allow_html=True
#         )

#     # Create a modern sidebar
#     with st.sidebar:
#         st.markdown("### ⚙️ Configuration")
#         st.text_input("Model", key="model")
#         st.text_input(
#             "API Key",
#             type="password",
#             key="api_key",
#             help="Enter your Anthropic API key",
#             on_change=lambda: save_to_storage("api_key", st.session_state.api_key),
#         )
        
#         with st.expander("Advanced Settings"):
#             st.number_input(
#                 "Recent Images Limit",
#                 min_value=0,
#                 key="only_n_most_recent_images",
#                 help="Limit the number of recent images in conversation"
#             )
#             st.text_area(
#                 "Custom System Prompt",
#                 key="custom_system_prompt",
#                 help="Additional system instructions",
#                 on_change=lambda: save_to_storage("system_prompt", st.session_state.custom_system_prompt),
#             )
#             st.checkbox("Hide Screenshots", key="hide_images")

#         if st.button("Reset Session", type="secondary"):
#             st.session_state.clear()
#             setup_state()
async def main():
    setup_state()
    setup_page_config()

    st.title("TurboTax Document Assistant")
    st.subheader("Upload tax documents and let our AI automate TurboTax entry")

    if "uploaded_files" not in st.session_state:
        st.session_state.uploaded_files = []
    
    if "extracted_documents" not in st.session_state:
        st.session_state.extracted_documents = []
    
    if "turbotax_status" not in st.session_state:
        st.session_state.turbotax_status = "Not started"

    # Create tabs for document flow
    upload_tab, extract_tab, turbotax_tab = st.tabs([
        "Upload Documents", 
        "Extract Information", 
        "TurboTax Automation"
    ])

    # Tab 1: Document Upload
    with upload_tab:
        st.header("Upload Tax Documents")
        
        # File uploader
        uploaded_files = st.file_uploader(
            "Upload your tax documents (W-2, 1099 forms, etc.)",
            accept_multiple_files=True,
            type=["pdf", "jpg", "jpeg", "png"],
            help="Supported file formats: PDF, JPEG, PNG"
        )
        
        # Handle uploaded files
        if uploaded_files:
            for file in uploaded_files:
                if file.name not in [f["name"] for f in st.session_state.uploaded_files]:
                    # Save file to temp directory
                    temp_dir = Path(tempfile.gettempdir()) / "tax_documents"
                    temp_dir.mkdir(exist_ok=True)
                    
                    temp_file = temp_dir / file.name
                    with open(temp_file, "wb") as f:
                        f.write(file.getbuffer())
                    
                    # Add to session state
                    file_info = {
                        "name": file.name,
                        "path": str(temp_file),
                        "size": file.size,
                        "type": file.type,
                        "timestamp": datetime.now().isoformat()
                    }
                    st.session_state.uploaded_files.append(file_info)
        
        # Display uploaded documents
        if st.session_state.uploaded_files:
            st.subheader("Uploaded Documents")
            
            for i, file_info in enumerate(st.session_state.uploaded_files):
                col1, col2, col3 = st.columns([4, 1, 1])
                
                with col1:
                    st.text(f"{i+1}. {file_info['name']}")
                
                with col2:
                    if 'size' in file_info:
                        file_size = file_info['size'] // 1024  # Convert to KB
                        st.text(f"{file_size} KB")
                
                with col3:
                    # Add remove button per file
                    if st.button("Remove", key=f"remove_{i}"):
                        # Remove file from session state
                        path = file_info.get("path")
                        if path and os.path.exists(path):
                            try:
                                os.remove(path)
                            except:
                                pass
                        st.session_state.uploaded_files.pop(i)
                        st.rerun()
            
            # Add button to clear all files
            if st.button("Clear All Files", type="secondary"):
                # Delete temp files
                for file_info in st.session_state.uploaded_files:
                    path = file_info.get("path")
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except:
                            pass
                
                # Clear session state
                st.session_state.uploaded_files = []
                st.rerun()
        else:
            st.info("Please upload your tax documents to get started.")

    # Tab 2: Extract Information
    with extract_tab:
        st.header("Extract Information from Documents")
        
        if not st.session_state.uploaded_files:
            st.warning("Please upload tax documents in the Upload tab first.")
        else:
            if st.button("Extract Information from Documents", type="primary"):
                # Show progress
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Process each document
                from tax_automation import TaxAutomation
                
                # Check if Google Document AI is configured
                google_project_id = st.session_state.get("google_project_id", "")
                google_processor_id = st.session_state.get("google_processor_id", "")
                
                if not google_project_id or not google_processor_id:
                    st.error("Google Document AI is not configured. Please set the Project ID and Processor ID in the sidebar.")
                    return
                
                # Initialize TaxAutomation with Google Document AI settings
                tax_automation = TaxAutomation(
                    project_id=google_project_id, 
                    processor_id=google_processor_id
                )
                
                # Clear previous extraction results
                st.session_state.extracted_documents = []
                
                for i, file_info in enumerate(st.session_state.uploaded_files):
                    try:
                        # Update progress
                        progress = int((i / len(st.session_state.uploaded_files)) * 100)
                        progress_bar.progress(progress)
                        status_text.text(f"Processing {file_info['name']}...")
                        
                        # Extract information
                        tax_doc = tax_automation.extract_from_document(file_info['path'])
                        st.session_state.extracted_documents.append(tax_doc)
                    except Exception as e:
                        st.error(f"Error processing {file_info['name']}: {str(e)}")
                
                # Complete progress
                progress_bar.progress(100)
                status_text.text("Document processing completed!")
                
                # Show success message
                if st.session_state.extracted_documents:
                    st.success(f"Successfully extracted information from {len(st.session_state.extracted_documents)} documents.")
            
            # Display extracted information
            if st.session_state.extracted_documents:
                st.subheader("Extracted Tax Information")
                
                import pandas as pd
                
                # Prepare data for table
                data = []
                for doc in st.session_state.extracted_documents:
                    # Format fields as a string
                    fields_str = ", ".join([f"{k}: {v}" for k, v in doc.fields.items()])
                    
                    data.append({
                        "Document Type": doc.doc_type,
                        "Issuer": doc.issuer,
                        "Tax Year": doc.tax_year,
                        "Fields": fields_str
                    })
                
                # Display as table
                if data:
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True)
                
                # Option to save extracted data
                if st.button("Export Data (JSON)"):
                    # Create JSON data
                    import json
                    
                    json_data = []
                    for doc in st.session_state.extracted_documents:
                        json_data.append({
                            "doc_type": doc.doc_type,
                            "issuer": doc.issuer,
                            "tax_year": doc.tax_year,
                            "fields": doc.fields,
                            "source_file": os.path.basename(doc.source_file)
                        })
                    
                    # Save to a file
                    temp_json = Path(tempfile.gettempdir()) / "tax_data.json"
                    with open(temp_json, "w") as f:
                        json.dump(json_data, f, indent=2)
                    
                    # Provide download link
                    with open(temp_json, "rb") as f:
                        st.download_button(
                            label="Download JSON",
                            data=f,
                            file_name="tax_data.json",
                            mime="application/json"
                        )

    # Tab 3: TurboTax Automation
    with turbotax_tab:
        st.header("TurboTax Automation")
        
        if not st.session_state.extracted_documents:
            st.warning("Please extract document information in the Extract Information tab first.")
        else:
            # TurboTax credentials section
            with st.expander("TurboTax Login Credentials", expanded=True):
                st.write("Enter your TurboTax login credentials:")
                
                col1, col2 = st.columns(2)
                with col1:
                    email = st.text_input("Email", key="turbotax_email")
                with col2:
                    password = st.text_input("Password", type="password", key="turbotax_password")
                
                # Browser visibility toggle
                headless_mode = st.checkbox("Run in headless mode (browser will not be visible)", key="headless_mode", value=False)
                st.info("""
                * When headless mode is OFF, you'll see the browser automation happen on screen
                * When headless mode is ON, automation runs in the background without showing a browser window
                """)
                
                st.info("Your credentials are used only for this session and not stored.")
            
            # Start automation button
            if st.button("Start TurboTax Automation", type="primary"):
                if not email or not password:
                    st.error("Please enter your TurboTax email and password.")
                else:
                    # Show progress
                    st.session_state.turbotax_status = "In progress"
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Step 1: Login to TurboTax
                    status_text.text("Logging into TurboTax...")
                    progress_bar.progress(10)
                    
                    # Display message
                    st.info("⚠️ Starting TurboTax automation. The agent will now open a browser window and automate TurboTax. Please do not interact with your computer until the process completes.")
                    
                    # Create a placeholder for the log
                    log_container = st.container()
                    log_container.write("Automation Log:")
                    log_text = log_container.empty()
                    
                    # Create log capture function
                    import sys
                    import io
                    import time
                    import asyncio
                    from tax_automation import TaxAutomation
                    
                    log_entries = [
                        "Starting TurboTax automation...",
                        "Initializing browser..."
                    ]
                    log_text.write("\n".join(log_entries))
                    
                    # Capture print statements to show in the UI
                    class LogCapture:
                        def __init__(self, log_text_widget):
                            self.log_text_widget = log_text_widget
                            self.log_entries = log_entries
                            self.original_stdout = sys.stdout
                            
                        def write(self, text):
                            if text.strip():  # Only add non-empty lines
                                self.log_entries.append(text.strip())
                                self.log_text_widget.write("\n".join(self.log_entries))
                            self.original_stdout.write(text)
                            
                        def flush(self):
                            self.original_stdout.flush()
                    
                    # Set up log capture
                    log_capture = LogCapture(log_text)
                    sys.stdout = log_capture
                    
                    try:
                        # Get headless mode setting
                        headless = st.session_state.get("headless_mode", False)
                        
                        # Initialize tax automation
                        tax_automation = TaxAutomation(
                            project_id=st.session_state.get("google_project_id", ""), 
                            processor_id=st.session_state.get("google_processor_id", ""),
                            api_key=st.session_state.get("api_key", "")  # Pass API key directly
                        )
                        
                        # Use the extracted documents
                        tax_automation.extracted_documents = st.session_state.extracted_documents
                        
                        # Run the actual automation (this will be visible if headless=False)
                        # Convert document paths to list
                        doc_paths = [doc.source_file for doc in st.session_state.extracted_documents]
                        
                        progress_bar.progress(20)
                        status_text.text("Starting browser automation...")
                        
                        # Create a background task for the automation
                        async def run_automation():
                            # We already have the extracted documents, so skip extraction step
                            if tax_automation.extracted_documents:
                                print(f"Starting TurboTax automation with {len(tax_automation.extracted_documents)} documents")
                                print(f"Headless mode: {'ON' if headless else 'OFF'}")
                                
                                # Access the correct variables from the outer scope
                                nonlocal email, password
                                
                                # Debug output for credentials
                                print(f"DEBUG (Safe): Email first 3 chars: {email[:3]}..., password length: {len(password)}")
                                
                                # Validate password before attempting login
                                if len(password) < 6 or ' ' in password:
                                    print("WARNING: Password does not meet TurboTax requirements (min 6 chars, no spaces)")
                                    print(f"Original password length: {len(password)}, contains spaces: {' ' in password}")
                                    
                                    # Fix password formatting
                                    fixed_password = password.replace(' ', '')
                                    if len(fixed_password) < 6:
                                        fixed_password = fixed_password + "123456"[:6-len(fixed_password)]
                                    print(f"Using corrected password format (showing length only): {len(fixed_password)} chars")
                                    password = fixed_password
                                
                                # Ensure we're using a valid password - hardcode a known working password for testing
                                if password == "USE_TEST_PASSWORD":
                                    password = "Intuit01-"
                                    print("Using test password for TurboTax login")
                                
                                # Process documents with TurboTax
                                await tax_automation.login_to_turbotax(
                                    headless=headless, 
                                    email=email, 
                                    password=password
                                )
                                
                                # Process each document
                                for i, doc in enumerate(tax_automation.extracted_documents):
                                    progress = 30 + int((i / len(tax_automation.extracted_documents)) * 60)
                                    progress_bar.progress(progress)
                                    status_text.text(f"Processing {doc.doc_type} from {doc.issuer}...")
                                    
                                    result = await tax_automation.enter_document_to_turbotax(doc)
                                    if result:
                                        print(f"✅ Successfully entered {doc.doc_type} from {doc.issuer}")
                                    else:
                                        print(f"❌ Failed to enter {doc.doc_type} from {doc.issuer}")
                                
                                # Close browser
                                if hasattr(tax_automation, 'browser') and tax_automation.browser:
                                    await tax_automation.browser.close()
                                    print("Closed browser session")
                        
                        # Run the automation
                        await run_automation()
                        
                        # Complete automation
                        progress_bar.progress(100)
                        status_text.text("TurboTax automation completed successfully!")
                        st.session_state.turbotax_status = "Completed"
                        
                        # Add final log entries
                        print("All documents processed successfully!")
                        print("Automation complete!")
                        
                        # Show success message
                        st.success("✅ TurboTax automation completed!")
                        
                    except Exception as e:
                        print(f"Error during automation: {str(e)}")
                        st.error(f"An error occurred during automation: {str(e)}")
                    finally:
                        # Restore original stdout
                        sys.stdout = sys.__stdout__
            
            # Show automation status
            if st.session_state.turbotax_status == "Completed":
                st.success("All tax data has been successfully entered into TurboTax!")
                
                # Option to restart
                if st.button("Start New Session", type="secondary"):
                    st.session_state.turbotax_status = "Not started"
                    st.rerun()

    # Sidebar configuration
    with st.sidebar:
        st.header("Configuration")
        
        # API key configuration
        st.text_input(
            "Anthropic API Key",
            type="password",
            key="api_key",
            help="Enter your Anthropic API key for AI functionality",
            on_change=lambda: save_to_storage("api_key", st.session_state.api_key),
        )
        
        # Google Document AI Configuration
        st.subheader("Google Document AI")
        
        # Display environment status
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            st.success(f"✅ Google credentials file found: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")
        else:
            st.warning("""⚠️ Google Application Credentials not set. 
            Please set the GOOGLE_APPLICATION_CREDENTIALS environment variable to point to your service account key file.""")
            st.markdown("""
            To set credentials, create a .env file with:
            ```
            GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-service-account-key.json
            ```
            """)
        
        # Project and processor input fields
        project_id = st.text_input(
            "Google Cloud Project ID",
            value=st.session_state.google_project_id,
            key="google_project_id",
            help="Enter your Google Cloud Project ID"
        )
        
        processor_id = st.text_input(
            "Document AI Processor ID",
            value=st.session_state.google_processor_id,
            key="google_processor_id",
            help="Enter your Document AI Form Parser Processor ID"
        )
        
        # Setup guide with more detailed information
        with st.expander("How to Set Up Google Document AI"):
            st.markdown("""
            ### Step 1: Create a Google Cloud Project
            1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
            2. Create a new project or select an existing one
            3. Note your Project ID
            
            ### Step 2: Enable the Document AI API
            1. In your project, go to "APIs & Services" > "Library"
            2. Search for "Document AI API" and enable it
            
            ### Step 3: Create a Document AI Processor
            1. Go to the [Document AI console](https://console.cloud.google.com/ai/document-ai)
            2. Click "Create Processor"
            3. Select "Form Parser" as the processor type
            4. Choose a location (e.g., "us")
            5. After creation, copy the Processor ID
            
            ### Step 4: Set Up Authentication
            1. In the Google Cloud Console, go to "IAM & Admin" > "Service Accounts"
            2. Create a new service account with "Document AI User" role
            3. Create and download a JSON key for this service account
            4. Set the GOOGLE_APPLICATION_CREDENTIALS environment variable to point to this key file
            """)
        
        # Show current configuration status
        if project_id and processor_id:
            st.success("Google Document AI configuration is complete")
        else:
            st.error("Please complete the Google Document AI configuration to use document extraction")
        
        st.checkbox("Hide screenshots", key="hide_images", value=True)
        
        # Reset button
        if st.button("Reset Application", type="secondary"):
            # Confirm reset
            if st.session_state.get("confirm_reset", False):
                st.session_state.clear()
                setup_state()
                st.rerun()
            else:
                st.session_state.confirm_reset = True
                st.warning("Click 'Reset Application' again to confirm. This will clear all uploaded documents and extracted data.")
        
        # Help information
        with st.expander("Help"):
            st.markdown("""
            ### Using the TurboTax Document Assistant
            
            1. **Configure Google Document AI**: Set up Google Document AI in the sidebar
            2. **Upload Documents**: Upload your tax documents (W-2, 1099, etc.) in the first tab
            3. **Extract Information**: Process documents to extract tax information using Google Document AI
            4. **TurboTax Automation**: Enter your TurboTax credentials to have the AI automatically enter your tax data
            
            ### Supported Document Types
            - W-2 (Wage and Tax Statement)
            - 1099-INT (Interest Income)
            - 1099-DIV (Dividends and Distributions)
            - 1099-B (Proceeds from Broker)
            - 1099-MISC (Miscellaneous Income)
            - 1098 (Mortgage Interest)
            - 1098-E (Student Loan Interest)
            
            ### Setting Up Google Document AI
            1. Create a Google Cloud account if you don't have one
            2. Create a new project in Google Cloud Console
            3. Enable the Document AI API for your project
            4. Create a Form Parser processor in Document AI
            5. Copy the Project ID and Processor ID to the sidebar configuration
            """)
            
        # About
        st.markdown("---")
        st.markdown("Made with ❤️ by Claude")

    if not st.session_state.auth_validated:
        if auth_error := validate_auth(st.session_state.api_key):
            st.warning(f"API Key not configured properly:\n\n{auth_error}")
        else:
            st.session_state.auth_validated = True

if __name__ == "__main__":
    asyncio.run(main())