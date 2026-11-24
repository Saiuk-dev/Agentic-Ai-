#!/bin/bash
set -e

echo "=================================================="
echo " Starting Ollama background daemon..."
echo "=================================================="
ollama serve &
OLLAMA_PID=$!

echo "Waiting for Ollama API to respond..."
until curl -s http://127.0.0.1:11434/ > /dev/null 2>&1; do
    sleep 1
done
echo "[✓] Ollama is online!"

echo "=================================================="
echo " Pulling models: qwen2.5:3b and nomic-embed-text..."
echo "=================================================="
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
echo "[✓] Models pulled successfully!"

echo "=================================================="
echo " Initializing SQLite profiles & Chroma Vector DB..."
echo "=================================================="
cd /app/ta2
python seed_db.py
python rag_setup.py

APP_PORT="${PORT:-7860}"
echo "=================================================="
echo " Starting FastAPI server on port ${APP_PORT}..."
echo "=================================================="
cd /app/web
exec uvicorn server:app --host 0.0.0.0 --port "${APP_PORT}"
