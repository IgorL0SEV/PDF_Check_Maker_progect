# PDF-чек-мейкер — курсовой проект (VPa06)

[![tests](https://github.com/IgorL0SEV/PDF_Check_Maker_progect/actions/workflows/tests.yml/badge.svg)](https://github.com/IgorL0SEV/PDF_Check_Maker_progect/actions/workflows/tests.yml)

CLI-приложение на Python: читает счета из CSV или JSON, подставляет данные
в HTML-шаблон Jinja2 и сохраняет готовый PDF в `output/`.

Проект учебный. В репозитории только синтетические данные; реальные счета
и персональные данные сюда не попадают.

> **Статус проверки:** локально на Windows фактический движок — xhtml2pdf:
> GTK3 нет. Ветка WeasyPrint проверена в CI на Ubuntu: workflow прошёл, PDF
> создан движком `weasyprint`. Локальная проверка на Windows — в разделе
> [«WeasyPrint и GTK3»](#weasyprint-и-gtk3).

## Что осваиваем

- HTML и CSS для печати: страница A4, таблицы, границы, переносы длинных строк.
- Шаблонизацию Jinja2: переменные, циклы, автоэкранирование.
- Загрузку и проверку данных из CSV и JSON.
- Денежные расчёты через `Decimal` без ошибок округления `float`.
- Два способа получить PDF из HTML: WeasyPrint и xhtml2pdf.
- Резервный сценарий (fallback), когда основной движок недоступен.
- CLI с интерактивным меню и аргументами для автоматизации.
- Модульные тесты без сети и без внешних сервисов.

## Возможности

- **Два формата данных:** CSV с группировкой строк по номеру счёта и JSON
  в виде списка или объекта с ключом `invoices`.
- **Гибкий шаблон:** номер счёта, покупатель, дата, таблица позиций,
  количество, цена, сумма по строке и итог.
- **Понятные ошибки:** пропущенная колонка, битое число, пустой файл,
  неверная структура JSON — сообщение с местом ошибки, без трейсбека.
- **Русские суммы:** пробелы между тысячами и десятичная запятая.
- **Два PDF-движка:** сначала WeasyPrint, затем xhtml2pdf.
- **Кириллица в PDF:** встроенный свободный шрифт DejaVu Sans.
- **Интерактивное меню:** выбор файла данных, счёта и шаблона по номеру.
- **Автоматизация:** запуск одной командой через `--data`, `--template`,
  `--invoice` и `--no-open`.
- **Автооткрытие:** готовый PDF открывается программой по умолчанию;
  в проверочных запусках использовался `--no-open`.

## Структура

```text
PDF_Check_Maker_progect/
├── pdf_generator.py              # загрузка данных, Jinja2, PDF, CLI
├── requirements.txt              # Jinja2, weasyprint, xhtml2pdf
├── run.cmd                       # venv + зависимости + запуск
├── .gitignore
├── README.md
├── CONSPECT.md                   # аннотация темы курса
├── PLAN.md                       # шаги, runbook, риски
├── SAMOPROVERKA.md               # вопросы и ответы
├── OFFER.md                       # оффер для фриланс-биржи
├── SUBMISSION.md                  # карточка сдачи
├── .github/workflows/tests.yml    # CI-проверка WeasyPrint на Ubuntu
├── reference/
│   └── pdf-generation.md         # справочник по HTML→PDF
├── assets/
│   ├── DejaVuSans.ttf            # шрифт с кириллицей
│   └── LICENSE-DejaVu.txt        # лицензия шрифта
├── templates/
│   └── invoice.html              # Jinja2-шаблон счёта
├── data/
│   ├── invoices.csv              # 5 строк, 2 счёта
│   └── orders.json               # 2 счёта в JSON
├── output/
│   ├── .gitkeep
│   └── *.pdf                     # результат, в git не попадает
└── tests/
    └── test_pdf_generator.py     # 35 тестов unittest
```

## Быстрый старт

### Windows: один клик

Двойной клик по `run.cmd`. Скрипт создаст `venv` при первом запуске,
установит зависимости и откроет меню приложения.

### Вручную

```powershell
cd PDF_Check_Maker_progect
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python pdf_generator.py
```

В Linux и macOS активация другая:

```bash
source venv/bin/activate
python pdf_generator.py
```

Без аргументов открывается меню:

1. Выберите файл данных из `data/`.
2. Выберите счёт из списка.
3. Выберите HTML-шаблон из `templates/`.
4. Программа создаст PDF в `output/`, напечатает путь и имя движка.

Для выхода из меню введите `q`.

## Запуск без меню

Полный набор аргументов создаёт один PDF:

```powershell
python pdf_generator.py --data data/invoices.csv --template templates/invoice.html --invoice INV-2026-001 --no-open
```

Второй счёт из CSV:

```powershell
python pdf_generator.py --data data/invoices.csv --template templates/invoice.html --invoice INV-2026-002 --no-open
```

Счёт из JSON:

```powershell
python pdf_generator.py --data data/orders.json --template templates/invoice.html --invoice INV-2026-101 --no-open
```

Посмотреть доступные файлы и счета:

```powershell
python pdf_generator.py --list
```

Аргументы:

| Аргумент | Назначение |
|---|---|
| `--data` | путь к CSV или JSON |
| `--template` | путь к HTML-шаблону |
| `--invoice` | номер счёта, например `INV-2026-001` |
| `--no-open` | не открывать PDF автоматически |
| `--list` | показать файлы данных, шаблоны и счета |

Для автоматического режима нужны все три аргумента: `--data`, `--template`
и `--invoice`. Если чего-то не хватает, программа объяснит это и вернёт код 1.

## Результат

PDF сохраняется в `output/` с именем:

```text
<имя-шаблона>_<номер-счёта>.pdf
```

Например:

```text
output/invoice_INV-2026-001.pdf
```

Номер счёта и имя шаблона проходят через `safe_filename()`: запрещённые
для Windows символы заменяются, переходы вида `../` не создаются.

## Как работает fallback

Порядок такой:

1. Программа пытается импортировать WeasyPrint и отрендерить PDF.
2. Если импорт или рендеринг падает, причина печатается в stderr.
3. Управление переходит к xhtml2pdf.
4. Функция возвращает имя движка: `weasyprint` или `xhtml2pdf`.
5. Если не сработал ни один движок, поднимается `PDFGenerationError`
   с причинами обеих попыток.

Фактический вывод на машине без GTK3:

```text
WeasyPrint недоступен, переключаюсь на xhtml2pdf. Причина: OSError: cannot load library 'libgobject-2.0-0' ...
```

PDF при этом создаётся через xhtml2pdf. Это не ошибка проекта, а ожидаемый
резервный сценарий.

## WeasyPrint и GTK3

WeasyPrint на Windows требует библиотеки GTK3/Pango. Без них импорт падает
с `OSError` про `libgobject-2.0-0`.

**Текущий статус проверки:** локально на Windows GTK3 нет, поэтому
фактический движок — **xhtml2pdf**. Ветка WeasyPrint проверена в CI на Ubuntu:
workflow установил библиотеки, импорт WeasyPrint прошёл, тесты и генерация PDF
завершились с движком `weasyprint`. Локальная проверка на Windows всё ещё
требует установки GTK3; тест принимает любой из двух движков.

Проверить WeasyPrint локально можно двумя способами.

### Вариант 1. Установить GTK3 на Windows

1. Установить GTK3 Runtime:

```powershell
winget install --id tschoonj.GTKForWindows
```

Подойдёт и установщик GTK3 Runtime для Windows с официальной страницы проекта
GTK. Это системный компонент, установка требует прав администратора.

2. Закрыть все окна терминала и открыть новое: установщик обновляет `PATH`.
3. Проверить импорт в окружении проекта:

```powershell
.\venv\Scripts\python.exe -c "import weasyprint; print(weasyprint.__version__)"
```

4. Сгенерировать PDF и посмотреть, какой движок сработал:

```powershell
.\venv\Scripts\python.exe pdf_generator.py --data data/invoices.csv --template templates/invoice.html --invoice INV-2026-001 --no-open
```

В выводе должно быть `Движок: weasyprint`. Полезно сравнить этот PDF с тем,
что был создан через xhtml2pdf: вёрстка может немного отличаться.

5. Прогнать тесты:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Вариант 2. Проверить в Linux или CI

В Linux Pango и Cairo ставятся системными пакетами, отдельный GTK3 Runtime
не нужен. В репозитории подготовлен workflow `.github/workflows/tests.yml`:
он устанавливает библиотеки, зависимости Python, проверяет импорт WeasyPrint,
прогоняет тесты и убеждается, что сгенерированный PDF сделан движком
`weasyprint`.

Workflow запускается на GitHub Actions при push и уже прошёл: импорт
WeasyPrint, тесты и проверка `Движок: weasyprint` — успешно. Вручную на Ubuntu
команды те же:

```bash
sudo apt-get update
sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python pdf_generator.py --data data/invoices.csv --template templates/invoice.html --invoice INV-2026-001 --no-open
```

В выводе последней команды должен быть `Движок: weasyprint`. Этот способ
не меняет Windows-окружение и даёт автоматическое доказательство того, что
основная ветка работает.

## Ограничения xhtml2pdf

xhtml2pdf понимает подмножество HTML и CSS, а не весь современный CSS:

- нет flexbox и grid;
- ограниченная поддержка сложных селекторов, теней, градиентов и анимаций;
- часть свойств игнорируется, например `border-collapse` и `table-layout`;
- `@page` поддерживается частично;
- шрифты подключаются через `@font-face` и TTF-файл;
- сложная вёрстка может отличаться от той, что показывает браузер.

Поэтому шаблон намеренно простой: таблицы, базовые отступы, границы,
цвета и один встроенный шрифт. Для сложных документов лучше установить GTK3
и использовать WeasyPrint.

## Шрифт и лицензия

`assets/DejaVuSans.ttf` — свободный шрифт DejaVu Sans. Он покрывает кириллицу,
латиницу и основные типографские символы. Лицензия лежит в
`assets/LICENSE-DejaVu.txt` и распространяется вместе с проектом.

В шаблоне шрифт подключён относительным путём:

```css
@font-face {
  font-family: "DejaVu Sans";
  src: url("assets/DejaVuSans.ttf");
}
```

## Тесты

```powershell
python -m unittest discover -s tests -v
```

Проверяются:

- группировка строк CSV и расчёт итогов;
- десятичная запятая и пробелы между тысячами;
- отсутствующие колонки, битые числа, пустой файл;
- JSON-список и JSON-объект, ошибки структуры;
- подстановка данных, цикл и экранирование `<script>`;
- безопасное имя файла;
- создание настоящего PDF: сигнатура `%PDF`, размер, извлечение текста
  с кириллицей и номером счёта;
- fallback на xhtml2pdf с причиной в stderr;
- CLI с `--no-open` для CSV и JSON, коды возврата и отсутствие трейсбеков.

Тесты используют `pypdf` для чтения готового PDF. `pypdf` приходит
как зависимость xhtml2pdf, отдельно устанавливать его не нужно.

## Соответствие заданию

| Требование | Где в проекте |
|---|---|
| CLI на Python | `pdf_generator.py` |
| CSV с двумя счетами, 3–5 строк | `data/invoices.csv`: 5 строк, 2 счёта |
| HTML-шаблон с подстановками и циклом | `templates/invoice.html` |
| Сохранение PDF в `output/` | `output/invoice_<номер>.pdf` |
| Автооткрытие PDF | `open_pdf()`; в проверках использовался `--no-open` |
| Понятные ошибки без трейсбеков | `DataError`, `PDFGenerationError`, обработка в `main()` |
| Тесты | `tests/test_pdf_generator.py`, 35 тестов |
| Документация | `README.md`, `CONSPECT.md`, `PLAN.md`, `SAMOPROVERKA.md`, `reference/` |
| Ссылка на GitHub | https://github.com/IgorL0SEV/PDF_Check_Maker_progect |
| Оффер для сдачи | `OFFER.md` — 4 предложения для карточки услуги |
| Статус PDF-движка | `SUBMISSION.md`: локально xhtml2pdf, WeasyPrint проверен в CI на Ubuntu |

Скриншоты интерфейса и готового PDF делает пользователь: в репозиторий они
не добавляются автоматически.

## Творческое задание: оффер

Короткое описание услуги для фриланс-биржи лежит в `OFFER.md`: что предлагается,
кому полезно и какое преимущество даёт автоматизация. Текст можно приложить
комментарием к сдаче или использовать как основу карточки услуги.

## Ограничения проекта

- Локально на Windows без GTK3 фактический движок — xhtml2pdf; WeasyPrint
  проверен в CI на Ubuntu, локальная Windows-проверка требует установки GTK3.
- Вёрстка рассчитана на один счёт на документ; пакетная генерация
  нескольких PDF за один запуск не реализована.
- Поддерживаются только CSV и JSON; Excel и базы данных не подключены.
- Автооткрытие зависит от настроек операционной системы и ассоциации PDF.
- Реальные персональные данные в примерах не используются.

## Если что-то не работает

| Симптом | Что делать |
|---|---|
| `ModuleNotFoundError: No module named 'jinja2'` | Запущен Python без venv. Активируйте `venv` или используйте `run.cmd` |
| PDF не создаётся, в stderr ошибка WeasyPrint | Это ожидаемо без GTK3; должна сработать резервная ветка xhtml2pdf |
| В PDF нет кириллицы | Проверьте, что `assets/DejaVuSans.ttf` на месте и шаблон ссылается на него |
| В консоли кракозябры | Запускайте через `run.cmd` или включите UTF-8: `chcp 65001` |
| `Счёт ... не найден` | Посмотрите доступные номера через `--list` |
| PDF не открылся сам | Файл уже создан; откройте его из `output/` вручную |
| Тесты не находят `pypdf` | Установите зависимости из `requirements.txt`; `pypdf` приходит с xhtml2pdf |

## Документация

- `CONSPECT.md` — краткая аннотация темы курса своими словами.
- `PLAN.md` — план, фактические проверки, runbook и риски.
- `SAMOPROVERKA.md` — 17 вопросов для самопроверки с ответами.
- `OFFER.md` — оффер для фриланс-биржи.
- `SUBMISSION.md` — карточка сдачи с фактическим статусом PDF-движка.
- `reference/pdf-generation.md` — справочник по HTML, Jinja2, CSV/JSON,
  WeasyPrint, xhtml2pdf, шрифтам и типичным ошибкам.
