FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed to build openslide-python and Pillow
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libopenslide-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
