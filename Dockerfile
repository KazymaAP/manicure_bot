# Multi-stage Dockerfile для оптимизации размера образа

# Stage 1: Builder
FROM python:3.12-slim as builder

WORKDIR /build

# Установка зависимостей для сборки (если нужны)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime (финальный образ)
FROM python:3.12-slim

LABEL maintainer="Manicure Bot v4"
LABEL description="Telegram-бот для записи на маникюр"

WORKDIR /app

# Установка только необходимых системных зависимостей для runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Копирование Python пакетов из builder
COPY --from=builder /root/.local /root/.local

# Добавляем в PATH
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Копирование исходного кода (без тестов, кэша и т.д. — см. .dockerignore)
COPY . .

# Директория для базы данных
RUN mkdir -p /app/data && chmod 777 /app/data

# Запуск бота
CMD ["python", "main.py"]
