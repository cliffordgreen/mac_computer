# src/agent/enhanced_agent.py
from typing import Any, Optional, List
import anthropic
from datetime import datetime
import asyncio
import json
from ..tools.computer import MacComputer
from ..tools.results import ToolResult
from ..workflows.manager import WorkflowManager
from ..utils.logger import logger
from .mac_shortcuts import MAC_SHORTCUTS

class EnhancedComputerAgent:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self.computer = MacComputer()
        self.workflow_manager = WorkflowManager()
        
        self.system_prompt = """You are a helpful assistant that can control a Mac computer.
        You have access to the following capabilities:
        
        1. Mouse Control:
        - Move mouse to coordinates
        - Click (left, right, double)
        - Drag and drop
        
        2. Keyboard Control:
        - Type text
        - Press individual keys
        - Use keyboard shortcuts
        
        3. System Control:
        - Take screenshots
        - Launch applications
        - Switch between windows
        
        4. Workflow Management:
        - Record sequences of actions
        - Save workflows for later use
        - Execute saved workflows
        
        Common Mac keyboard shortcuts are available using the format: command+key
        Example: command+c for copy, command+v for paste
        
        Always confirm actions before executing them and provide clear feedback.
        If an action fails, explain why and suggest alternatives."""
        
    async def process_message(
        self, 
        message: str,
        workflow_id: Optional[str] = None
    ) -> ToolResult | str:
        try:
            # Check if this is a workflow command
            if workflow_id:
                return await self.execute_workflow(workflow_id)
            
            if self._is_workflow_command(message):
                return self._handle_workflow_command(message)
            
            # Get Claude's response
            response = await self._get_claude_response(message)
            
            # Parse and execute actions
            actions = self._parse_actions(response)
            results = []
            
            for action in actions:
                # Add delay between actions
                if results:
                    await asyncio.sleep(0.5)
                
                # Execute action
                result = await self.computer(**action)
                results.append(result)
                
                # Record if we're recording a workflow
                if self.workflow_manager.is_recording:
                    self.workflow_manager.add_step(action, result)
                
                # Stop if there's an error
                if result.error:
                    break
            
            return self._combine_results(results) or response
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return ToolResult(error=f"Error: {str(e)}")
    
    async def execute_workflow(self, workflow_id: str) -> ToolResult:
        """Execute a saved workflow"""
        try:
            workflow = self.workflow_manager.load_workflow(workflow_id)
            results = []
            
            for step in workflow.steps:
                result = await self.computer(**step.parameters)
                results.append(result)
                
                if result.error:
                    return ToolResult(
                        error=f"Workflow failed at step {step.action}: {result.error}"
                    )
                
                await asyncio.sleep(step.delay)
            
            # Update workflow statistics
            workflow.success_count += 1
            workflow.last_run = datetime.now()
            self.workflow_manager.update_workflow(workflow)
            
            return self._combine_results(results)
            
        except Exception as e:
            logger.error(f"Error executing workflow: {str(e)}")
            return ToolResult(error=f"Workflow execution failed: {str(e)}")
    
    async def _get_claude_response(self, message: str) -> str:
        """Get response from Claude"""
        response = await self.client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1024,
            system=self.system_prompt,
            messages=[{"role": "user", "content": message}]
        )
        return response.content
    
    def _parse_actions(self, response: str) -> List[dict[str, Any]]:
        """Parse Claude's response into executable actions"""
        actions = []
        
        # Split response into lines
        lines = response.lower().split('\n')
        
        for line in lines:
            # Parse mouse actions
            if 'move mouse' in line or 'move cursor' in line:
                if coords := self._extract_coordinates(line):
                    actions.append({
                        "action": "mouse_move",
                        "x": coords[0],
                        "y": coords[1]
                    })
            
            # Parse click actions
            elif 'click' in line:
                if 'double click' in line:
                    actions.append({"action": "double_click"})
                elif 'right click' in line:
                    actions.append({"action": "right_click"})
                else:
                    actions.append({"action": "click"})
            
            # Parse typing actions
            elif 'type' in line:
                if text := self._extract_text(line):
                    actions.append({
                        "action": "type",
                        "text": text
                    })
            
            # Parse keyboard shortcuts
            elif 'press' in line:
                if keys := self._extract_keys(line):
                    actions.append({
                        "action": "hotkey",
                        "keys": keys
                    })
            
            # Parse screenshot action
            elif 'screenshot' in line:
                actions.append({"action": "screenshot"})
        
        return actions
    
    def _extract_coordinates(self, text: str) -> Optional[tuple[int, int]]:
        """Extract x,y coordinates from text"""
        import re
        if match := re.search(r'(\d+)\s*,\s*(\d+)', text):
            return (int(match.group(1)), int(match.group(2)))
        return None
    
    def _extract_text(self, text: str) -> Optional[str]:
        """Extract text to type from response"""
        import re
        if match := re.search(r'[\'"](.+?)[\'"]', text):
            return match.group(1)
        return None
    
    def _extract_keys(self, text: str) -> Optional[List[str]]:
        """Extract keyboard keys from text"""
        import re
        if match := re.search(r'press\s+(.+?)(?:\s|$)', text):
            keys = match.group(1).split('+')
            return [k.strip() for k in keys]
        return None
    
    def _combine_results(self, results: List[ToolResult]) -> ToolResult:
        """Combine multiple results into one"""
        return ToolResult(
            output="\n".join(r.output for r in results if r.output),
            error="\n".join(r.error for r in results if r.error),
            base64_image=next((r.base64_image for r in reversed(results) 
                             if r.base64_image), None)
        )