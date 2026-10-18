SHELL := /bin/bash

PYTHON ?= python3
UVICORN ?= uvicorn

ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: \
	install \
	install-dev \
	frontend-install \
	frontend \
	bootstrap \
	db-up \
	db-wait \
	db-down \
	db-reset \
	db-status \
	db-init \
	db-verify \
	ingest \
	index \
	index-force \
	api \
	api-dev \
	test \
	lint \
	format \
	typecheck \
	quality \
	benchmark \
	recall \
	article-recall \
	demo \
	environment \
	ef-search \
	hybrid-index \
	clean

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

frontend-install:
	cd frontend && npm ci

frontend:
	cd frontend && npm run dev

bootstrap:
	@test -f .env || cp .env.example .env
	@test -f frontend/.env || cp frontend/.env.example frontend/.env
	$(MAKE) install-dev
	$(MAKE) frontend-install
	$(MAKE) db-up
	$(MAKE) db-wait
	$(MAKE) db-init
	$(MAKE) db-verify
	$(MAKE) ingest
	$(MAKE) index


db-up:
	docker compose up -d mariadb


db-wait:
	@echo "Waiting for MariaDB..."
	@for attempt in {1..30}; do \
		if docker compose exec -T mariadb \
			mariadb-admin ping \
			-u"$(DB_USER)" \
			-p"$(DB_PASSWORD)" \
			--silent >/dev/null 2>&1; then \
			echo "MariaDB is ready."; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "MariaDB did not become ready in time." >&2; \
	exit 1


db-down:
	docker compose down


db-reset:
	docker compose down -v
	docker compose up -d mariadb
	$(MAKE) db-wait


db-status:
	docker compose ps


db-init:
	docker compose exec -T mariadb \
		mariadb \
		-u"$(DB_USER)" \
		-p"$(DB_PASSWORD)" \
		"$(DB_NAME)" \
		< database/schema/001_schema.sql

	docker compose exec -T mariadb \
		mariadb \
		-u"$(DB_USER)" \
		-p"$(DB_PASSWORD)" \
		"$(DB_NAME)" \
		< database/schema/002_vector_index.sql


db-verify:
	$(PYTHON) -m scripts.verify_database


ingest:
	$(PYTHON) -m scripts.ingest \
		--category "Machine learning" \
		--limit 300 \
		--concurrency 5


index:
	$(PYTHON) -m scripts.build_embeddings


index-force:
	$(PYTHON) -m scripts.build_embeddings --force


api:
	$(UVICORN) backend.app.main:app \
		--host 127.0.0.1 \
		--port 8000


api-dev:
	$(UVICORN) backend.app.main:app \
		--host 127.0.0.1 \
		--port 8000 \
		--reload


test:
	$(PYTHON) -m pytest -v


lint:
	ruff check backend scripts tests experiments


format:
	ruff format backend scripts tests experiments


typecheck:
	mypy backend scripts experiments tests


quality:
	ruff check backend scripts tests experiments
	ruff format --check backend scripts tests experiments
	mypy backend scripts experiments tests
	$(PYTHON) -m pytest -v


benchmark:
	$(PYTHON) -m experiments.search_strategies \
		--query "neural network training" \
		--category "Machine learning" \
		--source-title "Machine learning" \
		--limit 5 \
		--warmups 5 \
		--runs 50

	$(PYTHON) -m experiments.index_vs_bruteforce \
		"neural network training" \
		--limit 5 \
		--runs 50 \
		--warmup-runs 5


recall:
	$(PYTHON) -m experiments.recall


article-recall:
	$(PYTHON) -m experiments.article_recall


demo:
	$(PYTHON) -m scripts.demo


environment:
	$(PYTHON) -m experiments.environment


ef-search:
	$(PYTHON) -m experiments.vector_ef_search \
		--repeats 3 \
		--warmup-rounds 1


hybrid-index:
	$(PYTHON) -m experiments.hybrid_index_probe \
		--query "neural network training" \
		--category "Machine learning" \
		--limit 5 \
		--warmups 5 \
		--runs 50


clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
