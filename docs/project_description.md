# AI-Accountant: описание проекта

## 1. Назначение проекта

AI-Accountant — это личный бухгалтерский помощник в Telegram для учета доходов, расходов, документов, налоговых резервов и свободного бюджета.

Telegram в проекте используется только как интерфейс. Основные бухгалтерские данные, история операций, документы, настройки налогов и отчеты должны храниться в отдельной базе данных и файловом хранилище.

Главный принцип системы:

- AI понимает входящие сообщения и документы.
- Детерминированный код считает деньги, налоги и бюджет.
- Пользователь подтверждает спорные или важные решения.

AI не должен самостоятельно принимать финальные бухгалтерские или налоговые решения без проверки и подтверждения.

## 2. Что должен уметь бот

Бот должен принимать от пользователя:

- текстовые сообщения, например: "получила 1200 шекелей от клиента за консультацию";
- фотографии чеков, счетов и квитанций;
- команды, например: "отчет за апрель", "сколько можно потратить на этой неделе".

Система должна определять:

- доход это или расход;
- сумму, валюту и дату;
- категорию операции;
- наличие VAT / מע"מ;
- можно ли учитывать операцию как бизнес-расход;
- нужна ли ручная проверка.

После подтверждения пользователя бот должен сохранять операцию в базу и обновлять:

- доходы;
- расходы;
- прибыль;
- VAT к оплате или возврату;
- примерный резерв на подоходный налог;
- примерный резерв на Bituach Leumi;
- свободные деньги с учетом будущих обязательств.

## 3. Архитектурный подход

Неправильный подход:

```text
Пользователь -> Telegram -> AI -> AI сам решил налог -> записал результат
```

Так делать нельзя, потому что AI может ошибиться, перепутать VAT, неверно классифицировать расход или додумать отсутствующие детали.

Правильный поток:

```text
Пользователь
  -> Telegram Bot
  -> AI Extractor
  -> Validation Layer
  -> User Confirmation
  -> Accounting Engine
  -> Tax Engine
  -> Budget Engine
  -> Reports Engine
```

AI Extractor отвечает только за извлечение структурированных данных из текста или изображения. Финальные расчеты выполняют обычные программные модули по явным правилам.

## 4. Хранение данных

Основное хранилище: PostgreSQL.

PostgreSQL подходит для бухгалтерии, потому что данные структурированные:

- операции;
- суммы;
- даты;
- категории;
- налоги;
- отчеты;
- связи между документами и транзакциями;
- история изменений.

Telegram не должен быть местом хранения бухгалтерии. Он может хранить `file_id` фотографии, но не должен быть единственным архивом документов.

MongoDB не является предпочтительным вариантом для этого проекта, потому что финансовые отчеты, связи, расчеты по периодам и консистентность данных удобнее и надежнее реализуются в SQL-базе.

AI-результаты можно хранить в JSON-полях PostgreSQL, если нужна гибкость.

## 5. Хранилище документов

Для фото чеков и счетов можно использовать:

- локальное шифрованное хранилище;
- S3-compatible storage;
- private VPS volume.

Для личной версии проекта достаточно локального каталога:

```text
/data/private/documents/
```

В базе данных нужно хранить:

- путь к файлу;
- Telegram `file_id`;
- hash файла;
- дату загрузки;
- связь с операцией;
- OCR-текст;
- JSON-результат AI-извлечения.

## 6. Безопасность

Так как бот работает с личными финансовыми данными, безопасность нужно заложить с самого начала.

Минимальные требования:

- доступ только по allowlist Telegram `user_id`;
- секреты только в `.env`;
- PostgreSQL не должен быть открыт в интернет;
- база доступна только внутри Docker network или приватной сети;
- регулярные шифрованные бэкапы;
- audit log для всех изменений;
- soft delete вместо физического удаления;
- AI получает только конкретное сообщение или документ, а не всю финансовую историю.

Пример ограничения доступа:

```env
ALLOWED_TELEGRAM_USER_IDS=123456789
```

Нельзя хранить в коде:

- Telegram bot token;
- Groq API key;
- пароли к базе;
- ключи шифрования.

Пример имени бэкапа:

```text
backup_2026-05-08.sql.gz.enc
```

## 7. Подтверждение операций

