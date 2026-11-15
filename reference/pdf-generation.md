# Справочник: от данных до PDF-документа

Материал собран по практике проекта. Примеры путей относительные, команды
запускаются из корня проекта.

## 1. HTML и CSS для печати

### Страница

```css
@page {
  size: A4;
  margin: 18mm 16mm 20mm 16mm;
}
```

`@page` задаёт формат и поля страницы. Для печатного документа удобнее
миллиметры, а не пиксели: они не зависят от экрана. WeasyPrint поддерживает
`@page` широко; xhtml2pdf — частично. Сложные колонтитулы и именованные
страницы лучше проверять на конкретном движке.

### Таблица

```html
<table class="items">
  <thead>
    <tr><th>№</th><th>Наименование</th><th>Сумма</th></tr>
  </thead>
  <tbody>
    <tr><td>1</td><td>Товар</td><td>100,00</td></tr>
  </tbody>
</table>
```

```css
.items {
  width: 100%;
  border-collapse: collapse;
}
.items th,
.items td {
  padding: 6pt;
  border: 1px solid #bcccdc;
  vertical-align: top;
}
```

Для стабильной ширины колонок задавайте проценты через классы. Помните,
что `border-collapse` и `table-layout` xhtml2pdf может проигнорировать:
таблица всё равно отрисуется, но линии могут выглядеть иначе.

### Перенос длинных строк

```css
.items td {
  word-wrap: break-word;
  overflow-wrap: break-word;
}
```

Длинное слово без пробелов иначе растянет ячейку. Проверяйте PDF с реальным
длинным названием, а не только с коротким тестовым.

### Что избегать в шаблоне для xhtml2pdf

- flexbox и grid;
- сложные CSS-селекторы и псевдоэлементы;
- тени, градиенты, анимации;
- абсолютное позиционирование для основного содержимого;
- несколько вложенных таблиц без необходимости.

WeasyPrint поддерживает больше CSS, но шаблон должен оставаться рабочим
в обоих движках, если нужен fallback.

## 2. Jinja2

### Переменные и циклы

```html
<h1>Счёт № {{ invoice_id }}</h1>
<p>Покупатель: {{ customer_name }}</p>

<table>
  {% for item in items %}
  <tr>
    <td>{{ loop.index }}</td>
    <td>{{ item.product }}</td>
    <td>{{ item.qty }}</td>
    <td>{{ format_money(item.price) }}</td>
  </tr>
  {% endfor %}
</table>
```

`loop.index` начинается с 1, `loop.index0` — с 0. Внутри цикла доступны
поля объекта `item`.

### Автоэкранирование

```python
from jinja2 import Environment, FileSystemLoader

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=True,
)
template = env.get_template("invoice.html")
html = template.render(invoice_id="INV-1", customer_name="<script>alert(1)</script>")
```

При `autoescape=True` опасные символы заменяются HTML-сущностями.
Не применяйте фильтр `|safe` к данным из CSV/JSON: он отключает защиту.

### Ошибки шаблона

`TemplateError` ловят и превращают в понятное сообщение. Синтаксическая
ошибка в шаблоне не должна выглядеть как трейсбек в консоли пользователя.

## 3. CSV в Python

### Чтение

```python
import csv

with open("data/invoices.csv", "r", encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle)
    for row in reader:
        print(row["invoice_id"], row["price"])
```

- `utf-8-sig` убирает BOM, который иногда добавляет Excel.
- `newline=""` обязателен для корректной работы `csv` с переносами.
- `DictReader.fieldnames` позволяет проверить обязательные колонки.
- `reader.line_num` помогает указать номер проблемной строки.

### Группировка

CSV плоский, поэтому строки собирают по ключу:

```python
grouped = {}
for row in reader:
    invoice_id = row["invoice_id"].strip()
    invoice = grouped.setdefault(invoice_id, {"items": []})
    invoice["items"].append(row)
```

