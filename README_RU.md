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

## 🏗 Архитектура

### Диаграмма компонентов

![Диаграмма компонентов](docs/images/component_diagram_ru.svg)

**Поток данных:**
1. Клиент загружает файл через FastAPI
2. FastAPI публикует задачу извлечения в RabbitMQ
3. Celery Worker извлекает текст и сохраняет в MongoDB
4. Worker публикует событие "текст извлечён"
5. FastStream получает событие
6. FastStream извлекает сырой текст из MongoDB
7. FastStream отправляет текст в LLM для анализа
8. LLM возвращает результат анализа
9. FastStream сохраняет анализ в MongoDB
10. FastStream обновляет статус документа в PostgreSQL

### Диаграмма последовательности: Жизненный цикл документа

![Жизненный цикл документа](docs/images/sequence_ru.svg)

## 📊 Поток данных

### Конвейер обработки документов

1. **Загрузка и валидация** (FastAPI)
   - Пользователь загружает файл через `POST /documents`
   - FastAPI валидирует размер файла (макс. 50MB), MIME-тип и имя файла
   - Файл сохраняется во временное хранилище с вычислением SHA-256 хэша
   - Проверка дедупликации: если файл с таким хэшем уже существует, извлечение пропускается

2. **Сохранение метаданных** (PostgreSQL)
   - Сохраняются метаданные документа: имя файла, размер, MIME-тип, хэш, статус
   - Статус: `created` → `queued`

3. **Очередь задач** (RabbitMQ)
   - FastAPI публикует задачу извлечения в RabbitMQ
   - Задача содержит: document_id, temp_path, mime_type, user_id, request_id

4. **Извлечение текста** (Celery Worker)
   - Воркер забирает задачу из очереди
   - Извлекает текст в зависимости от MIME-типа (TXT, DOCX, XLSX, PDF)
   - Сохраняет сырой текст в MongoDB
   - Обновляет статус документа: `extracted`
   - Публикует событие: `documents.text.extracted`

5. **Анализ через LLM** (FastStream Consumer)
   - Консьюмер получает событие из очереди
   - Извлекает сырой текст из MongoDB
   - Получает активный промпт из кэша Redis (или MongoDB)
   - Отправляет текст + промпт в LLM (DeepSeek/Gemini)
   - Парсит JSON-ответ, валидирует структуру
   - Сохраняет результат анализа в MongoDB
   - Обновляет статус документа: `success`

6. **Получение результата** (FastAPI)
   - Пользователь опрашивает `GET /documents/{id}` для проверки статуса
   - Ответ включает: метаданные, сырой текст, результат анализа, версию

### Ключевые архитектурные решения

**Почему PostgreSQL + MongoDB + Redis?**
- **PostgreSQL**: Реляционные данные со строгой схемой (пользователи, метаданные документов, транзакции)
- **MongoDB**: Неструктурированный контент (сырой текст, результаты анализа LLM, промпты) — гибкая схема, большие документы
- **Redis**: Высокопроизводительное кэширование (промпты, статусы пользователей), rate limiting, token blacklist

**Почему Celery + FastStream?**
- **Celery**: Тяжёлые I/O-задачи (извлечение текста из файлов) — проверенное, надёжное решение с поддержкой ретраев
- **FastStream**: Современные асинхронные консьюмеры для анализа через LLM — нативная поддержка async/await, лучшая интеграция с асинхронной кодовой базой

**Почему локальные файлы вместо S3?**
- Текущая реализация использует локальное временное хранилище для простоты
- TODO: Мигрировать на S3/MinIO для stateless-архитектуры и горизонтального масштабирования

## 🚀 Быстрый старт

### Требования
- **Docker & Docker Compose** (v2.0+)
- **Python 3.13** (для локальной разработки)
- **Poetry** (управление зависимостями)
- **Make** (опционально, но рекомендуется)

### Установка и запуск

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/SadLaboka/DocMind.git
   cd DocMind
   ```

2. Настройте переменные окружения:
   ```bash
   cp .env.example .env
   # Отредактируйте .env, укажите API-ключи, учётные данные БД и т.д.
   ```

3. Запустите все сервисы:
   ```bash
   make up
   # Или напрямую: docker compose up -d --build
   ```

4. Приложение будет доступно по адресу `http://localhost:8000`

> [!TIP]
> Первый запуск может занять 2-3 минуты — Docker собирает образы и применяет миграции.

### Документация API

После запуска интерактивная документация API доступна по адресам:
- **Swagger UI (OpenAPI):** `http://localhost:8000/openapi`
- **ReDoc:** `http://localhost:8000/redoc`

---

## ⚡ Полезные команды

