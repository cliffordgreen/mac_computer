# src/tools/computer.py
import asyncio
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal, Dict, Any
import pyautogui
import Quartz
from PIL import Image
import AppKit
from ..utils.logger import logger
from .base import BaseTool
from .results import ToolResult

class MacComputer(BaseTool):
    def __init__(self):
        # Get screen dimensions
        screen = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        self.width = screen.size.width
        self.height = screen.size.height
        
        # Configure PyAutoGUI
        pyautogui.FAILSAFE = False
        self.screenshot_dir = Path("data/screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
    async def __call__(
        self,
        action: Literal[
            "mouse_move",
            "click",
            "double_click",
            "right_click",
            "type",
            "screenshot",
            "get_position",
            "press_key",
            "hotkey"
        ],
        **kwargs
    ) -> ToolResult:
        try:
            method = getattr(self, f"_handle_{action}")
            return await method(**kwargs)
        except AttributeError:
            return ToolResult(error=f"Unknown action: {action}")
        except Exception as e:
            logger.error(f"Error in computer action {action}: {str(e)}")
            return ToolResult(error=f"Error performing {action}: {str(e)}")
            
    async def _handle_mouse_move(self, x: int, y: int, **kwargs) -> ToolResult:
        pyautogui.moveTo(x, y)
        return ToolResult(output=f"Moved mouse to {x}, {y}")
        
    async def _handle_click(self, **kwargs) -> ToolResult:
        pyautogui.click()
        return ToolResult(output="Clicked")
        
    async def _handle_double_click(self, **kwargs) -> ToolResult:
        pyautogui.click(clicks=2)
        return ToolResult(output="Double clicked")
        
    async def _handle_right_click(self, **kwargs) -> ToolResult:
        pyautogui.click(button='right')
        return ToolResult(output="Right clicked")
        
    async def _handle_type(self, text: str, **kwargs) -> ToolResult:
        pyautogui.write(text, interval=0.01)
        return ToolResult(output=f"Typed: {text}")
        
    async def _handle_screenshot(self, **kwargs) -> ToolResult:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.screenshot_dir / f"screenshot_{timestamp}.png"
        
        screenshot = pyautogui.screenshot()
        screenshot.save(filename)
        
        with open(filename, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode()
            
        return ToolResult(
            output="Screenshot taken",
            base64_image=base64_image
        )
        
    async def _handle_get_position(self, **kwargs) -> ToolResult:
        x, y = pyautogui.position()
        return ToolResult(output=f"Mouse position: {x}, {y}")
        
    async def _handle_press_key(self, key: str, **kwargs) -> ToolResult:
        pyautogui.press(key)
        return ToolResult(output=f"Pressed key: {key}")
        
    async def _handle_hotkey(self, keys: list[str], **kwargs) -> ToolResult:
        pyautogui.hotkey(*keys)
        return ToolResult(output=f"Pressed hotkey: {'+'.join(keys)}")