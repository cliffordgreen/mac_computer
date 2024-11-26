import asyncio
import base64
import os
import shlex
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Literal, TypedDict
from uuid import uuid4
import pyautogui


from anthropic.types.beta import BetaToolComputerUse20241022Param

from .base import BaseAnthropicTool, ToolError, ToolResult
from .run import run

OUTPUT_DIR = "/tmp/outputs"

TYPING_DELAY_MS = 12
TYPING_GROUP_SIZE = 50

Action = Literal[
    "key",
    "type",
    "mouse_move",
    "left_click",
    "left_click_drag",
    "right_click",
    "middle_click",
    "double_click",
    "screenshot",
    "cursor_position",
]

class Resolution(TypedDict):
    width: int
    height: int

class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value

class ScalingSource(StrEnum):
    COMPUTER = "computer"
    API = "api"

MAX_SCALING_TARGETS: dict[str, Resolution] = {
    "XGA": Resolution(width=1024, height=768),
    "WXGA": Resolution(width=1280, height=800),
    "FWXGA": Resolution(width=1366, height=768),
}

class ComputerToolOptions(TypedDict):
    display_width_px: int
    display_height_px: int
    display_number: int | None

def chunks(s: str, chunk_size: int) -> list[str]:
    return [s[i : i + chunk_size] for i in range(0, len(s), chunk_size)]

