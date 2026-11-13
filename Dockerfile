FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p uploads outputs
EXPOSE 5000
CMD ["sh", "-c", "gunicorn --workers 1 --threads 8 --timeout 180 --bind 0.0.0.0:${PORT:-5000} app:app"]
