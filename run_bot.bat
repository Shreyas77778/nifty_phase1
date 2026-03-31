#!/bin/bash
echo "🔥 Starting Sector-Sense AI..."
pip install -r requirements.txt --quiet
python3 health_check.py
if [ $? -eq 0 ]; then
    python3 main.py
else
    echo "❌ Health check failed. Fix errors and retry."
fi