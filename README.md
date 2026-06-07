# AI Accountant Bot

Личный Telegram-бот для учета доходов, расходов, документов и финансовых
обязательств. Проект развивается в сторону налогового планирования и расчета
свободного бюджета, но не заменяет бухгалтера и не выполняет официальную
налоговую отчетность.

Актуальное состояние проекта: завершены этапы 1–8D. Следующий этап —
формирование ожидаемых периодов обязательств и статусов
`paid` / `unpaid` / `overdue`.

## Что уже работает

- доступ к боту только для Telegram-пользователей из allowlist;
- ручной ввод доходов и расходов;
- финансовый профиль, начальный баланс и текущий баланс;
- регулярные правила и генерация `auto_pay`-операций;
- обязательства с режимами `auto_pay`, `manual_pay`, `reserve_only`;
- ручная оплата обязательств с указанием отчетного периода;
- проверка в `/pay_obligation`, не позволяющая повторно оплатить тот же период;
- AI-извлечение операции из текста через Groq;
- Save/Cancel-подтверждение AI-операции;
- прием и локальное хранение документов;
- OCR через Tesseract;
- AI-preview операции по OCR-тексту;
- Save/Cancel-подтверждение операции из документа;
- связь документа с транзакцией и защита от повторного создания операции;
- бизнес-профиль и налоговые поля транзакций.

Полный документный flow:

```text
Фото -> Document -> OCR -> AI parse -> preview -> Save/Cancel
     -> Transaction + linked document
```

## Что пока не реализовано

- ожидаемые периоды обязательств и команда `/obligation_status`;
- просмотр и ручное редактирование налоговой классификации транзакций;
- VAT estimate, резервы income tax и Bituach Leumi;
- единый `/tax_summary`;
- reconciliation личных расходов;
- расчет `/available`;
- AI-консультант по бизнес-расходам;
- отчеты, экспорт, audit log, soft delete и зашифрованные бэкапы.

Актуальная последовательность работ описана в
[`docs/development_plan.md`](docs/development_plan.md). Назначение и границы
системы описаны в [`docs/project_description.md`](docs/project_description.md).

## Стек

- Python 3.13 в Docker, Python 3.11+ для локальной разработки;
- aiogram 3;
- SQLAlchemy 2 и Alembic;
- PostgreSQL 16;
- pydantic-settings;
- Groq через OpenAI-compatible API;
- Tesseract OCR и pytesseract;
- Docker Compose;
- pytest.

## Запуск через Docker

Docker Compose — основной способ запуска.

1. Создать приватный `.env`:

```bash
cp .env.example .env
```

2. Заполнить минимум:

```text
TELEGRAM_BOT_TOKEN
ALLOWED_TELEGRAM_USER_IDS
GROQ_API_KEY
```

3. Запустить PostgreSQL и бота:

```bash
docker compose up --build
```

4. Применить миграции в другом терминале:

```bash
docker compose exec bot alembic upgrade head
```

Если контейнер бота не запущен:

```bash
docker compose run --rm bot alembic upgrade head
```

В Docker бот подключается к базе по адресу:

```text
postgresql+asyncpg://ai_accountant:<password>@db:5432/ai_accountant
```

Документы сохраняются на хосте в `./data/private/documents` и монтируются в
контейнер как `/app/data/private/documents`.

Проверка OCR:

```bash
docker compose run --rm bot tesseract --version
```

Запуск тестов:

```bash
docker compose run --rm bot pytest
```

## Локальная разработка

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Для OCR нужен системный Tesseract. На macOS:

```bash
brew install tesseract
```

Запустить только PostgreSQL, применить миграции и запустить бота:

```bash
docker compose up -d db
.venv/bin/alembic upgrade head
.venv/bin/python -m app.main
```

Локальный `DATABASE_URL` должен использовать `localhost` и драйвер
`postgresql+asyncpg`.

## Начальные данные

Создать приватный bootstrap-файл:

```bash
cp config/bootstrap.example.yaml config/private/bootstrap.yaml
```

Указать Telegram ID владельца, финансовый профиль и recurring rules, затем
загрузить данные:

```bash
.venv/bin/python scripts/load_bootstrap.py \
  --file config/private/bootstrap.yaml
```

Загрузчик повторно использует пользователя, обновляет финансовый профиль и не
создает дубликаты идентичных правил. Тип бизнеса задается отдельно для каждого
пользователя, например `osek_patur` или `osek_murshe`.

Приватные `.env`, `config/private/*.yaml` и финансовые документы нельзя
коммитить.

## Команды текущей версии

```text
/start
/help
/profile
/balance

/income amount description
/expense amount description
/last
/ai_parse text

/recurring
/generate_recurring
/obligations
/obligation_payments
/pay_obligation rule_id amount period_start period_end description

/documents
/document document_id
/ocr_document document_id
/parse_document document_id
/link_document document_id transaction_id
/unlink_document document_id
```

Пример ручной оплаты VAT-обязательства за период:

```text
/pay_obligation 5 1200 2026-05-01 2026-06-30 VAT payment May-June
```

`/generate_recurring` создает транзакции только для `auto_pay`.
`manual_pay` оплачивается через `/pay_obligation`, а `reserve_only` не создает
реального списания.

## Важные ограничения

- `/income` и `/expense` сохраняют ручную операцию сразу;
- подтверждение Save/Cancel применяется к AI- и OCR-операциям;
- текущий `/balance` считает начальный баланс плюс доходы минус расходы;
- налоговые поля уже хранятся, но интерфейс их ручной классификации еще не
  реализован;
- защита от повторной оплаты периода сейчас реализована на уровне
  `/pay_obligation`, а не уникальным ограничением PostgreSQL;
- налоговые суммы и доступный бюджет пока не рассчитываются;
- все будущие налоговые результаты должны показываться как estimates, а не как
  официальная декларация или профессиональная консультация.