Даже если AI уверен в результате, бот должен показывать пользователю карточку подтверждения.

Пример:

```text
Я понял так:

Тип: расход
Сумма: 86.40 ₪
Категория: еда / бизнес-встреча
VAT: есть
Дата: 08.05.2026

Сохранить?
[Да] [Изменить] [Отмена]
```

Операция становится частью ledger только после подтверждения.

## 8. Налоговая логика для Израиля

Налоговая логика должна быть отдельным модулем и конфигурационным слоем. Бот не должен "придумывать закон" или хранить правила только в prompt для LLM.

Для `עוסק מורשה` система должна учитывать минимум:

- VAT / מע"מ;
- авансы по подоходному налогу;
- Bituach Leumi;
- требования по invoice allocation numbers для крупных B2B-счетов;
- календарь налоговых платежей.

VAT-модуль должен считать:

- VAT с доходов;
- входящий VAT с расходов;
- разницу к оплате или возврату;
- отчетный период.

Bituach Leumi должен быть отдельным расчетным модулем, потому что расчет для self-employed зависит от годовой налоговой оценки, порогов, ставок и специальных корректировок.

Требования по allocation number для tax invoice должны храниться в конфиге, потому что пороги меняются по датам.

## 9. Пример налогового конфига

```yaml
country: "IL"
year: 2026

vat:
  standard_rate: 0.18
  reporting_period: "monthly"

bituach_leumi:
  reduced_threshold_monthly: 7703
  max_income_monthly: 51910
  reduced_rate_total: 0.077
  full_rate_total: 0.18

income_tax:
  advance_percent_default: 0.10
  mode: "advance_percent"

invoice_allocation:
  thresholds:
    - from: "2025-01-01"
      amount_before_vat: 20000
    - from: "2026-01-01"
      amount_before_vat: 10000
    - from: "2026-06-01"
      amount_before_vat: 5000
```

Бот должен показывать пользователю, какой налоговый конфиг используется:

```text
Налоговые параметры: israel_2026.yaml
Последняя проверка: 2026-05-08
```

## 10. Расчет свободных денег

Вопрос "сколько можно потратить на этой неделе" должен считаться не как простой баланс минус расходы.

Формула:

```text
Свободные деньги =
текущий доступный баланс
+ ожидаемые поступления до конца периода
- регулярные списания до конца периода
- обязательный резерв на VAT
- резерв на подоходный налог
- резерв на Bituach Leumi
- уже запланированные расходы
- минимальный safety buffer
```

Пример ответа:

```text
На эту неделю свободно примерно: 1,240 ₪

Расчет:
Баланс сейчас: 5,800 ₪
Ожидаемые поступления: +2,000 ₪
Регулярные списания: -1,100 ₪
Резерв на VAT: -1,050 ₪
Резерв на Bituach Leumi: -620 ₪
Резерв на подоходный налог: -1,290 ₪
Буфер: -500 ₪

Итого можно безопасно потратить: 1,240 ₪
```

Если часть налогов считается как прогноз, бот должен использовать формулировку "примерно".

## 11. Основные модули

```text
Telegram Bot
  -> Input Processing
  -> AI / OCR Extraction
  -> Validation
  -> Transaction Confirmation
  -> Accounting Ledger
  -> Tax Engine
  -> Budget Engine
  -> Reports
```

### Telegram Bot

Технология: `aiogram 3`.

Задачи:

- принимать текст;
- принимать фото;
- показывать кнопки;
- задавать уточняющие вопросы;
- отправлять отчеты;
- ограничивать доступ по Telegram `user_id`.

### AI Extractor

Задачи:

- понимать текст;
- распознавать фото;
- возвращать структурированный JSON.

Пример результата:

```json
{
  "transaction_type": "expense",
  "amount_total": 86.40,
  "currency": "ILS",
  "date": "2026-05-08",
  "vendor_name": "Super-Pharm",
  "category": "office_supplies",
  "vat_included": true,
  "vat_amount": 13.18,
  "business_use_percent": 100,
  "confidence": 0.87,
  "needs_user_confirmation": true
}
```

### Validation Layer

Проверяет:

- сумма не пустая;
- дата корректная;
- валюта известна;
- тип операции понятен;
- VAT не больше суммы;
- категория существует;
- confidence не слишком низкий.

