FROM python:3.13.13-bookworm

WORKDIR /usr/src/app

RUN adduser SadLaboka --system --no-create-home --disabled-password --allow-bad-names

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false

ARG INSTALL_MODE=main

COPY ./poetry.lock ./pyproject.toml ./
RUN pip install --upgrade pip && pip install poetry

RUN if [ "$INSTALL_MODE" = "test" ]; then \
        poetry install --no-interaction --no-ansi --no-root; \
    else \
        poetry install --only=main --no-interaction --no-ansi --no-root; \
    fi

COPY . .

RUN mkdir -p /usr/src/app/keys && \
    echo '\nGenerating RSA-keys...\n' && \
    openssl genrsa -out /usr/src/app/keys/private.pem 4096 && \
    openssl rsa -in /usr/src/app/keys/private.pem -pubout -out /usr/src/app/keys/public.pem && \
    echo '\nKeys generated...\n'

RUN chown -R SadLaboka ./
USER SadLaboka

CMD ["uvicorn", "main:app", "--host", "0.0.0.0"]
