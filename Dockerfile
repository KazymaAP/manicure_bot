FROM python:3.12-slim

# Метаданные
LABEL maintainer="Manicure Bot v4"
LABEL description="Telegram-бот для записи на маникюр"

# Рабочая директория
WORKDIR /app

# Зависимости системы
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Установка зависимостей Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Директория для базы данных
RUN mkdir -p /app/data

# Запуск бота
CMD ["python", "main.py"]
