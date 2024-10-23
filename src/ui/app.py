# src/ui/app.py
import streamlit as st
import asyncio
from typing import Any
from ..agent.enhanced_agent import EnhancedComputerAgent, APIProvider
from ..tools.results import ToolResult
from .components.chat import render_chat_message
from .components.workflow_sidebar import render_workflow_sidebar

class StreamlitApp:
    def __init__(self):
        self.setup_state()
        self.setup_layout()
        
    def setup_state(self):
        """Initialize session state variables"""
        if "messages" not in st.session_state:
            st.session_state.messages = []
        if "agent" not in st.session_state:
            st.session_state.agent = EnhancedComputerAgent()
            
    def setup_layout(self):
        """Setup the main app layout"""
        st.set_page_config(
            page_title="Mac Computer Control",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Add custom CSS
        with open("src/ui/styles/main.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
            
    async def handle_message(self, message: str):
        """Handle basic message processing"""
        response = await st.session_state.agent.process_message(message)
        return response
        
    async def handle_message_with_callbacks(self, message: str):
        """Handle message processing with detailed callbacks"""
        messages = [{"role": "user", "content": message}]
        
        # Create a placeholder for real-time updates
        status_placeholder = st.empty()
        
        def output_callback(block: Any):
            """Handle output from the model"""
            with status_placeholder:
                if hasattr(block, 'text'):
                    st.write(f"🤔 Thinking: {block.text}")
                elif hasattr(block, 'type') and block.type == "tool_use":
                    st.write(f"🛠️ Using tool: {block.name}")
                    
        def tool_callback(result: ToolResult, tool_id: str):
            """Handle tool execution results"""
            with status_placeholder:
                if result.output:
                    st.write(f"✅ Tool result: {result.output}")
                if result.error:
                    st.error(f"❌ Tool error: {result.error}")
                if result.base64_image:
                    st.image(result.base64_image)
                    
        def api_callback(response: Any):
            """Handle API responses"""
            with status_placeholder:
                st.write("📡 Received API response")
        
        try:
            final_messages = await st.session_state.agent.sampling_loop(
                model="claude-3-opus-20240229",
                provider=APIProvider.ANTHROPIC,
                system_prompt_suffix="",
                messages=messages,
                output_callback=output_callback,
                tool_output_callback=tool_callback,
                api_response_callback=api_callback,
                api_key=st.secrets["ANTHROPIC_API_KEY"],
                only_n_most_recent_images=10,
            )
            
            # Clear the status placeholder
            status_placeholder.empty()
            
            return final_messages
            
        except Exception as e:
            st.error(f"Error processing message: {str(e)}")
            return None
            
    def render(self):
        """Render the main application"""
        st.title("Mac Computer Control Assistant")
        
        # Render sidebar
        render_workflow_sidebar(
            st.session_state.agent.workflow_manager,
            lambda workflow_id: asyncio.run(
                self.handle_message(f"Run workflow {workflow_id}")
            )
        )
        
        # Display chat history
        for message in st.session_state.messages:
            render_chat_message(message)
            
        # Chat input
        if prompt := st.chat_input("What would you like me to do?"):
            # Add user message to chat
            st.session_state.messages.append({
                "role": "user",
                "content": prompt
            })
            render_chat_message({"role": "user", "content": prompt})
            
            # Process message with callbacks
            with st.chat_message("assistant"):
                with st.spinner("Processing..."):
                    response = asyncio.run(
                        self.handle_message_with_callbacks(prompt)
                    )
                    
                    if response:
                        # Add assistant response to chat
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response[-1]["content"]
                        })
                        render_chat_message({
                            "role": "assistant",
                            "content": response[-1]["content"]
                        })

def main():
    app = StreamlitApp()
    app.render()

if __name__ == "__main__":
    main()