FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only application code (see .dockerignore)
COPY main.py config.yaml ./
COPY notbook_ai ./notbook_ai
COPY evals ./evals

# Non-root
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080
CMD ["python", "main.py"]
