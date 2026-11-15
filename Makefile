# Backend / evaluation shortcuts. Each target is a thin wrapper around a documented command.
# Requires: docker compose services running, uv, and (for eval targets) Ollama.

.PHONY: up test lint eval eval-answers eval-extra eval-results validate-data demo seed demo-down frontend-check

up:            ## Start Postgres + LocalStack
	docker compose up -d --wait

test:          ## Backend tests (no Ollama needed)
	cd backend && uv run pytest -q -p no:logging

lint:          ## Ruff + mypy
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app mcp_servers

eval:          ## Retrieval configs A-F on the test split; regenerates evaluation/RESULTS.md (~2 min)
	uv run --project backend python evaluation/run.py --split test

eval-answers:  ## Grounded answers + LLM faithfulness judge on the test split (~2 h on a laptop)
	uv run --project backend python evaluation/run.py --answers --split test

eval-results:  ## Rebuild evaluation/RESULTS.md from stored runs without re-running anything
	uv run --project backend python evaluation/run.py --results-only

demo:          ## Whole app in containers: infra, API, worker, MCP servers, frontend, demo seed
	docker compose --profile app up -d --build

seed:          ## Re-seed the demo workspace (the synthetic incident is relative to "now")
	docker compose --profile app run --rm seed

demo-down:     ## Stop the container stack (data kept; add -v manually to delete it)
	docker compose --profile app down

frontend-check: ## Frontend type check, lint, unit tests and production build (same as CI)
	cd frontend && npx tsc --noEmit && npm run lint && npm test && npm run build

eval-extra:    ## Tool-selection accuracy + prompt-injection resistance with the local LLM (~10 min)
	uv run --project backend python evaluation/run.py --extra

validate-data: ## Check every dataset label against the corpus
	python3 evaluation/datasets/validate.py v1; python3 evaluation/datasets/validate.py v2
