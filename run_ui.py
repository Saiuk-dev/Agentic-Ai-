"""
run_ui.py — One-click launcher for the Customer Complaint Triage Graph Web UI.
Starts the FastAPI server and launches the browser to http://localhost:8000.
"""

import os
import sys
import time
import webbrowser
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
sys.path.insert(0, WEB_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "ta2"))

def check_and_start_ollama():
    """Verify if Ollama daemon is reachable; if not, attempt to start it."""
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/", timeout=2)
        print("  [✓] Ollama server is running on http://127.0.0.1:11434")
    except Exception:
        print("  [!] Ollama not responding. Attempting to start 'ollama serve' in background...")
        try:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)
        except Exception as e:
            print(f"  [!] Note: Please ensure 'ollama serve' is running. Error: {e}")

def main():
    print("=" * 70)
    print("  CUSTOMER COMPLAINT TRIAGE GRAPH — INTERACTIVE WEB INTERFACE")
    print("  Topic 13 | Multi-Agent LangGraph Workflow")
    print("=" * 70)

    check_and_start_ollama()

    port = int(os.environ.get("PORT", 8000))

    import uvicorn
    # Open browser after a slight pause
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{port}")

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    print(f"\n  Starting Web Server on: http://localhost:{port}")
    print("  Press Ctrl+C to stop.\n")
    uvicorn.run("server:app", app_dir=WEB_DIR, host="0.0.0.0", port=port, reload=False)

if __name__ == "__main__":
    main()
