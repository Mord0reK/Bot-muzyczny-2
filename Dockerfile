FROM python:3.11-slim

# Instalacja ffmpeg potrzebnego do odtwarzania audio
RUN apt-get update && \
    apt-get install -y ffmpeg libopus0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]