В проекте используется датакласс `Invoice`; при добавлении позиции
проверяется, что покупатель и дата у одного номера не различаются.

### Десятичная запятая

```python
from decimal import Decimal

def parse_money(text: str) -> Decimal:
    normalized = text.replace(" ", "").replace(",", ".")
    return Decimal(normalized)
```

В проекте разбор сложнее: поддерживаются пробелы между тысячами, точка
и запятая, а также проверяется, что после нормализации осталось число.
Перед `Decimal` полезно проверить строку регулярным выражением, иначе
`NaN` или `Infinity` могут пройти неожиданно.

## 4. JSON в Python

```python
import json

with open("data/orders.json", "r", encoding="utf-8-sig") as handle:
    data = json.load(handle)

records = data["invoices"] if isinstance(data, dict) else data
```

Поддерживаются два корневых варианта:

```json
[
  {"invoice_id": "INV-1", "items": []}
]
```

```json
{
  "invoices": [
    {"invoice_id": "INV-1", "items": []}
  ]
}
```

Проверяйте:

- корень — список или объект с ключом `invoices`;
- `items` — непустой список;
- обязательные поля есть и не пусты;
- `qty` — целое положительное число;
- `price` — число или строка с числом;
- номер счёта не повторяется.

`json.JSONDecodeError` содержит `lineno` и `colno` — их стоит показать
пользователю.

## 5. WeasyPrint

### Установка

```powershell
pip install weasyprint
```

На Windows также нужны GTK3/Pango. Без них импорт может упасть с ошибкой:

```text
OSError: cannot load library 'libgobject-2.0-0'
```

Вариант установки:

```powershell
winget install --id tschoonj.GTKForWindows
```

После установки откройте новый терминал.

### Рендеринг

```python
from pathlib import Path
from weasyprint import HTML

root = Path(".").resolve()
HTML(
    string=html_text,
    base_url=root.as_uri() + "/",
).write_pdf("output/result.pdf")
```

`base_url` важен для относительных ссылок: шрифтов, картинок, CSS.
Без корректного base URL `assets/DejaVuSans.ttf` может не найтись.

### Шрифты

WeasyPrint читает `@font-face` из CSS и умеет подключать локальные TTF.
Для кириллицы подойдёт DejaVu Sans. Если шрифт не найден, текст может
отрисоваться запасным шрифтом без нужных глифов.

## 6. xhtml2pdf

### Рендеринг

```python
from xhtml2pdf import pisa

with open("output/result.pdf", "wb") as destination:
    result = pisa.CreatePDF(
        src=html_text,
        dest=destination,
        path=".",
        encoding="utf-8",
    )

if result.err:
    raise RuntimeError(f"xhtml2pdf: {result.err} ошибок")
```

- `path` задаёт базовый каталог для относительных ресурсов.
- `encoding="utf-8"` нужен для кириллицы.
- `result.err` — счётчик ошибок; его обязательно проверять.
- Даже при `result.err == 0` полезно проверить, что файл начинается
  с `%PDF` и имеет ненулевой размер.

### Ограничения CSS

xhtml2pdf реализует подмножество CSS. В этом проекте он сообщал:

```text
Ignoring CSS properties xhtml2pdf does not implement:
border-collapse, table-layout
```

Это не ошибка рендеринга, но означает, что вёрстка может отличаться
от браузерной. Проверяйте таблицы, отступы и переносы на реальном PDF.

### @font-face

```css
@font-face {
  font-family: "DejaVu Sans";
  src: url("assets/DejaVuSans.ttf");
}

body {
  font-family: "DejaVu Sans", sans-serif;
}
```

Путь относительный. Он разрешается от каталога, переданного в `path`.
Если шрифт не найден, кириллица может стать пустыми квадратами.
В HTML-шаблоне проекта путь подставляется через `font_url`, но значение
по умолчанию остаётся относительным.

## 7. DejaVu Sans и лицензия

