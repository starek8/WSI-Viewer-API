FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    openslide-tools \
    libopenslide0 \
    libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

COPY app/ /app/

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]