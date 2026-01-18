# Use official lightweight Python image
FROM python:3.10-slim

# Install system dependencies (git is needed for cloning repos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install the package
RUN pip install --no-cache-dir .

# Default command
ENTRYPOINT ["repgen"]
CMD ["--help"]
