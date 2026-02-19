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