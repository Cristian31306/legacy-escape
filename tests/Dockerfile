FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir pytest requests

COPY . /app

CMD ["pytest", ".", "--junit-xml=/app/test-results/junit.xml", "-v"]
