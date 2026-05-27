# Raspberry Pi Deploy API

Small FastAPI service for deploying allowlisted Docker Compose projects on a Raspberry Pi.

It is designed to run behind Cloudflare Tunnel. Bind Uvicorn to `127.0.0.1`, expose only the tunnel, and call the API from your CI/CD pipeline with a Bearer token.

## Structure

```text
deploy-api/
  main.py
  config.py
  deployer.py
  projects.json
  pyproject.toml
  .env.example
  README.md
  deploy-api.service
```

## Setup

```bash
cd /home/pi/deploy-api
poetry install
cp .env.example .env
nano .env
```

Set a strong token:

```bash
openssl rand -hex 32
```

Then edit `projects.json` and add your projects:

```json
{
  "my-app": {
    "path": "/home/pi/projects/my-app",
    "branch": "main",
    "compose_command": ["docker", "compose"]
  }
}
```

If a project already has a deploy script, use `deploy_command`:

```json
{
  "my-app": {
    "path": "/home/pi/projects/my-app",
    "deploy_command": ["bash", "./start.sh"]
  }
}
```

`deploy_command` runs from the configured project directory. When it is set, the API runs only that command and skips the default git and Docker Compose steps.

Only projects in this file can be deployed. After changing it, restart the API:

```bash
./server.sh restart
```

By default the API reads `projects.json` from this directory. To use another file:

```bash
PROJECTS_FILE=/path/to/projects.json ./server.sh start
```

## Run locally

```bash
poetry run uvicorn main:app --host 127.0.0.1 --port 18765
```

## Install systemd service

Copy `deploy-api.service` to systemd and enable it:

```bash
sudo cp deploy-api.service /etc/systemd/system/deploy-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now deploy-api
sudo systemctl status deploy-api
```

View logs:

```bash
journalctl -u deploy-api -f
```

## Trigger a deploy

```bash
curl -X POST "https://deploy.example.com/deploy/my-app" \
  -H "Authorization: Bearer YOUR_DEPLOY_TOKEN"
```

List configured projects:

```bash
curl "https://deploy.example.com/projects" \
  -H "Authorization: Bearer YOUR_DEPLOY_TOKEN"
```

## Deploy behavior

For the selected project, the API runs `deploy_command` when it is configured.
Otherwise, it runs:

```bash
git fetch origin <branch>
git checkout <branch>
git pull --ff-only origin <branch>
docker compose down
docker compose up -d --build
```

Commands are executed with `subprocess.run(..., shell=False)` from the configured project directory.

## Cloudflare Tunnel

Point your Cloudflare Tunnel service to:

```text
http://127.0.0.1:18765
```

Keep the API bound to localhost on the Pi. The project code does not need the deploy token; only this deploy API reads `.env`.
