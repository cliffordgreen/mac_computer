# tests/test_tools.py
import pytest
from src.tools.computer import MacComputer
from src.tools.results import ToolResult

@pytest.mark.asyncio
async def test_mouse_move(computer_tool):
    result = await computer_tool(action="mouse_move", x=100, y=100)
    assert isinstance(result, ToolResult)
    assert "Moved mouse" in result.output

@pytest.mark.asyncio
async def test_type_text(computer_tool):
    result = await computer_tool(action="type", text="Hello, World!")
    assert isinstance(result, ToolResult)
    assert "Typed" in result.output

@pytest.mark.asyncio
async def test_screenshot(computer_tool):
    result = await computer_tool(action="screenshot")
    assert isinstance(result, ToolResult)
    assert result.base64_image is not None
    assert "Screenshot taken" in result.output

@pytest.mark.asyncio
async def test_invalid_action(computer_tool):
    result = await computer_tool(action="invalid_action")
    assert isinstance(result, ToolResult)
    assert result.error is not None
    assert "Unknown action" in result.error