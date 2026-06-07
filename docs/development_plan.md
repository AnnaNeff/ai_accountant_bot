# План разработки AI-Accountant

Актуально на 7 июня 2026 года.

## Принципы разработки

```text
Сначала учет обязательств и периодов
Потом ручная налоговая классификация операций
Потом VAT и tax reserve calculations
Потом бюджет "сколько свободно"
Потом AI-помощники и автоматизация
```

- Telegram является интерфейсом, а не хранилищем бухгалтерии.
- AI извлекает данные и предлагает классификацию.
- Деньги, налоги, обязательства и бюджет считает детерминированный код.
- Пользователь подтверждает AI- и OCR-операции и принимает спорные налоговые
  решения.
- Estimates не выдаются за официальную отчетность или консультацию бухгалтера.

## Завершено

### Этапы 1–7. Учет, AI, документы и OCR

- [x] 1. Каркас проекта: aiogram, PostgreSQL, Alembic, Docker Compose,
  allowlist и базовые команды.
- [x] 2. Ручной ввод income/expense и просмотр последних транзакций.
- [x] 3. Financial profile, bootstrap и recurring rules.
- [x] 4. Расчет текущего balance.
- [x] 5. AI text extraction через Groq.
- [x] 6. AI preview и Save/Cancel confirmation flow.
- [x] 6.1. Раздельные callback-кнопки и очистка UX confirmation flow.
- [x] 7A. Локальное приватное хранение документов и file hash.
- [x] 7B. Ручная связь документа с транзакцией.
- [x] 7C. OCR через Tesseract.
- [x] 7C.1. Docker runtime с Tesseract.
- [x] 7D. AI preview из OCR-текста.
- [x] 7E. Save/Cancel транзакции из OCR-документа.
- [x] 7F. Защита от повторного создания транзакции из уже связанного документа.

Рабочий flow:

```text
Фото -> Document -> OCR -> AI parse -> preview -> Save/Cancel
     -> Transaction + linked document
```

### Этап 8A. Business profile и tax fields

- [x] `FinancialProfile.business_type`.
- [x] `tax_country`.
- [x] `default_vat_rate`.
- [x] `income_tax_reserve_percent`.
- [x] `bituach_leumi_reserve_percent`.
- [x] Поля транзакции: `amount_total`, `amount_net`, `vat_amount`, `vat_rate`,
  `vat_included`, `vat_relevant`, `business_use_percent`, `tax_deductible`,
  `tax_category`, `balance_impact_type`.
- [x] Тип бизнеса задается на уровне пользователя и не захардкожен.

### Этап 8B. Поведение обязательств

- [x] `payment_behavior`: `auto_pay`, `manual_pay`, `reserve_only`.
- [x] `obligation_type`: `regular`, `loan`, `rent`, `subscription`, `vat`,
  `income_tax`, `bituach_leumi`, `other_tax`, `other`.
- [x] `auto_pay` обрабатывается `/generate_recurring`.
- [x] `manual_pay` не генерируется автоматически.
- [x] `reserve_only` не влияет на баланс как реальное списание.

### Этап 8C. Ручная оплата обязательств

- [x] Команда `/pay_obligation`.
- [x] Создание подтвержденной expense-транзакции только для `manual_pay`.
- [x] Запрет прямой оплаты `auto_pay` и `reserve_only`.

### Этап 8D. Оплаты с отчетными периодами

- [x] Модель `ObligationPayment`.
- [x] Связь оплаты с recurring rule и transaction.
- [x] `period_start` и `period_end`.
- [x] Команда:

```text
/pay_obligation rule_id amount period_start period_end description
```

- [x] Проверка дубликата в `/pay_obligation` для того же правила и периода.
- [x] Просмотр последних оплат через `/obligation_payments`.

## Следующий этап

### Этап 8E. Expected obligation periods и статусы

Цель: построить календарь ожидаемых обязательств без расчета налоговых сумм.

#### 8E.1. Schedule-поля правил

Добавить или формализовать:

- [ ] длину отчетного периода: 1, 2 или 3 месяца;
- [ ] день оплаты;
- [ ] смещение месяца оплаты относительно конца периода;
- [ ] правила первой ожидаемой даты и границы активности;
- [ ] валидацию допустимых комбинаций для обязательств.

Пример:

```text
VAT period: May-June
period length: 2 months
due date: July 15
```

#### 8E.2. Генерация ожидаемых периодов

- [ ] Генерировать периоды из schedule-полей, `start_date` и `end_date`.
- [ ] Не создавать транзакции при генерации ожиданий.
- [ ] Корректно обрабатывать неполные первый и последний периоды.

#### 8E.3. Сопоставление с оплатами

- [ ] Сравнивать expected periods с `ObligationPayment`.
- [ ] Определять статусы `paid`, `unpaid`, `overdue`.
- [ ] Сохранить прикладную проверку от двойной оплаты одного периода.
- [ ] Решить, нужно ли дополнительно закрепить инвариант ограничением БД.

#### 8E.4. Команда `/obligation_status`

Пример:

