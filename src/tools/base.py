from abc import ABC, abstractmethod
from typing import Any

class BaseTool(ABC):
    @abstractmethod
    async def __call__(self, **kwargs) -> Any:
        pass