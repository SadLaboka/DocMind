.PHONY: up down logs migrate-up migrate-down migrate-new

# 🐳 Docker
up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f

# 🗄️ Migrations
migrate-up:
	poetry run alembic upgrade head

migrate-down:
	poetry run alembic downgrade -1

migrate-new:
	poetry run alembic revision --autogenerate -m "$(m)"