class ComputerTool(BaseAnthropicTool):
    name: Literal["computer"] = "computer"
    api_type: Literal["computer_20241022"] = "computer_20241022"
    width: int
    height: int
    display_num: int | None

    _screenshot_delay = 2.0
    _scaling_enabled = True

    def __init__(self):
        super().__init__()
        try:
            cmd = "system_profiler SPDisplaysDataType | grep Resolution"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            resolution = result.stdout.strip()
            if resolution:
                width, height = map(int, resolution.split(":")[1].split("x"))
                self.width = width
                self.height = height
            else:
                self.width = 1440
                self.height = 900
        except Exception:
            self.width = 1440
            self.height = 900

        self.display_num = None
        self._display_prefix = ""

    @property
    def options(self) -> ComputerToolOptions:
        width, height = self.scale_coordinates(
            ScalingSource.COMPUTER, self.width, self.height
        )
        return {
            "display_width_px": width,
            "display_height_px": height,
            "display_number": self.display_num,
        }

    def to_params(self) -> BetaToolComputerUse20241022Param:
        return {"name": self.name, "type": self.api_type, **self.options}

    async def __call__(
        self,
        *,
        action: Action,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        **kwargs,
    ):
        if action in ("mouse_move", "left_click_drag"):
            if coordinate is None:
                raise ToolError(f"coordinate is required for {action}")
            if text is not None:
                raise ToolError(f"text is not accepted for {action}")
            if not isinstance(coordinate, (list, tuple)) or len(coordinate) != 2:
                raise ToolError(f"{coordinate} must be a tuple of length 2")
            if not all(isinstance(i, int) and i >= 0 for i in coordinate):
                raise ToolError(f"{coordinate} must be a tuple of non-negative ints")

            x, y = self.scale_coordinates(
                ScalingSource.API, coordinate[0], coordinate[1]
            )

            if action == "mouse_move":
                pyautogui.moveTo(x, y)
                return ToolResult(output=f"Moved mouse to {x}, {y}")
            elif action == "left_click_drag":
                pyautogui.dragTo(x, y)
                return ToolResult(output=f"Dragged mouse to {x}, {y}")

        if action in ("key", "type"):
            if text is None:
                raise ToolError(f"text is required for {action}")
            if coordinate is not None:
                raise ToolError(f"coordinate is not accepted for {action}")
            if not isinstance(text, str):
                raise ToolError(output=f"{text} must be a string")

            if action == "key":
                # Map of special keys to their key codes
                key_codes = {
                    "return": "36",
                    "tab": "48",
                    "space": "49",
                    "delete": "51",
                    "escape": "53",
                    "arrow-left": "123",
                    "arrow-right": "124",
                    "arrow-down": "125",
                    "arrow-up": "126",
                    "home": "115",
                    "end": "119",
                    "page-up": "116",
                    "page-down": "121",
                }

                # Map of modifier keys
                # modifier_map = {
                #     "ctrl": "control",
                #     "control": "control",
                #     "cmd": "command",
                #     "command": "command",
                #     "alt": "option",
                #     "option": "option",
                #     "shift": "shift"
                # }
                modifier_map = {
                    "ctrl": "control down",
                    "control": "control down",
                    "cmd": "command down",
                    "command": "command down",
                    "alt": "option down",
                    "option": "option down",
                    "shift": "shift down"
                }

                if "+" in text:
                    parts = [part.strip() for part in text.split("+")]
                    modifiers = []
                    key = parts[-1]

                    # Standardize key
                    key = key.lower().replace('_', '-')

                    # Process modifiers
                    for mod in parts[:-1]:
                        mod = mod.lower()
                        if mod not in modifier_map:
                            raise ToolError(f"Invalid modifier key: {mod}. Valid modifiers are: {', '.join(modifier_map.keys())}")
                        modifiers.append(modifier_map[mod])

                    modifier_string = ", ".join(modifiers)

                    if len(key) == 1:
                        # Escape quotes in the key character
                        escaped_key = key.replace('"', '\\"')
                        cmd = f"""osascript -e 'tell application "System Events" to keystroke "{escaped_key}" using {{{modifier_string}}}'"""
                    else:
                        if key not in key_codes:
                            valid_keys = ', '.join(key_codes.keys())
                            raise ToolError(
                                f"Invalid key: {key}. Valid keys are: {valid_keys}. "
                                "Please use lowercase letters and replace underscores with hyphens."
                            )
                        cmd = f"""osascript -e 'tell application "System Events" to key code {key_codes[key]} using {{{modifier_string}}}'"""
                else:
                    # Handle keys without modifiers
                    key = text.lower().replace('_', '-')
                    if len(key) == 1:
                        escaped_key = key.replace('"', '\\"')
                        cmd = f"""osascript -e 'tell application "System Events" to keystroke "{escaped_key}"'"""
                    else:
                        if key not in key_codes:
                            valid_keys = ', '.join(key_codes.keys())
                            raise ToolError(
                                f"Invalid key: {key}. Valid keys are: {valid_keys}. "
                                "Please use lowercase letters and replace underscores with hyphens."
                            )
                        cmd = f"""osascript -e 'tell application "System Events" to key code {key_codes[key]}'"""

                # Execute the command
                return await self.shell(cmd)



                #second change
                # if "+" in text:
                #     parts = [part.lower().strip() for part in text.split("+")]
                #     modifiers = []
                #     key = parts[-1]

                #     # Process modifiers
                #     for mod in parts[:-1]:
                #         if mod not in modifier_map:
                #             raise ToolError(f"Invalid modifier key: {mod}. Valid modifiers are: {', '.join(modifier_map.keys())}")
                #         modifiers.append(modifier_map[mod])

                #     modifier_string = ", ".join(modifiers)

                #     if len(key) == 1:
                #         # Escape quotes in the key character
                #         escaped_key = key.replace('"', '\\"')
                #         cmd = f"""osascript -e 'tell application "System Events" to keystroke "{escaped_key}" using {{{modifier_string}}}'"""
                #     else:
                #         # For special keys with modifiers
                #         if key not in key_codes:
                #             raise ToolError(f"Invalid key: {key}. Valid special keys are: {', '.join(key_codes.keys())}")
                #         cmd = f"""osascript -e 'tell application "System Events" to key code {key_codes[key]} using {{{modifier_string}}}'"""