DejaVu Sans — свободный шрифт на основе Bitstream Vera. Он покрывает
кириллицу, латиницу, греческий алфавит и многие типографские символы.
Шрифт можно распространять вместе с проектом при соблюдении лицензии.

В проекте:

- `assets/DejaVuSans.ttf` — файл шрифта;
- `assets/LICENSE-DejaVu.txt` — текст лицензии;
- шаблон подключает шрифт через `@font-face`.

Не удаляйте лицензию при копировании проекта: она должна сопровождать
шрифт.

## 8. Decimal и деньги

```python
from decimal import Decimal, ROUND_HALF_UP

PRICE = Decimal("1250.00")
QTY = 3
TOTAL = (PRICE * QTY).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

Правила:

- не считать деньги через `float`;
- хранить цену как `Decimal`;
- округлять итог явно;
- форматировать только на выводе, не в расчётах;
- проверять конечность значения (`is_finite()`), чтобы отсечь `NaN`.

Форматирование с пробелами и запятой:

```python
def format_money(value: Decimal) -> str:
    text = f"{value:,.2f}"
    return text.replace(",", " ").replace(".", ",")
```

`1 234 567,50` читается привычнее в русском документе.

## 9. Открытие PDF по платформам

```python
import os
import subprocess
import sys

def open_pdf(path: str) -> bool:
    try:
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False
```

В реальном коде ошибку стоит вывести в stderr. Главное правило: неудача
автооткрытия не должна отменять уже созданный PDF.

## 10. Типичные ошибки

### Кракозябры вместо русского текста

Причины:

- файл прочитан не в UTF-8;
- PDF-движок не получил `encoding="utf-8"`;
- консоль Windows работает не в UTF-8;
- шрифт не содержит кириллицы.

Меры:

- `utf-8-sig` для CSV/JSON;
- явная кодировка в `CreatePDF`;
- `chcp 65001` и `PYTHONUTF8=1` в `run.cmd`;
- DejaVu Sans через `@font-face`;
- проверка извлечённого текста через `pypdf`.

### Таблица разъезжается или обрезается

Причины:

- слишком широкая колонка;
- длинное слово без переносов;
- сложный CSS, который движок игнорирует;
- вложенные таблицы.

Меры:

- фиксированные проценты ширины;
- `word-wrap` и `overflow-wrap`;
- простой шаблон;
- проверка на длинном названии.

### PDF пустой или отсутствует

Причины:

- `CreatePDF` вернул ошибку, но её не проверили;
- неверный путь к выходному файлу;
- нет прав на запись;
- движок не нашёл базовый каталог ресурсов.

Меры:

- проверять `result.err`;
- проверять сигнатуру `%PDF` и размер;
- создавать родительский каталог;
- передавать корректный `base_url`/`path`.

### Шрифт не найден

Причины:

- относительный путь не совпадает с `base_url`;
- файл шрифта не скопирован;
- имя семейства в CSS и `font-family` различаются.

Меры:

- держать `assets/DejaVuSans.ttf` рядом с проектом;
- использовать один и тот же относительный путь;
- проверять регистр имени файла на Linux.

### Ошибка WeasyPrint без GTK3

Это ожидаемая ситуация на чистой Windows. Не нужно маскировать её:
причина пишется в stderr, а PDF создаёт xhtml2pdf. Если нужен именно
WeasyPrint, установите GTK3 и перезапустите терминал.

## 11. Мини-чек-лист перед сдачей

- [ ] CSV и JSON читаются без ошибок.
- [ ] Обязательные колонки и структура проверяются.
- [ ] Цены и итоги считаются через `Decimal`.
- [ ] Кириллица видна в PDF и извлекается через `pypdf`.
- [ ] Длинное название не ломает таблицу.
- [ ] HTML из данных экранируется.
- [ ] Fallback пишет причину в stderr.
- [ ] PDF сохраняется в `output/` и не попадает в git.
- [ ] Тесты зелёные.
- [ ] В документах нет абсолютных локальных путей.
