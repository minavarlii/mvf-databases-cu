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
	ground-truth-latency \
	m-ground-truth \
	vector-lifecycle \
	multi-mode-latency \
	vector-concurrency \
	prebuilt-export \
	prebuilt-restore \
	offline-bootstrap \
	sql-demo \
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
	@if docker ps -a --format '{{.Names}}' | grep -qx 'mvf-mariadb'; then \
		echo "Reusing existing mvf-mariadb container"; \
		docker start mvf-mariadb >/dev/null 2>&1 || true; \
	else \
		docker compose up -d mariadb; \
	fi


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


ground-truth-latency:
	$(PYTHON) -m experiments.ground_truth_latency \
		--passes 5 \
		--warmup-passes 1


m-ground-truth:
	$(PYTHON) -m experiments.vector_index_m_ground_truth \
		--measured-passes 3


vector-lifecycle:
	$(PYTHON) -m experiments.vector_lifecycle


multi-mode-latency:
	$(PYTHON) -m experiments.multi_mode_latency \
		--passes 5 \
		--warmup-passes 1


vector-concurrency:
	$(PYTHON) -m experiments.vector_concurrency \
		--writers 2 \
		--rows-per-writer 25 \
		--queries 50


prebuilt-export:
	$(PYTHON) -m scripts.export_prebuilt \
		--output data/prebuilt/mvf_corpus.json.gz


prebuilt-restore:
	@test -f data/prebuilt/mvf_corpus.json.gz || \
		(echo "Missing data/prebuilt/mvf_corpus.json.gz; run make prebuilt-export first." >&2; exit 1)
	$(PYTHON) -m scripts.restore_prebuilt \
		--input data/prebuilt/mvf_corpus.json.gz


offline-bootstrap:
	@test -f .env || cp .env.example .env
	$(MAKE) install-dev
	$(MAKE) db-up
	$(MAKE) db-wait
	$(MAKE) db-init
	$(MAKE) prebuilt-restore
	$(MAKE) db-verify


sql-demo:
	$(MAKE) offline-bootstrap
	docker compose exec -T mariadb \
		mariadb \
		-u"$(DB_USER)" \
		-p"$(DB_PASSWORD)" \
		"$(DB_NAME)" \
		< sql/examples.sql


clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
