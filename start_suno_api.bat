@echo off
cd /d f:\AI_DRAMA_FACTORY\suno-api
echo [INFO] Starting suno-api via Docker Compose (Node LTS)...
echo [INFO] First run will build the image, may take 3-5 minutes.
docker compose up --build

