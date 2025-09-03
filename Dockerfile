FROM python:3.11-slim

WORKDIR /app

# Install only system dependencies needed by openslide
RUN apt-get update && apt-get install -y \
    libopenslide0 \
    openslide-tools \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]