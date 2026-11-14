# Backend / evaluation shortcuts. Each target is a thin wrapper around a documented command.
# Requires: docker compose services running, uv, and (for eval targets) Ollama.

.PHONY: up test lint eval eval-answers eval-results

up:            ## Start Postgres + LocalStack
	docker compose up -d --wait

test:          ## Backend tests (no Ollama needed)
	cd backend && uv run pytest -q -p no:logging

lint:          ## Ruff + mypy
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app mcp_servers

eval:          ## Retrieval configs A-D on the test split; regenerates evaluation/RESULTS.md (~1 min)
	uv run --project backend python evaluation/run.py --split test

eval-answers:  ## Grounded-answer checks with the local LLM on the test split (~30 min)
	uv run --project backend python evaluation/run.py --answers --split test

eval-results:  ## Rebuild evaluation/RESULTS.md from stored runs without re-running anything
	uv run --project backend python evaluation/run.py --results-only
