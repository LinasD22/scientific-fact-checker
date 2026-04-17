FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
COPY database/requirements.txt ./requirements-db.txt
RUN pip install --no-cache-dir -r requirements.txt -r requirements-db.txt

COPY backend/ ./backend
COPY database/ ./database

#CMD ["fastapi", "dev", "application.py", "--host", "0.0.0.0"]