### Accounting Engine

Отвечает за запись операций в ledger.

После подтверждения операция становится бухгалтерской записью. Старые операции лучше не менять напрямую: изменения должны фиксироваться через историю или корректирующие операции.

### Tax Engine

Считает:

- VAT output;
- VAT input;
- VAT payable;
- taxable profit;
- estimated income tax reserve;
- estimated Bituach Leumi reserve;
- tax payment calendar.

### Budget Engine

Считает:

- свободные деньги;
- план расходов;
- обязательные резервы;
- регулярные платежи;
- риск кассового разрыва.

### Reports Engine

Формирует:

- отчет за месяц;
- отчет за год;
- отчет по VAT;
- отчет по категориям;
- cashflow;
- список неподтвержденных операций;
- список операций без документов.

## 12. Стартовые данные и регулярные платежи

Реальные личные данные не должны лежать в git.

В репозитории должен быть шаблон:

```text
config/bootstrap.example.yaml
```

Реальный файл должен быть приватным и добавленным в `.gitignore`:

```text
config/private/bootstrap.yaml
```

Пример:

```yaml
owner:
  name: "Anna"
  country: "Israel"
  business_type: "osek_murshe"
  currency: "ILS"

business:
  vat_registered: true
  vat_reporting_period: "monthly"
  income_tax_advance_percent: 10
  bituach_leumi_estimation_mode: "projected_profit"

opening_balances:
  bank_main:
    amount: 12000
    currency: "ILS"
  cash:
    amount: 500
    currency: "ILS"

regular_income:
  - name: "Client retainer"
    amount: 3000
    currency: "ILS"
    frequency: "monthly"
    day_of_month: 10
    category: "services_income"

regular_expenses:
  - name: "Rent"
    amount: 4500
    currency: "ILS"
    frequency: "monthly"
    day_of_month: 1
    category: "personal_rent"
    business_use_percent: 0

  - name: "Loan payment"
    amount: 1200
    currency: "ILS"
    frequency: "monthly"
    day_of_month: 15
    category: "loan_payment"
    business_use_percent: 0

safety_buffer:
  weekly_minimum: 500
  monthly_minimum: 2000
```

## 13. Предлагаемая структура проекта

```text
ai_accountant_bot/
├── app/
│   ├── main.py
│   ├── bot/
│   │   ├── dispatcher.py
│   │   ├── middlewares.py
│   │   ├── keyboards.py
│   │   └── handlers/
│   │       ├── start.py
│   │       ├── text_input.py
│   │       ├── photo_input.py
│   │       ├── confirmation.py
│   │       ├── reports.py
│   │       └── budget.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── logging.py
│   │   └── exceptions.py
│   ├── db/
│   │   ├── session.py
│   │   ├── base.py
│   │   └── repositories/
│   │       ├── transactions.py
│   │       ├── documents.py
│   │       ├── recurring.py
│   │       ├── tax.py
│   │       └── audit.py
│   ├── models/
│   │   ├── user.py
│   │   ├── business_profile.py
│   │   ├── transaction.py
│   │   ├── document.py
│   │   ├── category.py
│   │   ├── recurring_rule.py
│   │   ├── tax_period.py
│   │   └── audit_log.py
│   ├── schemas/
│   │   ├── transaction.py
│   │   ├── extraction.py
│   │   ├── report.py
│   │   ├── budget.py
│   │   └── tax.py
│   ├── services/
│   │   ├── input_service.py
│   │   ├── transaction_service.py
│   │   ├── document_service.py
│   │   ├── recurring_service.py
│   │   ├── report_service.py
│   │   ├── budget_service.py
│   │   └── notification_service.py
│   ├── ai/
│   │   ├── llm_client.py
│   │   ├── ocr_service.py
│   │   ├── extraction_prompts.py
│   │   ├── transaction_classifier.py
│   │   └── confidence.py
│   ├── tax/
│   │   ├── engine.py
│   │   └── israel/
│   │       ├── vat.py
│   │       ├── income_tax.py
│   │       ├── bituach_leumi.py
│   │       ├── deductible_expenses.py
│   │       ├── allocation_numbers.py
│   │       └── rules_loader.py
│   ├── storage/
│   │   ├── file_storage.py
│   │   ├── encrypted_storage.py
│   │   └── backup_service.py
│   └── jobs/
│       ├── scheduler.py
│       ├── recurring_transactions_job.py
│       ├── tax_reminders_job.py
│       └── backup_job.py
├── config/
│   ├── app.example.yaml
│   ├── categories.yaml
│   ├── tax_rules/
│   │   └── israel_2026.yaml
│   └── private/
│       ├── bootstrap.yaml
│       └── secrets.note.txt
├── migrations/
│   └── alembic/
├── tests/
│   ├── test_transaction_extraction.py
│   ├── test_vat_calculation.py
│   ├── test_bituach_leumi.py
│   ├── test_budget.py
│   └── test_reports.py
├── scripts/
│   ├── init_db.py
│   ├── load_bootstrap.py
│   ├── create_backup.py
│   └── restore_backup.py
├── docs/
│   ├── architecture.md
│   ├── tax_logic.md
│   ├── data_model.md
│   └── telegram_flows.md
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env
├── .gitignore
└── README.md
```

