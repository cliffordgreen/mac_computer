from dataclasses import dataclass
from typing import Optional

@dataclass
class ToolResult:
    output: Optional[str] = None
    error: Optional[str] = None
    base64_image: Optional[str] = None
    system: Optional[str] = None