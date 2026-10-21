FROM python:3.14.7-slim-trixie
WORKDIR /fixture
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home fixture
COPY fixture.py .
USER 10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "fixture.py"]
