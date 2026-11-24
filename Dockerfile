FROM python:3.11-slim

# Prevent python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=7860 \
    OLLAMA_HOST=0.0.0.0:11434

# Install system dependencies, curl, git, and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    sqlite3 \
    procps \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama binary
RUN curl -fsSL https://ollama.com/install.sh | sh

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY ta2/requirements.txt /app/ta2/requirements.txt
RUN pip install --no-cache-dir -r /app/ta2/requirements.txt

# Copy all application files
COPY . /app

# Ensure shell scripts have Unix line endings and execute permissions
RUN chmod +x /app/start.sh

# Expose default web port (7860 for Hugging Face Spaces, or dynamic $PORT)
EXPOSE 7860

# Run entrypoint script
CMD ["/app/start.sh"]
