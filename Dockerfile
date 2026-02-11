FROM python:3.13-slim

WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY main.py .

# Создаем директорию для временных файлов
RUN mkdir -p temp_files

# Запускаем бота
CMD ["python", "bot.py"]
