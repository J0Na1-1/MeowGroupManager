FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system bot && adduser --system --ingroup bot bot
COPY pyproject.toml .
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
RUN pip install --no-cache-dir .
USER bot
CMD ["python", "-m", "app.main"]
