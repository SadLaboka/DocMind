# DocMind

[![codecov](https://codecov.io/github/SadLaboka/DocMind/badge.svg)](https://codecov.io/github/SadLaboka/DocMind)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=SadLaboka_DocMind&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=SadLaboka_DocMind)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)

[![SonarQube Cloud](https://sonarcloud.io/images/project_badges/sonarcloud-dark.svg)](https://sonarcloud.io/summary/new_code?id=SadLaboka_DocMind)

🇬🇧 [Read in English](README.md)

## 📋 Обзор

**DocMind** — это асинхронная система для анализа документов с использованием Large Language Models (LLM).
Проект построен по микросервисной архитектуре: REST API принимает файлы, фоновые воркеры извлекают из них текст, а отдельный консьюмер отправляет его на анализ в нейросети.

Система спроектирована для высокой отказоустойчивости, масштабируемости и строгого разделения ответственности между компонентами.

## ✨ Возможности

- **Асинхронная конвейерная обработка**: Загрузка, извлечение текста и анализ происходят в разных процессах, не блокируя основной API.
- **Поддержка множества форматов**: Извлечение текста из `.txt`, `.docx`, `.xlsx` и `.pdf` (включая таблицы в документах).
- **Дедупликация документов**: Система вычисляет SHA-256 хэш файла. Если такой файл уже обрабатывался, повторный анализ не запускается — результат берётся из базы.
- **Интеграция с LLM (Factory Pattern)**: Поддержка DeepSeek и Gemini. Провайдер выбирается динамически, а сырые ответы маппятся в строгую Pydantic-схему.
- **Надёжная очередь задач**: Использование RabbitMQ с настройкой Dead Letter Queues (DLQ) для автоматического ретрая и обработки упавших задач анализа.
- **Кэширование и Rate Limiting**: Защита API от перегрузок и оптимизация запросов к БД с помощью Redis (кэш статусов пользователей, промптов, blacklist токенов).
- **Безопасность**: JWT-аутентификация (RS256) с механизмом отзыва токенов (blacklist) и хэшированием паролей через Argon2.
- **Версионирование промптов**: Возможность загружать новые версии промптов для LLM через админ-панель с автоматическим кэшированием активной версии.

## 🛠 Технологический стек

### Core & API
<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/python/default.svg" alt="Python" width="32" height="32"/> **Python 3.13**

<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/fastapi/default.svg" alt="FastAPI" width="32" height="32"/> **FastAPI** — REST API, Dependency Injection, Middlewares

- **Pydantic v2** — валидация данных и схемы
- **structlog** — структурированное логирование в JSON

### Базы данных и кэширование
<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/postgresql/default.svg" alt="PostgreSQL" width="32" height="32"/> **PostgreSQL** (SQLAlchemy + asyncpg) — метаданные пользователей и документов

<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/mongodb/default.svg" alt="MongoDB" width="32" height="32"/> **MongoDB** (Beanie) — хранение промптов, сырого текста и результатов анализа

<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/redis/default.svg" alt="Redis" width="32" height="32"/> **Redis** — кэширование промптов, статусов пользователей, rate limiting, token blacklist

### Брокеры сообщений и асинхронные задачи
<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/rabbitmq/default.svg" alt="RabbitMQ" width="32" height="32"/> **RabbitMQ** (Kombu / aio-pika) — брокер очередей

<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/celery/default.svg" alt="Celery" width="32" height="32"/> **Celery** — воркеры для тяжёлого извлечения текста из файлов

- **FastStream** — консьюмеры для асинхронного анализа текста через LLM

### LLM-провайдеры
- **DeepSeek** (через OpenAI SDK)
- **Gemini** (через google-genai)

### Инфраструктура и DevOps
- **Docker & Docker Compose** — оркестрация всех сервисов
- **Poetry** — управление зависимостями
- **Alembic** — миграции PostgreSQL
- **GitHub Actions** — CI/CD, Codecov, SonarCloud
- **pytest** — покрытие API, сервисов и воркеров
