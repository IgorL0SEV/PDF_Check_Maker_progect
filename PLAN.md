# План проекта и фактические проверки

## Предусловия

- Python 3.10 или новее. Проверка выполнена на Python 3.12.10.
- Доступ в интернет для установки пакетов из `requirements.txt`.
- Свободный шрифт DejaVu Sans и его лицензия в `assets/`.
- Для WeasyPrint на Windows — GTK3/Pango. В проверке GTK3 не было,
  поэтому фактически использовался резервный xhtml2pdf.

## Шаги

| Шаг | Результат | Статус |
|---|---|---|
| 1. Создать структуру проекта и окружение | `venv`, папки `data/`, `templates/`, `output/`, `assets/`, `tests/`, `reference/` | ✅ |
| 2. Подготовить синтетические данные | CSV из 5 строк и 2 счетов, JSON из 2 счетов | ✅ |
| 3. Написать HTML-шаблон | `templates/invoice.html` с Jinja2, `@page`, таблицей и итогом | ✅ |
| 4. Реализовать модели и загрузку CSV | `InvoiceItem`, `Invoice`, группировка, `Decimal`, ошибки | ✅ |
| 5. Реализовать загрузку JSON | Список и объект `invoices`, проверка структуры | ✅ |
| 6. Реализовать Jinja2-рендеринг | `render_html()`, автоэкранирование, `font_url` | ✅ |
| 7. Реализовать два PDF-движка | `render_pdf()`: WeasyPrint, затем xhtml2pdf | ✅ |
| 8. Реализовать CLI | Меню, `--data`, `--template`, `--invoice`, `--no-open`, `--list` | ✅ |
| 9. Реализовать безопасные имена и открытие | `safe_filename()`, `open_pdf()` | ✅ |
| 10. Написать тесты | 35 тестов `unittest` | ✅ |
| 11. Прогнать тесты | Зелёный прогон, 35 тестов | ✅ |
| 12. Выполнить сквозные запуски | CSV и JSON → PDF, извлечение текста | ✅ |
| 13. Проверить fallback | Причина WeasyPrint в stderr, движок xhtml2pdf | ✅ |
| 14. Проверить git | `.gitignore`, `git ls-files`, один коммит | ✅ |
| 15. Подготовить творческое задание | `OFFER.md` — 4 предложения для биржи | ✅ |
| 16. Подготовить проверку WeasyPrint | `SUBMISSION.md`, README и CI-workflow для Ubuntu; локально не запускалось | ✅ |

## Фактические проверки

### Окружение и зависимости

Установлены:

- Python 3.12.10;
- Jinja2 3.1.6;
- WeasyPrint 70.0.0 (импорт падает без GTK3);
- xhtml2pdf 0.2.28;
- pypdf 7.1.0 (зависимость xhtml2pdf, используется тестами).

### Тесты

Команда:

```powershell
python -m unittest discover -s tests -v
```

Результат фактического прогона: **35 тестов, все успешно**.

Тесты работают во временных папках, не обращаются к сети и не требуют
открывать PDF. Проверяются загрузка CSV/JSON, ошибки, Jinja2,
экранирование, безопасные имена, реальный PDF через `pypdf` и CLI.

### Сквозные запуски

CSV:

```powershell
python pdf_generator.py --data data/invoices.csv --template templates/invoice.html --invoice INV-2026-001 --no-open
```

Результат: `output/invoice_INV-2026-001.pdf`, движок `xhtml2pdf`.
Из PDF извлечён текст: номер `INV-2026-001`, покупатель `ООО «Ромашка»`,
позиции, кириллица и итог `11 236,50 ₽`.

JSON:

```powershell
python pdf_generator.py --data data/orders.json --template templates/invoice.html --invoice INV-2026-101 --no-open
```

Результат: `output/invoice_INV-2026-101.pdf`, движок `xhtml2pdf`.
Из PDF извлечены номер `INV-2026-101`, покупатель `ООО «Вектор»`,
позиции и итог `59 722,00 ₽`.

### Fallback

WeasyPrint при импорте выдаёт:

```text
OSError: cannot load library 'libgobject-2.0-0'
```

Программа печатает причину в stderr и продолжает через xhtml2pdf.
Оба сквозных запуска завершились кодом 0.

### Git

Проверено:

- `git status` — чистое дерево после коммита;
- `git ls-files` — без `venv/`, `output/*.pdf`, `__pycache__` и локального файла правил;
- remote не настроен, проект локальный.

## Что не проверено

