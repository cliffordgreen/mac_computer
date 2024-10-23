# src/agent/mac_shortcuts.py
from typing import Dict, List

MAC_SHORTCUTS: Dict[str, List[str]] = {
    # Text editing
    "copy": ["command", "c"],
    "paste": ["command", "v"],
    "cut": ["command", "x"],
    "undo": ["command", "z"],
    "redo": ["command", "shift", "z"],
    "select_all": ["command", "a"],
    "save": ["command", "s"],
    "save_as": ["command", "shift", "s"],
    
    # Navigation
    "spotlight": ["command", "space"],
    "switch_app": ["command", "tab"],
    "mission_control": ["control", "up"],
    "app_windows": ["control", "down"],
    "next_tab": ["command", "shift", "]"],
    "previous_tab": ["command", "shift", "["],
    
    # Window management
    "new_window": ["command", "n"],
    "close_window": ["command", "w"],
    "minimize": ["command", "m"],
    "quit_app": ["command", "q"],
    
    # Browser specific
    "new_tab": ["command", "t"],
    "reload": ["command", "r"],
    "hard_reload": ["command", "shift", "r"],
    "private_window": ["command", "shift", "n"],
    
    # System
    "screenshot": ["command", "shift", "3"],
    "screenshot_selection": ["command", "shift", "4"],
    "lock_screen": ["command", "control", "q"],
    "force_quit": ["command", "option", "escape"],
}

def get_shortcut(name: str) -> List[str]:
    """Get the key combination for a named shortcut"""
    return MAC_SHORTCUTS.get(name, [])

def is_valid_shortcut(name: str) -> bool:
    """Check if a shortcut name is valid"""
    return name in MAC_SHORTCUTS

def get_all_shortcuts() -> Dict[str, List[str]]:
    """Get all available shortcuts"""
    return MAC_SHORTCUTS

def get_shortcut_categories() -> Dict[str, List[str]]:
    """Get shortcuts organized by category"""
    return {
        "Text Editing": ["copy", "paste", "cut", "undo", "redo", "select_all", "save"],
        "Navigation": ["spotlight", "switch_app", "mission_control", "app_windows"],
        "Window Management": ["new_window", "close_window", "minimize", "quit_app"],
        "Browser": ["new_tab", "reload", "hard_reload", "private_window"],
        "System": ["screenshot", "screenshot_selection", "lock_screen", "force_quit"]
    }