## 14. Основные таблицы базы

### users

- `id`
- `telegram_user_id`
- `name`
- `created_at`

### business_profiles

- `id`
- `user_id`
- `business_type`
- `country`
- `currency`
- `vat_registered`
- `vat_reporting_period`
- `income_tax_advance_percent`
- `created_at`

### transactions

- `id`
- `user_id`
- `type`: `income`, `expense`, `tax_payment`, `transfer`, `personal`
- `date`
- `amount_total`
- `currency`
- `amount_net`
- `vat_amount`
- `category_id`
- `counterparty_name`
- `description`
- `business_use_percent`
- `deductible_status`
- `source`: `text`, `photo`, `manual`, `recurring`
- `status`: `draft`, `confirmed`, `corrected`, `deleted`
- `created_at`
- `updated_at`

### documents

- `id`
- `transaction_id`
- `telegram_file_id`
- `local_path`
- `file_hash`
- `ocr_text`
- `ai_extracted_json`
- `created_at`

### recurring_rules

- `id`
- `user_id`
- `name`
- `type`
- `amount`
- `currency`
- `frequency`
- `day_of_month`
- `category_id`
- `business_use_percent`
- `active`

### tax_periods

- `id`
- `user_id`
- `period_start`
- `period_end`
- `vat_output`
- `vat_input`
- `vat_payable`
- `income_tax_reserve`
- `bituach_leumi_reserve`
- `status`

### audit_logs

- `id`
- `entity_type`
- `entity_id`
- `action`
- `old_value`
- `new_value`
- `created_at`

## 15. Сценарий текстового ввода

Пользователь пишет:

```text
получила 1500 шекелей от клиента за консультацию
```

Поток:

1. Бот передает текст в AI Extractor.
2. AI возвращает JSON.
3. Validation Layer проверяет поля.
4. Бот показывает пользователю карточку подтверждения.
5. Пользователь нажимает "Да".
6. Операция сохраняется.
7. Tax Engine обновляет прогноз по налогам.
8. Budget Engine обновляет доступный бюджет.

Пример подтверждения:

```text
Я понял так:

Доход: 1,500 ₪
Категория: услуги
VAT: включить
Дата: сегодня

Сохранить?
```

## 16. Сценарий с фото документа

Пользователь отправляет чек.

Поток:

1. Бот скачивает фото.
2. Сохраняет файл.
3. Считает hash файла.
4. Запускает OCR.
5. Передает OCR-текст и/или изображение в AI Extractor.
6. Получает структурированные данные.
7. Показывает пользователю подтверждение.
8. После подтверждения записывает операцию.

Если AI не уверен:

```text
Я не уверен, это личная или бизнес-трата.

Сумма: 184.90 ₪
Магазин: KSP
Возможная категория: техника / оборудование

Это бизнес-расход?
[Да] [Нет] [Частично]
```

## 17. Сценарий отчета

Пользователь пишет:

```text
отчет за апрель
```

Бот отвечает:

