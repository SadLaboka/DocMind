FROM python:3.13.13-bookworm

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false

RUN adduser SadLaboka \
    --system \
    --no-create-home \
    --disabled-password \
    --allow-bad-names

COPY ./poetry.lock ./pyproject.toml ./

RUN pip install --upgrade pip \
    && pip install poetry \
    && poetry install \
        --only=main \
        --no-interaction \
        --no-ansi \
        --no-root

RUN mkdir -p /usr/src/app/keys /usr/src/app/temp \
    && echo '\nGenerating RSA keys...\n' \
    && openssl genrsa -out /usr/src/app/keys/private.pem 4096 \
    && openssl rsa \
        -in /usr/src/app/keys/private.pem \
        -pubout \
        -out /usr/src/app/keys/public.pem \
    && chown -R SadLaboka /usr/src/app/keys /usr/src/app/temp \
    && chown SadLaboka /usr/src/app \
    && echo '\nRSA keys generated\n'

COPY --chown=SadLaboka ./src ./src
COPY --chown=SadLaboka ./alembic ./alembic
COPY --chown=SadLaboka ./scripts ./scripts

COPY --chown=SadLaboka \
    ./main.py \
    ./run_stream.py \
    ./alembic.ini \
    ./

USER SadLaboka

CMD ["uvicorn", "main:app", "--host", "0.0.0.0"]
