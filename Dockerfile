FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

WORKDIR /app
COPY requirements.txt requirements-web.txt ./
RUN pip install -r requirements-web.txt
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY web/ ./web/

RUN useradd --create-home --uid 1000 appuser
USER appuser
EXPOSE 7860
CMD ["gunicorn", "--chdir", "scripts", "web_server:app", "--bind", "0.0.0.0:7860", "--workers", "1", "--threads", "8", "--timeout", "120"]
