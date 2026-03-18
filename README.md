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

## Database usage
1. Install the Essentials:
  - Docker Desktop: Download and install it. Make sure it is running.
  - Cloudflare Tunnel: Download the .msi installer 

2. Add .env file to the database folder

3. Activate the Tunnel
- Open terminal as an Administrator and run this:
```
cloudflared.exe service install SECRET_TOKEN_HERE
```

4. Launch the Application
Open a terminal, navigate into the project folder and run:
```
docker-compose up -d
```
5. Final Verification
- Site should be access using localhost:8000 and healthfactchecker.site
Use /admin to see database information


