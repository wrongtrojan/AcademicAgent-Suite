FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared /app/shared
COPY services/llm_calling /app/services/llm_calling

ENV PYTHONPATH=/app

CMD ["python", "/app/services/llm_calling/worker/main.py"]
