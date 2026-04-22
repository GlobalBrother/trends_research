#!/usr/bin/env bash
set -e
PROJECT_DIR='/mnt/c/Users/MarianCraciun/OneDrive - Global Brother SRL/Documents/GitHub/trends_research'
VENV="$HOME/trends_venv"

if [ ! -d "$VENV" ]; then
    python3.13 -m venv "$VENV"
fi
source "$VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet pandas numpy vaderSentiment pytest python-dotenv

cd "$PROJECT_DIR"
python -m pytest tests/test_analytics_engine.py -v

