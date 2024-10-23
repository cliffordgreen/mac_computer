# scripts/setup.sh
#!/bin/bash

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Create necessary directories
mkdir -p data/workflows

# Copy example env file
cp .env.example .env

echo "Setup complete. Please edit .env with your settings."