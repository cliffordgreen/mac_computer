# src/agent/__init__.py
"""
Agent module for handling AI interactions and computer control.
"""

from .enhanced_agent import EnhancedComputerAgent
from .mac_shortcuts import MAC_SHORTCUTS, get_shortcut

__all__ = [
    'EnhancedComputerAgent',
    'MAC_SHORTCUTS',
    'get_shortcut',
]