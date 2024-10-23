# src/workflows/manager.py
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
from pathlib import Path
import uuid
from .models import Workflow, WorkflowStep
from ..tools.results import ToolResult
from ..utils.logger import logger

class WorkflowManager:
    def __init__(self, storage_dir: str = "data/workflows"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.current_recording: List[WorkflowStep] = []
        self.is_recording = False
    
    def start_recording(self) -> None:
        """Start recording a new workflow"""
        self.current_recording = []
        self.is_recording = True
        logger.info("Started recording new workflow")
    
    def stop_recording(self) -> None:
        """Stop recording the current workflow"""
        self.is_recording = False
        logger.info(f"Stopped recording workflow with {len(self.current_recording)} steps")
    
    def add_step(
        self,
        action: Dict[str, Any],
        result: Optional[ToolResult] = None
    ) -> None:
        """Add a step to the current recording"""
        if self.is_recording:
            step = WorkflowStep(
                action=action["action"],
                parameters={k: v for k, v in action.items() if k != "action"},
                result=result.__dict__ if result else None
            )
            self.current_recording.append(step)
            logger.debug(f"Added step: {step.action}")
    
    def save_workflow(
        self,
        name: str,
        description: str,
        tags: List[str] = None
    ) -> str:
        """Save the current recording as a workflow"""
        if not self.is_recording or not self.current_recording:
            raise ValueError("No workflow is being recorded")
        
        workflow = Workflow(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            steps=self.current_recording,
            created_at=datetime.now(),
            tags=tags or []
        )
        
        # Save to file
        workflow_path = self.storage_dir / f"{workflow.id}.json"
        with open(workflow_path, "w") as f:
            json.dump(workflow.dict(), f, indent=2, default=str)
        
        logger.info(f"Saved workflow {workflow.id}: {name}")
        self.stop_recording()
        return workflow.id
    
    def load_workflow(self, workflow_id: str) -> Workflow:
        """Load a workflow from storage"""
        workflow_path = self.storage_dir / f"{workflow_id}.json"
        if not workflow_path.exists():
            raise ValueError(f"Workflow {workflow_id} not found")
        
        with open(workflow_path, "r") as f:
            data = json.load(f)
            return Workflow.parse_obj(data)
    
    def update_workflow(self, workflow: Workflow) -> None:
        """Update a workflow in storage"""
        workflow_path = self.storage_dir / f"{workflow.id}.json"
        with open(workflow_path, "w") as f:
            json.dump(workflow.dict(), f, indent=2, default=str)
        logger.info(f"Updated workflow {workflow.id}")
    
    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow from storage"""
        workflow_path = self.storage_dir / f"{workflow_id}.json"
        if workflow_path.exists():
            workflow_path.unlink()
            logger.info(f"Deleted workflow {workflow_id}")
            return True
        return False
    
    def list_workflows(self, tag: Optional[str] = None) -> List[Workflow]:
        """List all saved workflows, optionally filtered by tag"""
        workflows = []
        for file in self.storage_dir.glob("*.json"):
            with open(file, "r") as f:
                data = json.load(f)
                workflow = Workflow.parse_obj(data)
                if tag is None or tag in workflow.tags:
                    workflows.append(workflow)
        return sorted(workflows, key=lambda w: w.created_at, reverse=True)
    
    def get_all_tags(self) -> List[str]:
        """Get all unique tags across all workflows"""
        tags = set()
        for workflow in self.list_workflows():
            tags.update(workflow.tags)
        return sorted(list(tags))