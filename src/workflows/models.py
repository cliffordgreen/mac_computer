# src/workflows/models.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class WorkflowStep(BaseModel):
    action: str
    parameters: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    delay: float = Field(default=0.5, ge=0)
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class Workflow(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    steps: List[WorkflowStep]
    created_at: datetime = Field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    success_count: int = Field(default=0, ge=0)
    tags: List[str] = Field(default_factory=list)
    version: str = "1.0"
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
    def add_step(self, step: WorkflowStep) -> None:
        self.steps.append(step)
        
    def clear_steps(self) -> None:
        self.steps = []