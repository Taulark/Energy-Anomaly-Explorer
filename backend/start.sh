#!/bin/bash
# Start FastAPI backend server

cd "$(dirname "$0")"
export NSRDB_API_KEY="${NSRDB_API_KEY:-}"
export NSRDB_EMAIL="${NSRDB_EMAIL:-}"

echo "Starting Energy Anomaly Explorer API..."
echo "API will be available at http://localhost:8000"
echo "API docs at http://localhost:8000/docs"

python main.py
