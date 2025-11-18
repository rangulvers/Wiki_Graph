#!/bin/bash

# Activate virtual environment
source .venv/bin/activate

# Start Flask server
uvicorn app.main:app --reload