#first change
                # if "+" in text:
                #     parts = [part.lower().strip() for part in text.split("+")]
                #     modifiers = []
                #     key = parts[-1]

                #     # Process modifiers
                #     for mod in parts[:-1]:
                #         if mod not in modifier_map:
                #             raise ToolError(f"Invalid modifier key: {mod}. Valid modifiers are: {', '.join(modifier_map.keys())}")
                #         modifiers.append(modifier_map[mod])

                #     # For single character keys with modifiers
                #     if len(key) == 1:
                #         modifier_string = " down, ".join(modifiers)
                #         cmd = f"""osascript -e '
                #             tell application "System Events"
                #                 key down {{{modifier_string}}}
                #                 keystroke "{key}"
                #                 key up {{{modifier_string}}}
                #             end tell'"""
                #     else:
                #         # For special keys with modifiers
                #         if key not in key_codes:
                #             raise ToolError(f"Invalid key: {key}. Valid special keys are: {', '.join(key_codes.keys())}")
                        
                #         modifier_string = " down, ".join(modifiers)
                #         cmd = f"""osascript -e '
                #             tell application "System Events"
                #                 key down {{{modifier_string}}}
                #                 key code {key_codes[key]}
                #                 key up {{{modifier_string}}}
                #             end tell'"""
                #secoond change
                # else:
                #     # For single special keys without modifiers
                #     if text.lower() not in key_codes:
                #         raise ToolError(
                #             f"Invalid key: {text}. Valid keys are: {', '.join(key_codes.keys())}\n"
                #             f"For combinations, use: ctrl+key, command+key, alt+key, shift+key"
                #         )
                    
                #     cmd = f"""osascript -e '
                #         tell application "System Events"
                #             key code {key_codes[text.lower()]}
                #         end tell'"""

                # return await self.shell(cmd)

            elif action == "type":
                results: list[ToolResult] = []
                for chunk in chunks(text, TYPING_GROUP_SIZE):
                    # Escape quotes and other special characters
                    escaped_chunk = chunk.replace('"', '\\"').replace("'", "'\\''")
                    cmd = f"""osascript -e '
                        tell application "System Events"
                            keystroke "{escaped_chunk}"
                        end tell'"""
                    results.append(await self.shell(cmd, take_screenshot=False))

                screenshot_base64 = (await self.screenshot()).base64_image
                return ToolResult(
                    output="".join(result.output or "" for result in results),
                    error="".join(result.error or "" for result in results),
                    base64_image=screenshot_base64,
                )

        if action in (
            "left_click",
            "right_click",
            "double_click",
            "middle_click",
            "screenshot",
            "cursor_position",
        ):
            if text is not None:
                raise ToolError(f"text is not accepted for {action}")
            if coordinate is not None:
                raise ToolError(f"coordinate is not accepted for {action}")

            if action == "screenshot":
                return await self.screenshot()
            elif action == "cursor_position":
                x, y = pyautogui.position()
                x, y = self.scale_coordinates(
                    ScalingSource.COMPUTER,
                    x,
                    y,
                )
                return ToolResult(output=f"X={x},Y={y}")
            else:
                click_actions = {
                    "left_click": pyautogui.click,
                    "right_click": pyautogui.rightClick,
                    "middle_click": pyautogui.middleClick,
                    "double_click": pyautogui.doubleClick,
                }
                click_actions[action]()
                return ToolResult(output=f"Performed {action}")

        raise ToolError(f"Invalid action: {action}")

    async def screenshot(self):
        output_dir = Path(OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"screenshot_{uuid4().hex}.png"

        screenshot_cmd = f"screencapture -x {path}"
        
        result = await self.shell(screenshot_cmd, take_screenshot=False)
        if self._scaling_enabled:
            x, y = self.scale_coordinates(
                ScalingSource.COMPUTER, self.width, self.height
            )
            await self.shell(
                f"sips -z {y} {x} {path}", take_screenshot=False
            )

        if path.exists():
            return result.replace(
                base64_image=base64.b64encode(path.read_bytes()).decode()
            )
        raise ToolError(f"Failed to take screenshot: {result.error}")

    async def shell(self, command: str, take_screenshot=True) -> ToolResult:
        _, stdout, stderr = await run(command)
        base64_image = None

        if take_screenshot:
            await asyncio.sleep(self._screenshot_delay)
            base64_image = (await self.screenshot()).base64_image

        return ToolResult(output=stdout, error=stderr, base64_image=base64_image)

    def scale_coordinates(self, source: ScalingSource, x: int, y: int):
        if not self._scaling_enabled:
            return x, y
        ratio = self.width / self.height
        target_dimension = None
        for dimension in MAX_SCALING_TARGETS.values():
            if abs(dimension["width"] / dimension["height"] - ratio) < 0.02:
                if dimension["width"] < self.width:
                    target_dimension = dimension
                break
        if target_dimension is None:
            return x, y
        x_scaling_factor = target_dimension["width"] / self.width
        y_scaling_factor = target_dimension["height"] / self.height
        if source == ScalingSource.API:
            if x > self.width or y > self.height:
                raise ToolError(f"Coordinates {x}, {y} are out of bounds")
            return round(x / x_scaling_factor), round(y / y_scaling_factor)
        return round(x * x_scaling_factor), round(y * y_scaling_factor)