```text
Obligation status:

1. VAT | 2026-05-01..2026-06-30 | unpaid | due 2026-07-15
2. Bituach Leumi | 2026-06-01..2026-06-30 | paid
3. Income tax advance | 2026-04-01..2026-06-30 | overdue
```

На этапе 8E рассчитывается наличие и срок обязательства, но не его сумма.

## Дальнейший план

### Этап 8F. Transaction detail и ручная налоговая классификация

Сделать до VAT engine, потому что налоговые поля уже существуют, но пока не
могут быть удобно проверены и исправлены пользователем.

- [ ] `/transaction transaction_id`.
- [ ] Команда или пошаговый flow `/set_transaction_tax`.
- [ ] Просмотр и редактирование `vat_relevant`, `vat_rate`, `vat_included`,
  `vat_amount`, `amount_net`, `business_use_percent`, `tax_deductible`,
  `tax_category`.
- [ ] Проверки согласованности total/net/VAT.
- [ ] Явное подтверждение изменений.
- [ ] Тесты прав доступа: пользователь изменяет только свои операции.

### Этап 8G. Basic VAT estimate

- [ ] Поддержать период или диапазон дат.
- [ ] Для `osek_murshe`: output VAT минус допустимый input VAT.
- [ ] Учитывать `business_use_percent` и `tax_deductible`.
- [ ] Для `osek_patur` возвращать ясное сообщение о неприменимости обычного
  VAT report.
- [ ] Добавить `/vat_report`.

Первый вариант является estimate по классифицированным транзакциям, а не
официальным расчетом декларации.

### Этап 8H. Income tax reserve

- [ ] Рассчитать taxable business profit за период.
- [ ] Применить `income_tax_reserve_percent`.
- [ ] Добавить `/income_tax_reserve`.
- [ ] Не моделировать на этом этапе полную официальную налоговую формулу.

### Этап 8I. Bituach Leumi reserve

- [ ] Рассчитать простой резерв от taxable business profit.
- [ ] Применить `bituach_leumi_reserve_percent`.
- [ ] Позже заменить простой процент на отдельный tiered calculation.

### Этап 8J. Tax summary

- [ ] Добавить `/tax_summary`.
- [ ] Показать VAT estimate, income tax reserve и Bituach Leumi reserve.
- [ ] Показать общий estimated reserve.
- [ ] Добавить paid/unpaid/overdue obligations по выбранному периоду.
- [ ] Явно маркировать результат как предварительный.

### Этап 9. Personal balance и budget

#### 9A. Personal spending reconciliation

- [ ] После дохода предложить сверить текущий банковский баланс или сумму
  личных трат.
- [ ] Рассчитывать агрегированные личные расходы:

```text
previous balance + income - new balance = personal spending
```

- [ ] Сохранять агрегированную expense-транзакцию с
  `balance_impact_type=personal`.
- [ ] Считать средние личные траты за неделю и месяц.

#### 9B. Available to spend

- [ ] Добавить safety buffer в профиль или настройки бюджета.
- [ ] Добавить `/available`.
- [ ] Учесть текущий баланс, unpaid/overdue obligations, налоговые резервы,
  ближайшие `auto_pay` и safety buffer.
- [ ] Не вычитать `reserve_only` дважды.

```text
available =
current balance
- unpaid/overdue obligations
- tax reserves
- upcoming auto-pay
- safety buffer
```

### Этап 10. AI business expense advisor

- [ ] `/can_deduct <описание>`.
- [ ] Тот же flow для OCR-документа.
- [ ] AI объясняет и предлагает `tax_deductible` и
  `business_use_percent`.
- [ ] Пользователь подтверждает или исправляет предложение.
- [ ] Ответ содержит предупреждение о необходимости проверки с бухгалтером.

AI не принимает окончательное налоговое решение автоматически.

### Этап 11. AI rule creation

- [ ] `/add_rule <свободный текст>`.
- [ ] Преобразование текста в structured recurring rule.
- [ ] Preview и подтверждение перед сохранением.
- [ ] Поддержка payment behavior, obligation type и schedule-полей.
- [ ] До этого этапа правила создаются через надежный bootstrap/YAML flow.

### Этап 12. Reports

- [ ] `/month_report`.
- [ ] `/category_report`.
- [ ] `/tax_report`.
- [ ] `/personal_spending_report`.
- [ ] `/documents_without_transactions`.
- [ ] `/transactions_without_documents`.
- [ ] CSV/XLSX export после стабилизации схемы данных.

### Этап 13. Hardening

- [ ] Зашифрованные бэкапы и проверенный restore.
- [ ] Audit log.
- [ ] Soft delete.
- [ ] Admin diagnostics.
- [ ] Улучшенные пользовательские ошибки.
- [ ] Проверка утечек персональных данных в логах и AI-запросах.

## Критерий ближайшего релиза

Ближайший законченный инкремент — этап 8E:

1. Правило обязательства описывает периодичность и due date.
2. Система строит ожидаемые периоды.
3. Периоды сопоставляются с фактическими оплатами.
4. `/obligation_status` показывает `paid`, `unpaid` и `overdue`.
5. Налоговые суммы на этом этапе не рассчитываются.

После этого работа переходит к 8F, и только затем к VAT engine.
