FROM python:3.12-slim

#Install system dependencies for MariaDB/MySQL
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

#Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Start the server
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app_root.wsgi:application"]