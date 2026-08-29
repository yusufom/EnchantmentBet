.PHONY: help install env mongo mongo-stop backend frontend dev stop build refresh results

BACKEND := backend
FRONTEND := frontend
VENV := $(BACKEND)/.venv
UVICORN := $(VENV)/bin/uvicorn
DATE ?= $(shell date +%Y-%m-%d)
# Optional: SPORT=football or SPORT=basketball. Empty = every enabled sport.
SPORT ?=
SPORT_JSON := $(if $(SPORT),"$(SPORT)",null)

help: ## Show available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: env ## One-time setup: python venv + pip deps + npm deps
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r $(BACKEND)/requirements.txt
	cd $(FRONTEND) && npm install

env: ## Create backend/.env from the example if it doesn't exist
	@test -f $(BACKEND)/.env || (cp $(BACKEND)/.env.example $(BACKEND)/.env && echo "created $(BACKEND)/.env — put your API keys there")

mongo: ## Start MongoDB (launches OrbStack/Docker if needed)
	@docker info >/dev/null 2>&1 || (open -a OrbStack && until docker info >/dev/null 2>&1; do sleep 1; done)
	docker compose up -d mongo

mongo-stop: ## Stop the MongoDB container
	docker compose down

backend: mongo ## Run the FastAPI backend on :8000 (foreground, auto-reload)
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend: ## Run the Next.js frontend on :3000 (foreground)
	cd $(FRONTEND) && npm run dev

dev: mongo ## Run everything: mongo + backend (background) + frontend (foreground)
	cd $(BACKEND) && nohup .venv/bin/uvicorn app.main:app --reload --port 8000 > ../backend.log 2>&1 &
	@until curl -sf http://localhost:8000/api/health >/dev/null; do sleep 1; done
	@echo "backend up on :8000 (logs in backend.log) — starting frontend"
	cd $(FRONTEND) && npm run dev

stop: ## Stop frontend, backend and MongoDB
	-lsof -ti:3000 -sTCP:LISTEN | xargs kill 2>/dev/null
	-lsof -ti:8000 -sTCP:LISTEN | xargs kill 2>/dev/null
	docker compose down

build: ## Production build of the frontend
	cd $(FRONTEND) && npm run build

refresh: ## Generate predictions (make refresh DATE=2026-08-22 SPORT=football)
	curl -s -X POST http://localhost:8000/api/predictions/refresh \
		-H 'Content-Type: application/json' \
		-d '{"date":"$(DATE)","sport":$(SPORT_JSON)}' | head -c 300; echo

results: ## Fetch scores and grade predictions (make results DATE=... SPORT=basketball)
	curl -s -X POST http://localhost:8000/api/results/refresh \
		-H 'Content-Type: application/json' \
		-d '{"date":"$(DATE)","sport":$(SPORT_JSON)}' | head -c 300; echo
