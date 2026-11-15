# Карточка сдачи VPa06

## Ссылка на проект

https://github.com/IgorL0SEV/PDF_Check_Maker_progect

## Что сдаётся

- `pdf_generator.py` — CLI-генератор PDF;
- `templates/invoice.html` — HTML-шаблон с плейсхолдерами;
- `data/invoices.csv`, `data/orders.json` — тестовые данные;
- `assets/DejaVuSans.ttf` — шрифт с кириллицей;
- `README.md`, `CONSPECT.md`, `PLAN.md`, `SAMOPROVERKA.md`, `reference/`;
- `OFFER.md` — оффер для фриланс-биржи.

## Статус PDF-движков

Локально на Windows фактический движок — **xhtml2pdf**: GTK3 не установлен.
Ветка WeasyPrint проверена в CI на Ubuntu: workflow `.github/workflows/tests.yml`
прошёл, импорт WeasyPrint и генерация PDF движком `weasyprint` подтверждены.
Локальная проверка на Windows требует установки GTK3 и описана в README,
раздел «WeasyPrint и GTK3»:

1. Windows: `winget install --id tschoonj.GTKForWindows`, новое окно терминала,
   затем генерация PDF и проверка строки `Движок: weasyprint`.
2. Linux/CI: установить `libpango-1.0-0 libpangocairo-1.0-0 libcairo2`
   и прогнать `.github/workflows/tests.yml` или тесты вручную.

## Оффер

Автоматизирую создание PDF-документов для бизнеса: чеков, счетов, актов и
сертификатов. Вы присылаете образец документа и таблицу с данными — я настраиваю
шаблон и генератор, который за секунды создаёт готовые PDF без ручного
заполнения. Это убирает опечатки, экономит время и подходит для регулярной
отчётности. Готов адаптировать решение под ваш формат данных и фирменный стиль.
