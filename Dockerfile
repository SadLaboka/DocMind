FROM python:3.13.13-bookworm

WORKDIR /usr/src/app

RUN adduser SadLaboka --system --no-create-home --disabled-password --allow-bad-names

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY ./poetry.lock .
COPY ./pyproject.toml .
RUN pip install --upgrade pip && pip install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --only=main --no-interaction --no-ansi --no-root

COPY . .

RUN chown -R SadLaboka ./
USER SadLaboka

CMD ["uvicorn", "main:app", "--host", "0.0.0.0"]