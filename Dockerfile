FROM python:3.12-slim

# #Install system dependencies for MariaDB/MySQL
# RUN apt-get update && apt-get install -y \
#     gcc \
#     python3-dev \
#     default-libmysqlclient-dev \
#     pkg-config \
#     && rm -rf /var/lib/apt/lists/*

# WORKDIR /app

# #Install Python dependencies
# COPY database/requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# COPY backend/ .

WORKDIR /app

# 1. Copy the dedicated requirements from the root or backend
COPY database/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy the FastAPI logic
COPY backend/ ./backend

# 3. Copy the Django models/UI logic 
# This allows FastAPI to import or reference the Django structure if needed
COPY database/ ./database

# 4. Set the working directory to where your main script is
WORKDIR /app/backend

CMD ["fastapi", "dev", "application.py", "--host", "0.0.0.0"]

# Start the server
#CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app_root.wsgi:application"]