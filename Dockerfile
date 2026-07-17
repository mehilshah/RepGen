# Use official lightweight Python image
FROM python:3.12-slim

# Install system dependencies (git is needed for cloning repos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . .

# Install the CLI (dependency-light; no ML stack required).
RUN pip install --no-cache-dir .

# RepGen is a CLI tool; run it directly.
ENTRYPOINT ["repgen"]
CMD ["--help"]
