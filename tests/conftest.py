# tests/conftest.py
import pytest
import asyncio
from pathlib import Path
from typing import Generator
from src.workflows.manager import WorkflowManager
from src.tools.computer import MacComputer
from src.agent.enhanced_agent import EnhancedComputerAgent

@pytest.fixture
def temp_workflow_dir(tmp_path) -> Generator[Path, None, None]:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    yield workflow_dir

@pytest.fixture
def workflow_manager(temp_workflow_dir) -> WorkflowManager:
    return WorkflowManager(storage_dir=str(temp_workflow_dir))

@pytest.fixture
def computer_tool() -> MacComputer:
    return MacComputer()

@pytest.fixture
def enhanced_agent(workflow_manager) -> EnhancedComputerAgent:
    agent = EnhancedComputerAgent()
    agent.workflow_manager = workflow_manager
    return agent

@pytest.fixture
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()