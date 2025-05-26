FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

ENV BOT_TOKEN=your_default_token \
    DATABASE_URL=sqlite+aiosqlite:///./db.sqlite \
    YOOKASSA_SHOP_ID=your_shop_id \
    YOOKASSA_SECRET_KEY=your_secret_key

CMD ["python", "run_bot.py"]
