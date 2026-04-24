# Grato Bot

Telegram buyurtma boti + FastAPI backend.

## Stack
- Telegram bot: `pyTelegramBotAPI`
- API: `FastAPI` + `uvicorn`
- DB: PostgreSQL (`pg8000`)

## Talab qilinadigan environment o'zgaruvchilar
`BOT_TOKEN`, `ADMIN_ID`, `AUTH_SECRET`, `DATABASE_URL`, `API_URL` (yoki `API_BASE`), `WEB_APP_URL`.

Namuna: `.env.example`

## Local ishga tushirish

1. Virtualenv va dependency:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. `.env.example` asosida `.env` yarating va qiymatlarni to'ldiring.

3. API ni ishga tushiring:
```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

4. Botni ishga tushiring (boshqa terminalda):
```bash
python bot.py
```

## Deploy bo'yicha tavsiya
Bot va API ni alohida process/service qilib deploy qiling:

- **Web service**: `uvicorn api.app:app --host 0.0.0.0 --port $PORT`
- **Worker service**: `python bot.py`

## Tez diagnostika
```bash
python - <<'PY'
import importlib
importlib.import_module('api.app')
importlib.import_module('bot')
print('imports ok')
PY
```
