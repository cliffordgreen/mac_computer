# src/ui/components/workflow_sidebar.py
import streamlit as st
from typing import Callable
from ...workflows.manager import WorkflowManager
from ...workflows.models import Workflow

def render_workflow_sidebar(
    workflow_manager: WorkflowManager,
    on_run_workflow: Callable[[str], None]
) -> None:
    st.sidebar.title("Workflow Management")
    
    # Recording controls
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("Start Recording", key="start_recording"):
            workflow_manager.start_recording()
            st.success("Started recording")
            
    with col2:
        if st.button("Stop Recording", key="stop_recording"):
            if workflow_manager.is_recording:
                workflow_manager.stop_recording()
                st.success("Stopped recording")
    
    # Recording status
    if workflow_manager.is_recording:
        st.sidebar.warning("🔴 Recording in progress...")
    
    # Save workflow form
    with st.sidebar.form("save_workflow"):
        st.subheader("Save Workflow")
        name = st.text_input("Name")
        description = st.text_area("Description")
        tags = st.text_input("Tags (comma-separated)")
        
        if st.form_submit_button("Save"):
            if not name:
                st.error("Name is required")
            else:
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]
                workflow_id = workflow_manager.save_workflow(
                    name=name,
                    description=description,
                    tags=tag_list
                )
                st.success(f"Saved workflow: {workflow_id}")
    
    # List workflows
    st.sidebar.subheader("Saved Workflows")
    
    # Filter by tags
    all_tags = workflow_manager.get_all_tags()
    selected_tag = st.sidebar.selectbox(
        "Filter by tag",
        ["All"] + sorted(all_tags)
    )
    
    workflows = workflow_manager.list_workflows(
        tag=None if selected_tag == "All" else selected_tag
    )
    
    for workflow in workflows:
        with st.sidebar.expander(f"{workflow.name} ({workflow.id[:8]})"):
            st.write(f"Description: {workflow.description}")
            st.write(f"Steps: {len(workflow.steps)}")
            st.write(f"Success rate: {workflow.success_count} runs")
            if workflow.tags:
                st.write(f"Tags: {', '.join(workflow.tags)}")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Run", key=f"run_{workflow.id}"):
                    on_run_workflow(workflow.id)
            
            with col2:
                if st.button("Edit", key=f"edit_{workflow.id}"):
                    st.session_state.editing_workflow = workflow
                    
            with col3:
                if st.button("Delete", key=f"delete_{workflow.id}"):
                    if workflow_manager.delete_workflow(workflow.id):
                        st.success("Workflow deleted")
                        st.experimental_rerun()