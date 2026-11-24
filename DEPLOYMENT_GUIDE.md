# 🚀 Free Deployment Guide

This project contains a multi-agent AI system running a local LLM (**qwen2.5:3b**) and vector embeddings (**nomic-embed-text**) via Ollama, along with SQLite and Chroma DB.

Because local 3B LLMs require ~**3 GB of RAM**, standard free hosting platforms (like Render or Vercel, which only provide 512 MB RAM) will run out of memory. 

Below are the **two best 100% free ways** to deploy and share this project:

---

## ⚡ Method 1: Instant Public HTTPS Link (Live in 10 Seconds)
*Best for: Showing your jury, teacher, or classmates right now from your laptop without any cloud signups.*

1. **Start the Web App**:
   Double-click `start_web.bat` (or run `python run_ui.py`).
2. **Double-click `share_public.bat`**:
   This runs an instant tunnel that gives you a public HTTPS URL like:
   ```text
   your url is: https://gentle-tiger-42.loca.lt
   ```
3. **Open the Link**:
   Anyone on any phone or laptop in the world can now open that URL and interact with your live LangGraph website!
   *(Note: The first time someone opens the `loca.lt` link, it asks for your public IP as a one-time safety confirmation, which you can see at [loca.lt/mytunnelpassword](https://loca.lt/mytunnelpassword)).*

---

## 🌐 Method 2: Hugging Face Spaces (Permanent 24/7 Cloud Hosting)
*Best for: A permanent cloud website that stays online 24/7 even when your laptop is turned off.*

**Hugging Face Spaces** is the only major provider offering **16 GB of RAM** and 2 vCPUs completely free on their CPU Basic tier, which is more than enough to run Ollama and your FastAPI app.

### Step-by-Step Instructions:

1. **Create an Account**:
   Sign up for free at [huggingface.co](https://huggingface.co/) if you don't already have an account.

2. **Create a New Space**:
   - Go to [huggingface.co/new-space](https://huggingface.co/new-space).
   - Enter a **Space name** (e.g., `customer-complaint-triage`).
   - Select **License**: `MIT` or `Open Rail`.
   - Select **Space SDK**: Click **Docker** -> **Blank**.
   - Select **Space hardware**: `CPU basic • 2 vCPU • 16 GB • Free`.
   - Set visibility to **Public**.
   - Click **Create Space**.

3. **Deploy from your GitHub Repository**:
   - In your newly created Space, click **Files** -> **Clone repository** (or click **Settings** -> **Connect to GitHub**).
   - Alternatively, push your project files directly to the Space's Git URL:
     ```bash
     git remote add space https://huggingface.co/spaces/<your-username>/<your-space-name>
     git push space main
     ```
   - Hugging Face will automatically detect the `Dockerfile` and `start.sh`, install Ollama, pull `qwen2.5:3b` and `nomic-embed-text`, and host the app at:
     `https://<your-username>-<your-space-name>.hf.space`

---

## 🐳 Method 3: Render (Docker Web Service)
If you have a paid Render plan or a cloud provider with at least 3 GB RAM:
1. Create a **New Web Service** on Render.
2. Connect your GitHub repository: `https://github.com/Saiuk-dev/Agentic-Ai-`.
3. Choose **Docker** as the runtime environment.
4. Set the Instance Type to an instance with at least 4 GB RAM.
5. Render will automatically build the `Dockerfile` and launch the app.
