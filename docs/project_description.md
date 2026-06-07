# AI-Accountant: описание проекта

## 1. Назначение

AI-Accountant — личный Telegram-помощник для учета доходов, расходов,
финансовых документов и обязательств. Целевая версия также рассчитывает
предварительные налоговые резервы и отвечает на вопрос, сколько денег можно
безопасно потратить.

Telegram используется только как интерфейс. Источником данных являются
PostgreSQL и приватное файловое хранилище.

Проект не является системой официальной подачи отчетности и не заменяет
бухгалтера. Налоговые результаты должны называться estimates или резервами и
сопровождаться понятными ограничениями.

## 2. Основной принцип

```text
Пользователь
  -> Telegram Bot
  -> AI/OCR Extraction
  -> Validation
  -> User Confirmation
  -> Accounting and Obligation Services
  -> Tax Engine
  -> Budget Engine
  -> Reports
```

- AI извлекает структуру из свободного текста и OCR.
- Детерминированный код валидирует и считает деньги.
- Пользователь подтверждает AI- и OCR-операции.
- Спорная налоговая классификация не применяется без пользователя.
- LLM не хранит налоговые правила и не выполняет финальный расчет сам.

## 3. Текущее состояние

На 7 июня 2026 года реализованы этапы 1–8D.

### Учет

- пользователи с доступом по Telegram allowlist;
- ручные income/expense-транзакции;
- список последних транзакций;
- финансовый профиль и начальный баланс;
- текущий баланс: opening balance + income - expense;
- bootstrap приватных стартовых данных;
- ежемесячные recurring rules.

### AI и подтверждение

- извлечение транзакции из текста через Groq;
- валидация структурированного результата;
- preview операции;
- кнопки Save/Cancel;
- сохранение только после подтверждения AI-preview.

Ручные `/income` и `/expense` в текущей версии сохраняются сразу. Save/Cancel
реализован для AI- и OCR-потоков.

### Документы и OCR

- прием фото из Telegram;
- локальное приватное хранение;
- Telegram `file_id`, путь, SHA-256 hash, MIME type и размер;
- OCR-текст, статус, ошибка и время обработки;
- ручная связь и отвязка документа от транзакции;
- AI-preview по OCR-тексту;
- создание и привязка транзакции после Save;
- запрет повторного создания транзакции из уже связанного документа.

Текущий flow:

```text
Фото -> Document -> OCR -> AI parse -> preview -> Save/Cancel
     -> Transaction + linked document
```

### Business profile и налоговые поля

`FinancialProfile` хранит:

```text
business_type
tax_country
default_vat_rate
income_tax_reserve_percent
bituach_leumi_reserve_percent
```

Тип бизнеса задается для каждого пользователя отдельно. Например, один
пользователь может иметь `osek_patur`, другой — `osek_murshe`.

`Transaction` уже содержит:

```text
amount_total
amount_net
vat_amount
vat_rate
vat_included
vat_relevant
business_use_percent
tax_deductible
tax_category
balance_impact_type
```

Эти поля пока являются основой данных: интерфейс ручного просмотра и изменения
налоговой классификации запланирован на этап 8F.

### Обязательства

Recurring rule различает поведение:

```text
auto_pay
manual_pay
reserve_only
```

И тип обязательства:

```text
regular
loan
rent
subscription
vat
income_tax
bituach_leumi
other_tax
other
```

Поведение:

- `auto_pay` создает транзакцию через `/generate_recurring`;
- `manual_pay` создает транзакцию только через `/pay_obligation`;
- `reserve_only` используется для планирования и не создает реального
  списания.

`ObligationPayment` связывает правило, транзакцию, сумму и оплаченный период.
Команда `/pay_obligation` проверяет существующую paid-запись и блокирует
повторную оплату того же правила и точного периода. Уникального ограничения БД
для этого сочетания пока нет.

## 4. Ближайшая цель

Следующий этап — expected obligation periods и
`/obligation_status`.

Для правил обязательств нужно описать:

- длину периода: 1, 2 или 3 месяца;
- due day;
- смещение due month относительно конца периода;
- начало и окончание действия.

Система должна строить ожидаемые периоды, сопоставлять их с
`ObligationPayment` и показывать:

```text
paid
unpaid
overdue
```

Пример:

```text
VAT | 2026-05-01..2026-06-30 | unpaid | due 2026-07-15
```

На этом этапе суммы налогов не рассчитываются.

## 5. Целевая последовательность

```text
1. Expected obligation periods and statuses
2. Manual transaction tax classification
3. VAT and tax reserve estimates
4. Personal reconciliation and available-to-spend budget
5. AI advisors and rule creation
6. Reports
7. Hardening
```

Ручная налоговая классификация должна появиться раньше VAT engine: отчет не
будет надежным, если `vat_relevant`, deductible status и business use у
транзакций не проверены.

## 6. Целевая налоговая логика

### VAT

Для `osek_murshe`:

```text
VAT output from classified income
- deductible input VAT from business expenses
= estimated VAT payable
```

Для `osek_patur` обычный VAT payable report должен быть недоступен или явно
помечен как неприменимый к профилю.

