.PHONY: up down logs migrate-up migrate-down migrate-new lint test test-cov

# Docker
up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f --no-log-prefix application

# Migrations
migrate-up:
	poetry run alembic upgrade head

migrate-down:
	poetry run alembic downgrade -1

migrate-new:
	poetry run alembic revision --autogenerate -m "$(m)"

# Development
lint:
	docker run --rm -it \
		-v "$(CURDIR):/src" \
		-w "/src" \
		-v "pre-commit-cache:/cache" \
		-e "PRE_COMMIT_HOME=/cache" \
		python:3.13-slim \
		bash -c "apt-get update && apt-get install -y --no-install-recommends git && pip install --no-cache-dir pre-commit && git config --global --add safe.directory /src && pre-commit run --all-files"
format:
	poetry run ruff check src/ --fix
	poetry run ruff format src/
typecheck:
	poetry run mypy src/

#Tests
test:
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
cov:
	@python -c "import pathlib; pathlib.Path('coverage').mkdir(exist_ok=True)"
	docker compose -f docker-compose.test.yml -f docker-compose.cov.yml up --build --abort-on-container-exit
	@echo ""
	@echo "Coverage report: ./coverage/coverage.xml"
clean-cov:
	@python -c "import shutil, pathlib; [shutil.rmtree(p) for p in ['coverage', '.coverage', 'htmlcov'] if pathlib.Path(p).exists()]"
	@echo "Coverage artifacts cleaned"
