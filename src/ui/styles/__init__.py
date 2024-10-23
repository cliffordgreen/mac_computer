# src/ui/styles/__init__.py
"""
CSS styles and theme configurations for the Streamlit interface.
"""

from pathlib import Path

def load_css() -> str:
    """Load custom CSS styles."""
    css_path = Path(__file__).parent / "main.css"
    with open(css_path) as f:
        return f"<style>{f.read()}</style>"