FROM python:3.12-slim

# tzdata so ZoneInfo('Europe/Prague') resolves and DST is correct.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Unbuffered stdout so logs stream to `docker logs` in real time.
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "app.main"]
