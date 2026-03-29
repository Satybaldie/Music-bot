FROM python:3.11-slim

# Устанавливаем ffmpeg
RUN apt update && apt install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем Python-пакеты
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Запускаем бота
CMD uvicorn bot:fastapi_app --host 0.0.0.0 --port $PORT