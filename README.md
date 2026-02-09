# CUI-IP-ID
Intellectual property ID tool. the following is a work in progress, and non-demo version is kept private, for now.

***Prior to running, make sure you have Docker installed and running in your computer.***

## How to run it
### 1. Open terminal (shell) (In Mac: search "Terminal") and navigate to the folder where this repo resides (replace the /path/to/repository/ with real path):
```bash 
cd /path/to/repository/CUI-IP-ID
```

ONLY for your first run (or after image changes), then do:

```bash 
docker build -t cui-ip-id .
```
### 2. From that folder now paste this and click enter:

```bash 
docker run --rm -p 8501:8501 --env-file .env cui-ip-id
```

### 3. Open the following [link in your browser (Google Chrome)](http://localhost:8501)

- Interact with the app!

## Quick demo (no LLM)

### 1. Same as above

### 2. From that folder now paste this and click enter:

```bash

docker build -t cui-ip-id .

docker run --rm -p 8501:8501 --env-file .env cui-ip-id

```
### 3. Open the following [link in your browser (Google Chrome)](http://localhost:8501)