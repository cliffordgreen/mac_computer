# tests/test_agent.py
import pytest
from unittest.mock import Mock, patch
from src.agent.enhanced_agent import EnhancedComputerAgent
from src.tools.results import ToolResult

@pytest.mark.asyncio
async def test_agent_process_message(enhanced_agent):
    with patch('anthropic.Anthropic') as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value.content = "Moving mouse to 100, 100"
        mock_anthropic.return_value = mock_client
        
        result = await enhanced_agent.process_message("Move mouse to 100, 100")
        assert isinstance(result, ToolResult)
        assert "mouse" in result.output.lower()

@pytest.mark.asyncio
async def test_agent_workflow_recording(enhanced_agent):
    enhanced_agent.workflow_manager.start_recording()
    
    with patch('anthropic.Anthropic') as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value.content = "Taking screenshot"
        mock_anthropic.return_value = mock_client
        
        await enhanced_agent.process_message("Take a screenshot")
        
        workflows = enhanced_agent.workflow_manager.list_workflows()
        assert len(workflows) == 0  # Not saved yet
        
        workflow_id = enhanced_agent.workflow_manager.save_workflow(
            name="Test Workflow",
            description="Test Description"
        )
        
        workflows = enhanced_agent.workflow_manager.list_workflows()
        assert len(workflows) == 1
        assert workflows[0].steps[0].action == "screenshot"