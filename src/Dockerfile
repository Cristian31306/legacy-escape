FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn psycopg2-binary

COPY . /app/src

ENV PYTHONPATH=/app
ENV LOG_DIR=/app/logs
ENV RESILIENCE_DB=/app/data/resilience.db

RUN mkdir -p /app/logs /app/data

EXPOSE 8082

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8082"]
