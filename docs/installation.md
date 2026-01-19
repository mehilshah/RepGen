# Installation

## Prerequisites
- **Python**: 3.8 or higher
- **Git**

## Option A: Virtual Environment (Recommended)

To avoid conflicts with system packages, we recommend installing in a virtual environment.

```bash
# 1. Create a virtual environment
python3 -m venv venv

# 2. Activate it
# On Mac/Linux:
source venv/bin/activate
# On Windows:
# .\venv\Scripts\activate

# 3. Install RepGen
git clone https://github.com/mehilshah/RepGen
cd RepGen
pip install -e .
```

## Option B: Docker

Run the entire stack in an isolated container.

```bash
docker build -t repgen .
docker run -p 8000:8000 repgen
```
