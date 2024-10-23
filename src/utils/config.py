import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    WORKFLOWS_DIR = os.getenv("WORKFLOWS_DIR", "data/workflows")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"