# DocMind

[![codecov](https://codecov.io/github/SadLaboka/DocMind/badge.svg)](https://codecov.io/github/SadLaboka/DocMind)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=SadLaboka_DocMind&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=SadLaboka_DocMind)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)

[![SonarQube Cloud](https://sonarcloud.io/images/project_badges/sonarcloud-dark.svg)](https://sonarcloud.io/summary/new_code?id=SadLaboka_DocMind)

🇷🇺 [Читать на русском](README_RU.md)

## 📋 Overview

**DocMind** is an asynchronous document analysis system using Large Language Models (LLM).
The project is built on a microservices architecture: REST API accepts files, background workers extract text from them, and a separate consumer sends it for analysis to neural networks.

The system is designed for high fault tolerance, scalability, and strict separation of responsibilities between components.

## ✨ Features

- **Asynchronous pipeline processing**: Upload, text extraction, and analysis occur in separate processes without blocking the main API.
- **Multiple format support**: Text extraction from `.txt`, `.docx`, `.xlsx`, and `.pdf` (including tables in documents).
- **Document deduplication**: The system calculates the SHA-256 hash of the file. If such a file has already been processed, re-analysis is not launched — the result is taken from the database.
- **LLM integration (Factory Pattern)**: Support for DeepSeek and Gemini. The provider is selected dynamically, and raw responses are mapped to a strict Pydantic schema.
- **Reliable task queue**: Using RabbitMQ with Dead Letter Queues (DLQ) configuration for automatic retry and handling of failed analysis tasks.
- **Caching and Rate Limiting**: API protection from overloads and optimization of database queries using Redis (user status cache, prompts, token blacklist).
- **Security**: JWT authentication (RS256) with token revocation mechanism (blacklist) and password hashing via Argon2.
- **Prompt versioning**: Ability to upload new prompt versions for LLM via admin panel with automatic caching of the active version.

## 🛠 Tech Stack

### Core & API
<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/python/default.svg" alt="Python" width="32" height="32"/> **Python 3.13**

<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/fastapi/default.svg" alt="FastAPI" width="32" height="32"/> **FastAPI** — REST API, Dependency Injection, Middlewares

- **Pydantic v2** — data validation and schemas
- **structlog** — structured JSON logging

### Databases & Caching
<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/postgresql/default.svg" alt="PostgreSQL" width="32" height="32"/> **PostgreSQL** (SQLAlchemy + asyncpg) — user and document metadata

<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/mongodb/default.svg" alt="MongoDB" width="32" height="32"/> **MongoDB** (Beanie) — storage of prompts, raw text, and analysis results

<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/redis/default.svg" alt="Redis" width="32" height="32"/> **Redis** — prompt caching, user statuses, rate limiting, token blacklist

### Message Brokers & Async Tasks
<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/rabbitmq/default.svg" alt="RabbitMQ" width="32" height="32"/> **RabbitMQ** (Kombu / aio-pika) — message broker

<img src="https://cdn.jsdelivr.net/gh/glincker/thesvg@main/public/icons/celery/default.svg" alt="Celery" width="32" height="32"/> **Celery** — workers for heavy text extraction from files

- **FastStream** — consumers for asynchronous text analysis via LLM

### LLM Providers
- **DeepSeek** (via OpenAI SDK)
- **Gemini** (via google-genai)

### Infrastructure & DevOps
- **Docker & Docker Compose** — orchestration of all services
- **Poetry** — dependency management
- **Alembic** — PostgreSQL migrations
- **GitHub Actions** — CI/CD, Codecov, SonarCloud
- **pytest** — coverage for API, services, and workers

## 🏗 Architecture

### Component Diagram
![Component Diagram](docs/images/component_diagram.svg)

**Flow:**
1. Client uploads file via FastAPI
2. FastAPI publishes extraction task to RabbitMQ
3. Celery Worker extracts text and saves to MongoDB
4. Worker publishes "text extracted" event
5. FastStream consumes the event
6. FastStream retrieves raw text from MongoDB
7. FastStream sends text to LLM for analysis
8. LLM returns analysis result
9. FastStream saves analysis to MongoDB
10. FastStream updates document status in PostgreSQL

### Sequence Diagram: Document Lifecycle

![Document Lifecycle](docs/images/sequence.svg)

## 📊 Data Flow

### Document Processing Pipeline

1. **Upload & Validation** (FastAPI)
   - User uploads file via `POST /documents`
   - FastAPI validates file size (max 50MB), MIME type, and filename
   - File is saved to temporary storage with SHA-256 hash calculation
   - Deduplication check: if file with same hash exists, skip extraction

2. **Metadata Storage** (PostgreSQL)
   - Document metadata saved: filename, size, MIME type, hash, status
   - Status: `created` → `queued`

3. **Task Queue** (RabbitMQ)
   - FastAPI publishes extraction task to RabbitMQ
   - Task contains: document_id, temp_path, mime_type, user_id, request_id

4. **Text Extraction** (Celery Worker)
   - Worker consumes task from queue
   - Extracts text based on MIME type (TXT, DOCX, XLSX, PDF)
   - Saves raw text to MongoDB
   - Updates document status: `extracted`
   - Publishes event: `documents.text.extracted`

5. **LLM Analysis** (FastStream Consumer)
   - Consumer receives event from queue
   - Retrieves raw text from MongoDB
   - Fetches active prompt from Redis cache (or MongoDB)
   - Sends text + prompt to LLM (DeepSeek/Gemini)
   - Parses JSON response, validates structure
   - Saves analysis result to MongoDB
   - Updates document status: `success`

6. **Result Retrieval** (FastAPI)
   - User polls `GET /documents/{id}` to check status
   - Response includes: metadata, raw text, analysis result, version

### Key Architectural Decisions

**Why PostgreSQL + MongoDB + Redis?**
- **PostgreSQL**: Relational data with strict schema (users, documents metadata, transactions)
- **MongoDB**: Unstructured content (raw text, LLM analysis results, prompts) — flexible schema, large documents
- **Redis**: High-performance caching (prompts, user status), rate limiting, token blacklist

**Why Celery + FastStream?**
- **Celery**: Heavy I/O-bound tasks (text extraction from files) — proven, reliable, supports retries
- **FastStream**: Modern async consumers for LLM analysis — native async/await, better integration with async codebase

**Why local files instead of S3?**
- Current implementation uses local temp storage for simplicity
- TODO: Migrate to S3/MinIO for stateless architecture and horizontal scaling
