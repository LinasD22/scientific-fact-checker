# Scientific-fact-checker
Fact-Check Plugin is a Chrome-based browser extension designed to help users quickly evaluate the factual reliability of selected text on the web. By simply right-clicking highlighted content, users can request a fact score supported by scientific evidence and trusted sources.

## Usage
Usage with python fast api package added test api endpoint.

Steps to run endpoint:
- Start server:
```shell
fastapi dev app/bin/app.py 
```
- Test endpoint
```shell
curl -X GET 'http://127.0.0.1:8000/test?item_id=123' -H 'Content-Type: application/json' -d '{"name":"foo","size":10}'
```

## Local database usage
1. Add .env file to the database folder

2. Start and run docker (from root folder):
```
docker-compose up -d
```

# Scientific Fact Checker – Setup Guide

Projektas palaiko kelis paleidimo režimus. Pasirinkite pagal poreikį.

---

## Režimų apžvalga

| Režimas | Duomenų bazė | API |
|---|---|---|
| **A** | Serverio (per Cloudflare) | Serverio |
| **B** | Lokalus MariaDB | Lokalus FastAPI |
| **C** | Serverio (per Cloudflare) | Lokalus FastAPI |

---

## Režimas A – Serverio DB + Serverio API

### `scientific-fact-checker/database/.env`
```env
DB_HOST=localhost
DB_PORT=3307
```

### `docker-compose.yml` – įjunkite tik `cf-tunnel-db`
```yaml
services:
  cf-tunnel-db:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    network_mode: host
    env_file:
      - .env
    command: >
      access tcp
      --hostname db.healthfactchecker.site
      --url localhost:3307
      --header "CF-Access-Client-Id: ${CF_CLIENT_ID}"
      --header "CF-Access-Client-Secret: ${CF_CLIENT_SECRET}"
```

### `frontend/background.js`
```js
const API_URL = "https://api.healthfactchecker.site/api/fact-check/search";
```

### `frontend/auth.js`
```js
const url = isLogin
  ? "https://api.healthfactchecker.site/auth/login"
  : "https://api.healthfactchecker.site/auth/register";
```

### Paleidimas
```bash
docker compose up cf-tunnel-db
```

---

## Režimas B – Lokalus DB + Lokalus API

### `scientific-fact-checker/database/.env`
```env
DB_HOST=localhost
DB_PORT=3306
```

### `docker-compose.yml` – įjunkite tik `db`
```yaml
services:
  db:
    image: mariadb:10.11
    restart: always
    environment:
      MYSQL_DATABASE: ${DB_NAME}
      MYSQL_USER: ${DB_USER}
      MYSQL_PASSWORD: ${DB_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
    env_file:
      - .env
    ports:
      - "3306:3306"
    healthcheck:
      test: ["CMD", "mariadb-admin", "ping", "-h", "localhost"]
      interval: 5s
      timeout: 5s
      retries: 5
```

### `frontend/background.js`
```js
const API_URL = "http://localhost:8000/api/fact-check/search";
```

### `frontend/auth.js`
```js
const url = isLogin
  ? "http://localhost:8000/auth/login"
  : "http://localhost:8000/auth/register";
```

### Paleidimas
```bash
docker compose up db
cd backend
uvicorn application:app --host 0.0.0.0 --port 8000 --reload
```

---

## Režimas C – Serverio DB + Lokalus API

### `scientific-fact-checker/database/.env`
```env
DB_HOST=localhost
DB_PORT=3307
```

### `docker-compose.yml` – įjunkite tik `cf-tunnel-db`
```yaml
services:
  cf-tunnel-db:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    network_mode: host
    env_file:
      - .env
    command: >
      access tcp
      --hostname db.healthfactchecker.site
      --url localhost:3307
      --header "CF-Access-Client-Id: ${CF_CLIENT_ID}"
      --header "CF-Access-Client-Secret: ${CF_CLIENT_SECRET}"
```

### `frontend/background.js`
```js
const API_URL = "http://localhost:8000/api/fact-check/search";
```

### `frontend/auth.js`
```js
const url = isLogin
  ? "http://localhost:8000/auth/login"
  : "http://localhost:8000/auth/register";
```

### Paleidimas
```bash
docker compose up cf-tunnel-db
cd backend
uvicorn application:app --host 0.0.0.0 --port 8000 --reload
```