- **WeasyPrint без GTK3.** Движок не запускался: на машине проверки нет
  библиотек GTK3. Код ветки написан, но фактический PDF сформирован
  только xhtml2pdf.
- **Автооткрытие PDF.** Функция реализована для Windows, macOS и Linux,
  но проверочные запуски использовали `--no-open`, чтобы не открывать
  окно просмотрщика. Ошибка открытия не роняет программу.
- **Визуальное сравнение движков.** xhtml2pdf игнорирует часть CSS
  (`border-collapse`, `table-layout`), поэтому вёрстка в WeasyPrint может
  отличаться. Сравнение не выполнялось.
- **Скриншоты.** Их делает пользователь при подготовке карточки сдачи.

## Runbook: продолжение на другой машине

1. Клонировать репозиторий:

```powershell
git clone <repo-url>
cd PDF_Check_Maker_progect
```

2. Создать окружение и установить зависимости:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Прогнать тесты:

```powershell
python -m unittest discover -s tests -v
```

Ожидается 35 успешных тестов.

4. Сделать пробный PDF:

```powershell
python pdf_generator.py --data data/invoices.csv --template templates/invoice.html --invoice INV-2026-001 --no-open
```

5. Проверить файл в `output/`. Если WeasyPrint недоступен, в stderr будет
   причина, а PDF всё равно создастся через xhtml2pdf.

6. Проверить ветку WeasyPrint. Возможны два пути.

   **Windows + GTK3:**

```powershell
winget install --id tschoonj.GTKForWindows
```

   Открыть новое окно терминала, проверить `python -c "import weasyprint"`
   и повторить генерацию. В выводе должно быть `Движок: weasyprint`.

   **Linux/CI:** установить `libpango-1.0-0 libpangocairo-1.0-0 libcairo2
   libgdk-pixbuf-2.0-0`, затем прогнать тесты и генерацию. В репозитории
   подготовлен workflow `.github/workflows/tests.yml`; он не запускался,
   пока remote не настроен.

## Риски и меры

| Риск | Последствие | Мера |
|---|---|---|
| Нет GTK3 | WeasyPrint не импортируется | Fallback на xhtml2pdf, причина в stderr |
| Разный CSS у движков | Вёрстка отличается | Простой шаблон, ограничения описаны в README и справочнике |
| Неверная кодировка CSV/JSON | Кракозябры или ошибка чтения | `utf-8-sig`, `PYTHONUTF8=1` в `run.cmd`, понятные сообщения |
| Ошибки округления денег | Неверный итог | `Decimal`, `ROUND_HALF_UP`, округление до копеек |
| Нет шрифта с кириллицей | Пустые символы в PDF | DejaVu Sans в `assets/`, `@font-face` с относительным путём |
| Потеря лицензии шрифта | Нарушение условий распространения | `assets/LICENSE-DejaVu.txt` рядом со шрифтом |
| Реальные данные в git | Утечка персональных данных | Только синтетические примеры, `output/*.pdf` в `.gitignore` |
| Слишком длинное название | Разрыв таблицы | `word-wrap`, `overflow-wrap`, простая ширина колонок |
| Неверный путь к данным | Падение с трейсбеком | `DataError`, проверка файла, код выхода 1 |

## Решения по реализации

- **Модели.** `InvoiceItem` и `Invoice` — датаклассы; итог — свойство
  `Invoice.total`.
- **Цены.** Хранятся как `Decimal`, округляются до `0.01`.
- **CSV.** `csv.DictReader`, `utf-8-sig`, группировка по `invoice_id`.
- **JSON.** Поддерживаются список и объект с ключом `invoices`.
- **Шаблон.** Jinja2 с `autoescape=True`, относительный путь к шрифту.
- **PDF.** Основной WeasyPrint, резервный xhtml2pdf, проверка `result.err`.
- **CLI.** Меню без аргументов; аргументы для автоматизации; ошибки
  возвращают код 1 без трейсбеков.
- **Имена файлов.** `safe_filename()` убирает недопустимые символы
  и переходы по папкам.
- **Открытие.** `os.startfile` в Windows, `open` в macOS, `xdg-open`
  в Linux; ошибки перехватываются.

## Git-политика

- Репозиторий инициализирован веткой `main`.
- Один осмысленный коммит на русском.
- Remote не добавлен, публикация не выполнялась.
- Локальный файл правил исключён через `.git/info/exclude`.
- `output/.gitkeep` сохранён, готовые PDF игнорируются.
