# AI Accountant Bot

Minimal working Telegram bot skeleton for a personal accounting assistant.

## Stack

- Python 3.11+
- aiogram 3
- pydantic-settings
- SQLAlchemy 2
- Alembic
- PostgreSQL
- Docker Compose
- pytest

## Local Setup

Create and activate a virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -e ".[dev]"
```

The project uses a local `.env` file for real credentials and runtime
configuration. The file is intentionally excluded by `.gitignore` and must not
be committed or shared.

Ensure the local `.env` contains:

- `TELEGRAM_BOT_TOKEN` with the token issued by BotFather.
- `ALLOWED_TELEGRAM_USER_IDS` with one or more comma-separated Telegram user
  ids allowed to access the bot.
- `DATABASE_URL` using the async PostgreSQL driver.
- `GROQ_API_KEY` with the API key used for AI features.
- `LOG_LEVEL` if a non-default log level is needed.

Start PostgreSQL:

```bash
docker compose up -d db
```

Apply database migrations:

```bash
.venv/bin/alembic upgrade head
```

Run tests:

```bash
.venv/bin/pytest
```

Run the bot:

```bash
.venv/bin/python -m app.main
```

Open Telegram and send:

```text
/start
```

Expected response for an allowed user:

```text
AI Accountant Bot is running. Access confirmed.
```

For a user id not listed in `ALLOWED_TELEGRAM_USER_IDS`, the bot responds:

```text
Access denied.
```

## Check User Creation

After sending `/start` from an allowed Telegram account, connect to PostgreSQL:

```bash
docker compose exec db psql -U ai_accountant -d ai_accountant
```

Run:

```sql
select id, telegram_user_id, name, created_at, updated_at from users;
```

The table should contain a row with your Telegram user id.

## Bootstrap Financial Data

Create a private bootstrap file from the example:

```bash
cp config/bootstrap.example.yaml config/private/bootstrap.yaml
```

Edit `config/private/bootstrap.yaml` and replace `owner.telegram_user_id` with
your Telegram user id. Keep this file private; `config/private/*.yaml` is
ignored by Git.

Load the bootstrap data:

```bash
.venv/bin/python scripts/load_bootstrap.py --file config/private/bootstrap.yaml
```

The loader creates or finds the user, creates or updates the financial profile,
and inserts recurring rules without duplicating identical rules on repeated
runs.

Check the loaded data in PostgreSQL:

```bash
docker compose exec db psql -U ai_accountant -d ai_accountant
```

```sql
select id, user_id, opening_balance, currency, opening_balance_date
from financial_profiles;

select id, user_id, type, amount, currency, category, description,
       frequency, day_of_month, active
from recurring_rules
order by user_id, type, day_of_month;
```
# ai_accountant_bot