```text
Отчет за апрель 2026

Доходы: 18,500 ₪
Расходы: 6,300 ₪
Прибыль до налогов: 12,200 ₪

VAT с доходов: 2,823 ₪
Входящий VAT: 641 ₪
VAT к оплате: 2,182 ₪

Резерв на подоходный налог: 1,800 ₪
Резерв на Bituach Leumi: 1,050 ₪

Ориентировочно после резервов: 7,168 ₪
```

## 18. План разработки

Подробная рабочая дорожная карта вынесена в отдельный документ: [development_plan.md](development_plan.md).

### Этап 1. Каркас проекта

Цель: запустить пустого Telegram-бота.

Сделать:

- структуру проекта;
- `.env`;
- Docker;
- подключение к PostgreSQL;
- базовые команды `/start`, `/help`;
- проверку Telegram `user_id`.

Результат: бот работает, но пока ничего не считает.

### Этап 2. База данных и ручной ввод операций

Цель: сохранять операции без AI.

Сделать:

- таблицы `users`, `transactions`, `categories`;
- команду добавления дохода;
- команду добавления расхода;
- подтверждение операции;
- просмотр последних операций.

Результат: можно вручную вести учет через Telegram.

### Этап 3. Стартовые данные и регулярные платежи

Цель: учитывать кредиты, аренду, подписки и регулярные доходы.

Сделать:

- `bootstrap.yaml`;
- загрузчик стартовых данных;
- recurring rules;
- job, который создает регулярные операции;
- команду "регулярные платежи".

Результат: бот понимает не только ручные операции, но и будущие обязательства.

### Этап 4. AI-распознавание текста

Цель: пользователь пишет обычной фразой, бот сам предлагает операцию.

Сделать:

- LLM client;
- prompt для извлечения JSON;
- validation;
- confidence score;
- подтверждение перед сохранением.

Результат: фраза "Заплатила 120 шекелей за интернет" превращается в предложенную расходную операцию.

### Этап 5. Фото чеков и OCR

Цель: принимать фото документов.

Сделать:

- загрузку фото из Telegram;
- локальное хранение;
- OCR;
- AI extraction из OCR-текста;
- связь документа с операцией.

Результат: пользователь отправляет чек, бот предлагает готовую операцию.

### Этап 6. Базовый налоговый модуль

Цель: считать предварительные налоговые резервы.

Сделать:

- VAT calculator;
- income tax reserve calculator;
- Bituach Leumi estimator;
- tax period model;
- отчет "налоги сейчас".

Результат: бот показывает, сколько примерно надо отложить.

### Этап 7. Бюджетный модуль

Цель: отвечать на вопросы вроде "сколько можно потратить".

Сделать:

- расчет текущего свободного баланса;
- учет будущих регулярных платежей;
- учет налоговых резервов;
- недельный и месячный бюджет;
- предупреждения о кассовом разрыве.

Результат: бот дает практическую цифру, сколько можно безопасно потратить.

### Этап 8. Отчеты

Цель: получать понятные отчеты.

Сделать:

- отчет за месяц;
- отчет по категориям;
- отчет по VAT;
- отчет по прибыли;
- экспорт CSV/XLSX;
- список операций без документов.

Результат: бот становится полезным как личный бухгалтерский помощник.

### Этап 9. Защита, бэкапы, аудит

Цель: не потерять данные и не раскрыть их.

Сделать:

- encrypted backups;
- restore script;
- audit log;
- soft delete;
- ограничение доступа;
- логирование ошибок без персональных данных.

Результат: проект можно безопасно использовать лично.

## 19. MVP

Рекомендуемый порядок MVP:

1. Telegram bot.
2. PostgreSQL.
3. Ручной ввод доходов и расходов.
4. Стартовые данные и регулярные платежи.
5. Простой отчет за месяц.
6. Простой расчет свободных денег.
7. AI для текста.
8. Фото чеков.
9. Более сложные налоги.

Такой порядок позволит быстрее получить работающий продукт и не застрять на сложной архитектуре до появления базовой пользы.

## 20. Итоговая концепция

AI-Accountant должен быть не "магическим AI-бухгалтером", а системой из трех уровней:

- AI извлекает и предлагает структуру данных.
- Код считает учет, налоги и бюджет по явным правилам.
- Пользователь подтверждает спорные решения.

Такой подход снижает риск ошибок и делает проект пригодным для реального личного использования.
