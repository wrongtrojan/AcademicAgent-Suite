FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared /app/shared
COPY services/sandbox_inference /app/services/sandbox_inference

ENV PYTHONPATH=/app

CMD ["python", "/app/services/sandbox_inference/worker/main.py"]
