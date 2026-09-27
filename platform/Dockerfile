FROM python:3.14.7-slim-trixie
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home platform
RUN mkdir -p /var/lib/platform-monitoring && chown 10001:10001 /var/lib/platform-monitoring
COPY app ./app
USER 10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
