FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# КОПИРУЕМ ТОЧНО СУЩЕСТВУЮЩИЙ ФАЙЛ
COPY requirements.txt .

# СТАВИМ ЗАВИСИМОСТИ
RUN pip install --no-cache-dir -r requirements.txt

# КОД ПРИЛОЖЕНИЯ
COPY app/ ./app/

RUN mkdir -p /app/data

EXPOSE 8000
CMD ["python", "-m", "app.main"]