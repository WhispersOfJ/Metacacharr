FROM python:3.13-slim-bookworm

WORKDIR /app

# Unbuffered stdout - print()'s default block-buffering inside a non-tty
# container would otherwise sit in memory and not reach `docker logs -f`
# in time for live per-item progress lines to actually stream.
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY settings_store.py main.py alembic.ini healthcheck.py .
COPY static ./static
COPY core ./core
COPY models ./models
COPY services ./services
COPY migrations ./migrations

EXPOSE 8420

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8420"]
