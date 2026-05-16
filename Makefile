.PHONY: up down test lint build scan

up:
    docker compose up -d --build

down:
    docker compose down -v

test:
    cd services/reservation && python -m pytest tests/ -v --cov=src
    cd services/member && npm test

lint:
    hadolint services/reservation/Dockerfile
    hadolint services/member/Dockerfile
    yamllint -d relaxed .

build:
    docker build -t nekocafe/reservation:local services/reservation/
    docker build -t nekocafe/member:local services/member/

scan: build
    trivy image nekocafe/reservation:local --severity HIGH,CRITICAL --exit-code 1
    trivy image nekocafe/member:local --severity HIGH,CRITICAL --exit-code 1
