FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared /app/shared
COPY services/mixture_searching /app/services/mixture_searching

ENV PYTHONPATH=/app

CMD ["python", "/app/services/mixture_searching/worker/main.py"]
