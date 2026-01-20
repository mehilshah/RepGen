# Use official lightweight Python image
FROM python:3.12-slim

# Install system dependencies (git is needed for cloning repos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install the package
RUN pip install --no-cache-dir .

EXPOSE 8000

# Run API Server by default
CMD ["uvicorn", "repgen.server:app", "--host", "0.0.0.0", "--port", "8000"]