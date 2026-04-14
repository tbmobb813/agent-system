FROM python:3.11-slim

WORKDIR /app

RUN pip install --upgrade pip
COPY requirements-telegram.txt .
RUN pip install --no-cache-dir -r requirements-telegram.txt

COPY bot.py .

RUN adduser --disabled-password --gecos '' botuser \
    && chown -R botuser /app
USER botuser

CMD ["python3", "-u", "bot.py"]
