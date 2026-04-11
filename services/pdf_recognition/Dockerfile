FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared /app/shared
COPY services/pdf_recognition /app/services/pdf_recognition

ENV PYTHONPATH=/app

CMD ["python", "/app/services/pdf_recognition/worker/main.py"]