| Команда | Описание |
|---------|----------|
| `make up` | Запуск всех сервисов (`docker compose up -d --build`) |
| `make down` | Остановка всех сервисов и удаление томов |
| `make test` | Запуск тестов в изолированном Docker-окружении |
| `make cov` | Запуск тестов с отчётом покрытия |
| `make cov-html` | Открыть интерактивный HTML-отчёт покрытия |
| `make lint` | Запуск pre-commit хуков (ruff, black, mypy) в Docker |
| `make format` | Запуск ruff check + format |
| `make typecheck` | Запуск mypy |
| `make logs` | Просмотр логов приложения |
| `make logs-all` | Просмотр логов всех сервисов |

---

## ⚙️ Переменные окружения

Полный список переменных находится в `.env.example`. Основные переменные по категориям:

### Сервер
| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `SERVER_HOST` | Хост приложения | `127.0.0.1` |
| `SERVER_PORT` | Порт приложения | `8000` |
| `SERVER_RELOAD` | Автоперезагрузка при изменении кода | `true` |

### Базы данных
| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DB_USER` / `DB_PASSWORD` / `DB_NAME` | Учётные данные PostgreSQL | `postgres` / `postgres` / `postgres` |
| `DB_HOST` / `DB_PORT` | Подключение к PostgreSQL | `localhost` / `5432` |
| `MONGO_USERNAME` / `MONGO_PASSWORD` | Учётные данные MongoDB | `root` / `example` |
| `MONGO_HOST` / `MONGO_PORT` / `MONGO_NAME` | Подключение к MongoDB | `127.0.0.1` / `27017` / `DocMind` |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | Подключение к Redis | `localhost` / `6379` / `0` |

### Брокер сообщений
| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASSWORD` | Учётные данные RabbitMQ | `guest` / `guest` |
| `RABBITMQ_HOST` / `RABBITMQ_PORT` | Подключение к RabbitMQ | `127.0.0.1` / `15672` |

### JWT-аутентификация
| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `JWT_ALGORITHM` | Алгоритм подписи | `RS256` |
| `JWT_TIMEDELTA` | Время жизни access-токена (минуты) | `15` |
| `JWT_REFRESH_TIMEDELTA` | Время жизни refresh-токена (дни) | `7` |

### LLM-провайдеры
| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `LLM_DEFAULT_PROVIDER` | Провайдер по умолчанию для анализа | `deepseek` |
| `DEEPSEEK_API_KEY` | API-ключ DeepSeek | — |
| `DEEPSEEK_MODEL` | Название модели DeepSeek | `deepseek-v4-flash` |
| `GEMINI_API_KEY` | API-ключ Google Gemini | — |
| `GEMINI_MODEL` | Название модели Gemini | `gemini-3.1-flash-lite` |

### Rate Limiting
| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `RATE_LIMIT_GLOBAL_LIMIT` / `RATE_LIMIT_GLOBAL_WINDOW` | Глобальный лимит (запросы / секунды) | `60` / `60` |
| `RATE_LIMIT_LOGIN_LIMIT` / `RATE_LIMIT_LOGIN_WINDOW` | Лимит для эндпоинта логина | `5` / `60` |
| `RATE_LIMIT_REGISTER_LIMIT` / `RATE_LIMIT_REGISTER_WINDOW` | Лимит для эндпоинта регистрации | `3` / `60` |
| `RATE_LIMIT_DOCUMENTS_POST_LIMIT` / `..._WINDOW` | Лимит для загрузки документов | `10` / `60` |
| `RATE_LIMIT_DOCUMENTS_GET_LIMIT` / `..._WINDOW` | Лимит для получения списка документов | `20` / `60` |

### Кэширование
| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `CACHE_PROMPT_TTL` | TTL кэша промптов (секунды) | `3600` |
| `CACHE_USER_STATUS_TTL` | TTL кэша статусов пользователей (секунды) | `3600` |

---

## 🧪 Тестирование

Тесты запускаются в изолированном Docker-окружении с отдельной тестовой базой данных:

```bash
make test
```

Сгенерировать отчёт покрытия (XML + вывод в терминал):
```bash
make cov
# Результат: ./coverage/coverage.xml
```

Открыть интерактивный HTML-отчёт покрытия:
```bash
make cov-html
```

> [!NOTE]
> Тестовая база данных автоматически создаётся и удаляется после каждого прогона тестов.

---

## 🔍 Качество кода

Запуск линтеров и проверки типов:
```bash
make lint        # pre-commit хуки в Docker
make format      # ruff check + format
make typecheck   # mypy
```

---

## 🗄 Миграции базы данных

Схема PostgreSQL управляется через **Alembic**.

Создать новую миграцию:
```bash
make migrate-new m="описание_изменений"
# Или: poetry run alembic revision --autogenerate -m "описание_изменений"
```

Применить все ожидающие миграции:
```bash
make migrate-up
# Или: poetry run alembic upgrade head
```

Откатить последнюю миграцию:
```bash
make migrate-down
# Или: poetry run alembic downgrade -1
```

> [!IMPORTANT]
> При запуске через `make up` миграции применяются автоматически через сервис `db-migrate`. Эти команды нужны только при локальной разработке.
