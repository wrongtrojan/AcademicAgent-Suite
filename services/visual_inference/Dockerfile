FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared /app/shared
COPY services/visual_inference /app/services/visual_inference

ENV PYTHONPATH=/app

CMD ["python", "/app/services/visual_inference/worker/main.py"]