VAT engine должен учитывать период, `business_use_percent`,
`tax_deductible` и согласованность total/net/VAT.

### Income tax reserve

Первый вариант:

```text
taxable business profit * income_tax_reserve_percent
```

Это резерв для планирования, а не расчет годовой декларации.

### Bituach Leumi reserve

Первый вариант:

```text
taxable business profit * bituach_leumi_reserve_percent
```

Позже простой процент может быть заменен отдельным tiered calculation.

### Tax summary

Целевой `/tax_summary` объединяет:

- VAT estimate;
- income tax reserve;
- Bituach Leumi reserve;
- total estimated reserve;
- paid/unpaid/overdue obligations.

## 7. Personal balance и свободные деньги

Бот не обязан получать каждый личный чек. Планируется reconciliation по
изменению фактического банковского баланса:

```text
previous balance + income - new balance = personal spending
```

Результат сохраняется агрегированной expense-транзакцией с
`balance_impact_type=personal`.

Целевой `/available`:

```text
current balance
- unpaid/overdue obligations
- tax reserves
- upcoming auto-pay
- safety buffer
= available to spend
```

Расчет должен исключать двойной учет одной суммы, например одновременное
вычитание фактической налоговой оплаты и того же резерва.

## 8. AI business expense advisor

Целевой flow:

```text
/can_deduct оплатила электричество, работаю из дома
```

AI может:

- объяснить вероятную классификацию;
- предложить `tax_deductible`;
- предложить `business_use_percent`;
- подготовить preview транзакции.

AI не должен автоматически принимать окончательное налоговое решение. Ответ
должен указывать, что спорную классификацию следует подтвердить с бухгалтером.

## 9. Хранение данных

Основная база — PostgreSQL. Она хранит пользователей, финансовые профили,
транзакции, recurring rules, документы и оплаты обязательств.

Основные существующие сущности:

### `users`

- Telegram identity;
- имя;
- timestamps.

### `financial_profiles`

- opening balance и дата;
- currency;
- business type и tax country;
- VAT и reserve defaults.

### `transactions`

- income/expense;
- amount, currency и date;
- category и description;
- source и status;
- VAT, deductible и business-use поля;
- balance impact type.

### `recurring_rules`

- amount, frequency и day of month;
- start/end date;
- payment behavior;
- obligation type;
- признак влияния на баланс;
- дата последней генерации.

### `obligation_payments`

- recurring rule;
- transaction;
- period start/end;
- amount, currency и status;
- notes.

### `documents`

- Telegram file id;
- local path и hash;
- MIME type и размер;
- OCR data и status;
- optional transaction link.

Будущие сущности должны добавляться только при появлении реальной логики:
ожидаемые периоды обязательств, audit log и, при необходимости, сохраненные
налоговые snapshots.

## 10. Безопасность

Уже применяется:

- Telegram allowlist;
- секреты в `.env`;
- приватный bootstrap вне git;
- запуск PostgreSQL через Docker Compose;
- локальный приватный каталог документов;
- разделение данных по `user_id`;
- передача AI только конкретного текста или OCR-содержимого.

Текущий `docker-compose.yml` публикует PostgreSQL на порту `5432` хоста. Для
развертывания вне локальной машины этот порт нужно закрыть или ограничить
сетевыми правилами.

Запланировано:

- encrypted backups и restore-проверки;
- audit log;
- soft delete;
- диагностические команды;
- редактирование без потери истории;
- исключение персональных данных из логов.

Нельзя хранить в git:

- Telegram bot token;
- Groq API key;
- пароли базы;
- приватный bootstrap;
- финансовые документы;
- ключи шифрования.

## 11. Техническая архитектура

Текущие слои:

```text
app/bot          Telegram handlers, middleware, keyboards, FSM
app/ai           Groq client, prompts, transaction extraction
app/ocr          Tesseract OCR service
app/services     accounting, balance, recurring, obligations, documents
app/models       SQLAlchemy models
app/schemas      Pydantic input/output validation
app/storage      private file storage
app/db           async SQLAlchemy session and metadata
migrations       Alembic migrations
tests            unit and handler tests
```

Целевые дополнительные слои:

```text
app/tax          deterministic VAT and reserve calculations
app/budget       reconciliation and available-to-spend calculations
app/reports      reports and exports
app/audit        immutable change history
```

Новые модули должны опираться на существующие сервисы и схемы, а налоговые
правила — быть явными, версионируемыми и тестируемыми.

## 12. Границы продукта

AI-Accountant должен:

- вести личный ledger;
- хранить подтвержденные документы;
- показывать состояние обязательств;
- давать прозрачные предварительные расчеты;
- объяснять, из каких сумм получен результат.

AI-Accountant не должен:

- подавать декларации от имени пользователя;
- гарантировать юридическую корректность AI-совета;
- скрыто менять налоговые поля;
- считать неизвестные данные как нулевые без предупреждения;
- смешивать данные разных пользователей;
- использовать Telegram как единственный архив.

Подробная последовательность реализации находится в
[`development_plan.md`](development_plan.md).
