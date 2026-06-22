.PHONY: up down logs migrate-up migrate-down migrate-new lint test test-cov

# Docker
up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f --no-log-prefix application

logs-worker:
	docker compose logs -f --no-log-prefix worker

logs-all:
	docker compose logs -f --no-log-prefix

logs-app:
	docker compose logs -f --no-log-prefix application worker seed-prompt stream

# Migrations
migrate-up:
	poetry run alembic upgrade head

migrate-down:
	poetry run alembic downgrade -1

migrate-new:
	poetry run alembic revision --autogenerate -m "$(m)"

migrate-new-local:
	poetry run python scripts/migrate_local.py revision --autogenerate -m "$(m)"

migrate-up-local:
	poetry run python scripts/migrate_local.py upgrade head

# Development
lint:
	docker run --rm -it \
		-v "$(CURDIR):/src" \
		-w "/src" \
		-v "pre-commit-cache:/cache" \
		-v "pip-cache:/root/.cache/pip" \
		-e "PRE_COMMIT_HOME=/cache" \
		-e "PIP_DEFAULT_TIMEOUT=300" \
		-e "PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/" \
		-e "PIP_TRUSTED_HOST=mirrors.aliyun.com" \
		python:3.13 \
		bash -c "apt-get update && apt-get install -y --no-install-recommends git ca-certificates && update-ca-certificates && pip install --no-cache-dir --timeout 300 --retries 5 pre-commit && git config --global --add safe.directory /src && pre-commit run --all-files"
format:
	poetry run ruff check src/ --fix
	poetry run ruff format src/
typecheck:
	poetry run mypy src/

#Tests
test:
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
cov:
	@python -c "import pathlib, os; p = pathlib.Path('coverage'); p.mkdir(exist_ok=True); os.chmod(p, 0o777)"
	docker compose -f docker-compose.test.yml -f docker-compose.cov.yml up --build --abort-on-container-exit
	@echo ""
	@echo "Coverage report: ./coverage/coverage.xml"
cov-html:
	@docker compose -f docker-compose.test.yml -f docker-compose.cov.yml run --rm -e COVERAGE_FILE=/usr/src/app/coverage/.coverage app-test coverage html -d /usr/src/app/coverage/html
	@powershell -Command "if (Test-Path 'coverage\html\index.html') { Start-Process 'coverage\html\index.html' } else { Write-Host 'HTML report not found. Run `make cov` first.'; exit 1 }"
clean-cov:
	@python -c "import shutil, pathlib; [shutil.rmtree(p) for p in ['coverage', '.coverage', 'htmlcov'] if pathlib.Path(p).exists()]"
	@echo "Coverage artifacts cleaned"
