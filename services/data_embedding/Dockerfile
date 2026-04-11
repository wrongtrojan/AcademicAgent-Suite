FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared /app/shared
COPY services/data_embedding /app/services/data_embedding

ENV PYTHONPATH=/app

CMD ["python", "/app/services/data_embedding/worker/main.py"]
