# tests/test_workflows.py
import pytest
from datetime import datetime
from src.workflows.models import Workflow, WorkflowStep
from src.tools.results import ToolResult

def test_workflow_creation(workflow_manager):
    workflow_id = workflow_manager.save_workflow(
        name="Test Workflow",
        description="Test Description",
        tags=["test"]
    )
    
    workflow = workflow_manager.load_workflow(workflow_id)
    assert workflow.name == "Test Workflow"
    assert workflow.description == "Test Description"
    assert workflow.tags == ["test"]

def test_workflow_step_addition(workflow_manager):
    workflow_manager.start_recording()
    
    step = WorkflowStep(
        action="mouse_move",
        parameters={"x": 100, "y": 100}
    )
    workflow_manager.add_step(step)
    
    workflow_id = workflow_manager.save_workflow(
        name="Test Workflow",
        description="Test Description"
    )
    
    workflow = workflow_manager.load_workflow(workflow_id)
    assert len(workflow.steps) == 1
    assert workflow.steps[0].action == "mouse_move"

@pytest.mark.asyncio
async def test_workflow_execution(workflow_manager, computer_tool):
    # Create a workflow
    workflow_manager.start_recording()
    
    step = WorkflowStep(
        action="type",
        parameters={"text": "Hello, World!"}
    )
    workflow_manager.add_step(step)
    
    workflow_id = workflow_manager.save_workflow(
        name="Test Workflow",
        description="Test Description"
    )
    
    # Execute the workflow
    result = await workflow_manager.execute_workflow(workflow_id, computer_tool)
    assert isinstance(result, ToolResult)
    assert result.error is None
    
    # Check that success count was incremented
    workflow = workflow_manager.load_workflow(workflow_id)
    assert workflow.success_count == 1
    assert workflow.last_run is not None