"""Генератор PDF-счетов из CSV или JSON по HTML-шаблону.

Запуск без аргументов открывает интерактивное меню. Для автоматизации
предусмотрены аргументы --data, --template, --invoice, --no-open и --list.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Sequence

from jinja2 import Environment, FileSystemLoader, TemplateError

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output"

MONEY_QUANT = Decimal("0.01")
FONT_URL = "assets/DejaVuSans.ttf"
REQUIRED_CSV_COLUMNS = (
    "invoice_id",
    "customer_name",
    "date",
    "product",
    "qty",
    "price",
)
DATA_SUFFIXES = {".csv", ".json"}
TEMPLATE_SUFFIXES = {".html", ".htm"}
PRICE_PATTERN = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
QTY_PATTERN = re.compile(r"^\+?\d+$")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class PdfCheckError(Exception):
    """Базовая ошибка проекта с понятным пользователю сообщением."""


class DataError(PdfCheckError):
    """Ошибка чтения или проверки исходных данных."""


class PDFGenerationError(PdfCheckError):
    """Не удалось сформировать PDF ни одним из движков."""


@dataclass(frozen=True)
class InvoiceItem:
    """Одна позиция счёта."""

    product: str
    qty: int
    price: Decimal

    @property
    def line_total(self) -> Decimal:
        """Стоимость позиции с округлением до копеек."""
        return (self.price * self.qty).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


@dataclass
class Invoice:
    """Счёт с набором позиций."""

    invoice_id: str
    customer_name: str
    date: str
    items: list[InvoiceItem] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        """Итоговая сумма счёта с округлением до копеек."""
        amount = sum((item.line_total for item in self.items), Decimal("0.00"))
        return amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def init_directories() -> None:
    """Создаёт рабочие папки проекта, если их ещё нет."""
    for folder in (DATA_DIR, TEMPLATES_DIR, OUTPUT_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def format_money(amount: Decimal | int | str) -> str:
    """Форматирует сумму с двумя знаками, пробелами тысяч и запятой."""
    if isinstance(amount, bool):
        raise ValueError("Сумма не может быть логическим значением")
    if isinstance(amount, Decimal):
        value = amount
    else:
        value = Decimal(str(amount))
    if not value.is_finite():
        raise ValueError("Сумма должна быть конечным числом")
    value = value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    formatted = f"{value:,.2f}"
    return formatted.replace(",", " ").replace(".", ",")


def _required_text(value: object, location: str) -> str:
    if value is None:
        raise DataError(f"{location}: обязательное поле не заполнено")
    if not isinstance(value, str):
        raise DataError(f"{location}: ожидается текст, получено {type(value).__name__}")
    text = value.strip()
    if not text:
        raise DataError(f"{location}: обязательное поле не заполнено")
    return text


def _parse_date(value: object, location: str) -> str:
    text = _required_text(value, location)
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise DataError(
            f"{location}: дата «{text}» должна быть в формате ГГГГ-ММ-ДД"
        ) from exc
    return text


def _parse_qty(value: object, location: str) -> int:
    if isinstance(value, bool):
        raise DataError(f"{location}: количество должно быть целым числом")
    if isinstance(value, int):
        qty = value
    elif isinstance(value, str):
        text = value.strip()
        if not QTY_PATTERN.fullmatch(text):
            raise DataError(f"{location}: количество «{value}» должно быть целым числом")
        qty = int(text)
    else:
        raise DataError(f"{location}: количество должно быть целым числом")
    if qty <= 0:
        raise DataError(f"{location}: количество должно быть больше нуля")
    return qty


def _parse_price(value: object, location: str) -> Decimal:
    """Разбирает цену, поддерживая точку, запятую и пробелы между тысячами."""
    if isinstance(value, bool) or value is None:
        raise DataError(f"{location}: цена должна быть числом")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise DataError(f"{location}: цена должна быть числом")

    if not text:
        raise DataError(f"{location}: цена не указана")

    normalized = re.sub(r"[\s\u00a0\u202f]", "", text)
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        if normalized.count(",") != 1:
            raise DataError(f"{location}: цена «{text}» содержит несколько запятых")
        normalized = normalized.replace(",", ".")

    if not PRICE_PATTERN.fullmatch(normalized):
        raise DataError(f"{location}: цена «{text}» не является числом")

    try:
        price = Decimal(normalized)
    except InvalidOperation as exc:
        raise DataError(f"{location}: цена «{text}» не является числом") from exc
    if not price.is_finite():
        raise DataError(f"{location}: цена должна быть конечным числом")
    if price < 0:
        raise DataError(f"{location}: цена не может быть отрицательной")
    return price.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _append_csv_row(grouped: dict[str, Invoice], row: dict[str, str], line: int) -> None:
    where = f"Строка {line}"
    invoice_id = _required_text(row.get("invoice_id"), f"{where}, invoice_id")
    customer = _required_text(row.get("customer_name"), f"{where}, customer_name")
    date = _parse_date(row.get("date"), f"{where}, date")
    product = _required_text(row.get("product"), f"{where}, product")
    qty = _parse_qty(row.get("qty"), f"{where}, qty")
    price = _parse_price(row.get("price"), f"{where}, price")

    item = InvoiceItem(product=product, qty=qty, price=price)
    existing = grouped.get(invoice_id)
    if existing is None:
        grouped[invoice_id] = Invoice(
            invoice_id=invoice_id,
            customer_name=customer,
            date=date,
            items=[item],
        )
        return
    if existing.customer_name != customer:
        raise DataError(
            f"{where}: у счёта «{invoice_id}» различается покупатель "
            f"(«{existing.customer_name}» и «{customer}»)"
        )
    if existing.date != date:
        raise DataError(
            f"{where}: у счёта «{invoice_id}» различаются даты "
            f"(«{existing.date}» и «{date}»)"
        )
    existing.items.append(item)


def load_csv_invoices(path: str | Path) -> list[Invoice]:
    """Загружает счета из CSV и группирует позиции по invoice_id."""
    data_path = Path(path)
    grouped: dict[str, Invoice] = {}

    try:
        with data_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise DataError(f"Файл данных «{data_path}» пуст")
            missing = [name for name in REQUIRED_CSV_COLUMNS if name not in reader.fieldnames]
            if missing:
                raise DataError(
                    "В CSV не хватает обязательных колонок: "
                    + ", ".join(missing)
                    + ". Ожидаются: "
                    + ", ".join(REQUIRED_CSV_COLUMNS)
                )

            for row in reader:
                if row is None:
                    continue
                values = [value for value in row.values() if value is not None]
                if not values or all(not str(value).strip() for value in values):
                    continue
                _append_csv_row(grouped, row, reader.line_num)
    except UnicodeDecodeError as exc:
        raise DataError(
            f"Файл «{data_path}» должен быть сохранён в кодировке UTF-8"
        ) from exc
    except csv.Error as exc:
        raise DataError(f"Не удалось разобрать CSV «{data_path}»: {exc}") from exc
    except OSError as exc:
        raise DataError(f"Не удалось прочитать файл «{data_path}»: {exc}") from exc

    if not grouped:
        raise DataError(f"Файл «{data_path}» не содержит ни одной позиции счёта")
    return sorted(grouped.values(), key=lambda invoice: invoice.invoice_id.casefold())


def _build_json_invoice(record: object, index: int) -> Invoice:
    where = f"Запись {index}"
    if not isinstance(record, dict):
        raise DataError(f"{where}: ожидается объект счёта")
    invoice_id = _required_text(record.get("invoice_id"), f"{where}, invoice_id")
    where = f"Счёт «{invoice_id}»"
    customer = _required_text(record.get("customer_name"), f"{where}, customer_name")
    date = _parse_date(record.get("date"), f"{where}, date")
    raw_items = record.get("items")
    if not isinstance(raw_items, list):
        raise DataError(f"{where}: поле items должно быть списком позиций")
    if not raw_items:
        raise DataError(f"{where}: список позиций пуст")

    items: list[InvoiceItem] = []
    for item_index, raw_item in enumerate(raw_items, start=1):
        item_where = f"{where}, позиция {item_index}"
        if not isinstance(raw_item, dict):
            raise DataError(f"{item_where}: ожидается объект позиции")
        product = _required_text(raw_item.get("product"), f"{item_where}, product")
        qty = _parse_qty(raw_item.get("qty"), f"{item_where}, qty")
        price = _parse_price(raw_item.get("price"), f"{item_where}, price")
        items.append(InvoiceItem(product=product, qty=qty, price=price))

    return Invoice(
        invoice_id=invoice_id,
        customer_name=customer,
        date=date,
        items=items,
    )


def load_json_invoices(path: str | Path) -> list[Invoice]:
    """Загружает счета из JSON-списка или объекта с ключом invoices."""
    data_path = Path(path)
    try:
        text = data_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataError(
            f"Файл «{data_path}» должен быть сохранён в кодировке UTF-8"
        ) from exc
    except OSError as exc:
        raise DataError(f"Не удалось прочитать файл «{data_path}»: {exc}") from exc

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataError(
            f"Некорректный JSON в «{data_path}»: "
            f"строка {exc.lineno}, колонка {exc.colno}: {exc.msg}"
        ) from exc

    if isinstance(raw, dict):
        if "invoices" not in raw:
            raise DataError("JSON-объект должен содержать ключ «invoices»")
        records = raw["invoices"]
    elif isinstance(raw, list):
        records = raw
    else:
        raise DataError("JSON должен содержать список счетов или объект с ключом «invoices»")

    if not isinstance(records, list):
        raise DataError("Ключ «invoices» должен содержать список счетов")
    if not records:
        raise DataError(f"Файл «{data_path}» не содержит ни одного счёта")

    invoices: list[Invoice] = []
    seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        invoice = _build_json_invoice(record, index)
        if invoice.invoice_id in seen:
            raise DataError(f"Счёт «{invoice.invoice_id}» встречается в JSON несколько раз")
        seen.add(invoice.invoice_id)
        invoices.append(invoice)
    return sorted(invoices, key=lambda invoice: invoice.invoice_id.casefold())


def load_invoices(path: str | Path) -> list[Invoice]:
    """Выбирает способ загрузки по расширению файла."""
    data_path = Path(path)
    if not data_path.is_file():
        raise DataError(f"Файл данных не найден: «{data_path}»")
    suffix = data_path.suffix.lower()
    if suffix == ".csv":
        return load_csv_invoices(data_path)
    if suffix == ".json":
        return load_json_invoices(data_path)
    raise DataError(
        f"Неподдерживаемый формат данных «{suffix or 'без расширения'}». "
        "Используйте CSV или JSON."
    )


def _files_in(folder: Path, suffixes: set[str]) -> list[Path]:
    """Возвращает отсортированные файлы только из указанной папки."""
    if not folder.is_dir():
        return []
    root = folder.resolve()
    found: list[Path] = []
    for candidate in folder.iterdir():
        try:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if resolved.suffix.lower() in suffixes:
            found.append(candidate)
    return sorted(found, key=lambda item: item.name.casefold())


def list_data_files() -> list[Path]:
    """Файлы CSV и JSON в папке data."""
    return _files_in(DATA_DIR, DATA_SUFFIXES)


def list_templates() -> list[Path]:
    """HTML-шаблоны в папке templates."""
    return _files_in(TEMPLATES_DIR, TEMPLATE_SUFFIXES)


def list_invoices(data_path: str | Path) -> list[Invoice]:
    """Счета из выбранного файла данных, отсортированные по номеру."""
    return load_invoices(data_path)


def safe_filename(text: str) -> str:
    """Превращает номер счёта в безопасное имя файла без переходов по папкам."""
    cleaned = "".join(
        char if (char.isalnum() or char in "._-") else "_"
        for char in str(text).strip()
    )
    cleaned = re.sub(r"_+", "_", cleaned).strip(" ._-")
    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"{cleaned}_file"
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip(" ._-")
    return cleaned or "invoice"


def render_html(template_path: str | Path, invoice: Invoice) -> str:
    """Рендерит HTML-шаблон с данными счёта и включённым автоэкранированием."""
    path = Path(template_path)
    if not path.is_file():
        raise DataError(f"Шаблон не найден: «{path}»")
    environment = Environment(
        loader=FileSystemLoader(str(path.parent)),
        autoescape=True,
    )
    try:
        template = environment.get_template(path.name)
        return template.render(
            invoice=invoice,
            invoice_id=invoice.invoice_id,
            customer_name=invoice.customer_name,
            date=invoice.date,
            items=invoice.items,
            total=format_money(invoice.total),
            font_url=FONT_URL,
            format_money=format_money,
        )
    except TemplateError as exc:
        raise DataError(f"Ошибка шаблона «{path}»: {exc}") from exc


def _looks_like_pdf(path: Path) -> bool:
    try:
        if path.stat().st_size <= 0:
            return False
        with path.open("rb") as handle:
            return handle.read(4) == b"%PDF"
    except OSError:
        return False


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def render_pdf(
    html_text: str,
    output_path: str | Path,
    base_dir: str | Path,
) -> str:
    """Сохраняет HTML в PDF: WeasyPrint, затем резервный xhtml2pdf.

    Возвращает имя сработавшего движка. Если не сработал ни один,
    поднимает PDFGenerationError.
    """
    target = Path(output_path)
    base = Path(base_dir).resolve()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PDFGenerationError(f"Не удалось создать папку для PDF: {exc}") from exc

    weasy_reason = "неизвестная ошибка"
    try:
        from weasyprint import HTML  # type: ignore import-not-found

        _remove_file(target)
        HTML(string=html_text, base_url=base.as_uri() + "/").write_pdf(str(target))
        if not _looks_like_pdf(target):
            raise RuntimeError("WeasyPrint не создал корректный PDF")
        return "weasyprint"
    except Exception as exc:  # импорт WeasyPrint может падать без GTK3
        weasy_reason = f"{type(exc).__name__}: {exc}"
        print(
            "WeasyPrint недоступен, переключаюсь на xhtml2pdf. "
            f"Причина: {weasy_reason}",
            file=sys.stderr,
        )
        _remove_file(target)

    try:
        from xhtml2pdf import pisa  # type: ignore import-not-found

        with target.open("wb") as destination:
            result = pisa.CreatePDF(
                src=html_text,
                dest=destination,
                path=str(base),
                encoding="utf-8",
            )
        if result.err:
            raise RuntimeError(f"xhtml2pdf сообщил об ошибках: {result.err}")
        if not _looks_like_pdf(target):
            raise RuntimeError("xhtml2pdf не создал корректный PDF")
        return "xhtml2pdf"
    except Exception as exc:
        xhtml_reason = f"{type(exc).__name__}: {exc}"
        _remove_file(target)
        raise PDFGenerationError(
            "Не удалось создать PDF. "
            f"WeasyPrint: {weasy_reason}. "
            f"xhtml2pdf: {xhtml_reason}."
        ) from exc


def open_pdf(path: str | Path) -> bool:
    """Пытается открыть PDF программой по умолчанию, не роняя приложение."""
    pdf_path = Path(path)
    if not pdf_path.is_file():
        print(f"Файл PDF не найден: «{pdf_path}»", file=sys.stderr)
        return False
    try:
        if os.name == "nt":
            os.startfile(str(pdf_path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(
                ["open", str(pdf_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["xdg-open", str(pdf_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True
    except Exception as exc:
        print(f"Не удалось открыть PDF автоматически: {exc}", file=sys.stderr)
        return False


def generate_invoice(
    invoice: Invoice,
    template_path: str | Path,
    output_dir: str | Path = OUTPUT_DIR,
) -> tuple[Path, str]:
    """Создаёт PDF и возвращает путь к файлу и имя движка."""
    html_text = render_html(template_path, invoice)
    template_stem = safe_filename(Path(template_path).stem)
    invoice_part = safe_filename(invoice.invoice_id)
    pdf_path = Path(output_dir) / f"{template_stem}_{invoice_part}.pdf"
    engine = render_pdf(html_text, pdf_path, PROJECT_ROOT)
    return pdf_path, engine


def _prompt_choice(prompt: str, count: int) -> int | None:
    """Запрашивает номер варианта. None означает отказ пользователя."""
    while True:
        try:
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.lower() in {"q", "quit", "exit", "0"}:
            return None
        if raw.isdigit():
            number = int(raw)
            if 1 <= number <= count:
                return number
        print(f"Введите номер от 1 до {count} или q для выхода.")


def _print_invoice_list(invoices: Sequence[Invoice]) -> None:
    for index, invoice in enumerate(invoices, start=1):
        print(
            f"  {index}. {invoice.invoice_id} — {invoice.customer_name}, "
            f"{invoice.date}, итого {format_money(invoice.total)} ₽"
        )


def _interactive_menu(no_open: bool = False) -> int:
    data_files = list_data_files()
    templates = list_templates()
    if not data_files:
        print(
            f"В папке «{DATA_DIR.name}/» нет CSV или JSON. "
            "Добавьте файл данных и запустите программу снова."
        )
        return 1
    if not templates:
        print(
            f"В папке «{TEMPLATES_DIR.name}/» нет HTML-шаблонов. "
            "Добавьте шаблон и запустите программу снова."
        )
        return 1

    print("PDF-чек-мейкер")
    print("\nФайлы данных:")
    for index, path in enumerate(data_files, start=1):
        print(f"  {index}. {path.name}")
    data_number = _prompt_choice("\nВыберите файл данных (q — выход): ", len(data_files))
    if data_number is None:
        return 0

    data_path = data_files[data_number - 1]
    invoices = list_invoices(data_path)
    if not invoices:
        print("В выбранном файле нет счетов.")
        return 1

    print("\nСчета:")
    _print_invoice_list(invoices)
    invoice_number = _prompt_choice("\nВыберите счёт (q — выход): ", len(invoices))
    if invoice_number is None:
        return 0

    print("\nШаблоны:")
    for index, path in enumerate(templates, start=1):
        print(f"  {index}. {path.name}")
    template_number = _prompt_choice("\nВыберите шаблон (q — выход): ", len(templates))
    if template_number is None:
        return 0

    invoice = invoices[invoice_number - 1]
    template_path = templates[template_number - 1]
    pdf_path, engine = generate_invoice(invoice, template_path, OUTPUT_DIR)
    print(f"\nPDF создан: {pdf_path}")
    print(f"Движок: {engine}")
    if not no_open and not open_pdf(pdf_path):
        print("PDF сохранён, но открыть его автоматически не удалось.", file=sys.stderr)
    return 0


def _list_everything(data_path: str | None) -> int:
    data_files = list_data_files()
    templates = list_templates()

    print("Файлы данных:")
    if data_files:
        for path in data_files:
            print(f"  - {path.name}")
    else:
        print("  нет")

    print("\nШаблоны:")
    if templates:
        for path in templates:
            print(f"  - {path.name}")
    else:
        print("  нет")

    paths = [Path(data_path)] if data_path else data_files
    for path in paths:
        print(f"\nСчета в «{path.name}»:")
        try:
            for invoice in list_invoices(path):
                print(
                    f"  - {invoice.invoice_id}: {invoice.customer_name}, "
                    f"{invoice.date}, итого {format_money(invoice.total)} ₽"
                )
        except PdfCheckError as exc:
            print(f"  Ошибка: {exc}")
    return 0


class _ArgumentParser(argparse.ArgumentParser):
    """Парсер с кодом выхода 1 для ошибок аргументов."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: ошибка: {message}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="pdf_generator.py",
        description="Генератор PDF-счетов из CSV или JSON по HTML-шаблону.",
    )
    parser.add_argument("--data", help="путь к CSV или JSON с данными")
    parser.add_argument("--template", help="путь к HTML-шаблону")
    parser.add_argument("--invoice", help="номер счёта, например INV-2026-001")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="не открывать PDF автоматически",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_files",
        help="показать файлы данных, шаблоны и счета",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """Точка входа CLI. Возвращает код выхода, не показывает трейсбеки."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        init_directories()

        if args.list_files:
            return _list_everything(args.data)

        automated = args.data or args.template or args.invoice
        if automated:
            if not (args.data and args.template and args.invoice):
                raise DataError(
                    "Для автоматического режима укажите все три аргумента: "
                    "--data, --template и --invoice."
                )
            invoices = list_invoices(args.data)
            selected = next(
                (item for item in invoices if item.invoice_id == args.invoice),
                None,
            )
            if selected is None:
                available = ", ".join(item.invoice_id for item in invoices)
                raise DataError(
                    f"Счёт «{args.invoice}» не найден. Доступные счета: {available}"
                )
            template_path = Path(args.template)
            pdf_path, engine = generate_invoice(selected, template_path, OUTPUT_DIR)
            print(f"PDF создан: {pdf_path}")
            print(f"Движок: {engine}")
            if not args.no_open and not open_pdf(pdf_path):
                print(
                    "PDF сохранён, но открыть его автоматически не удалось.",
                    file=sys.stderr,
                )
            return 0

        return _interactive_menu(no_open=args.no_open)
    except PdfCheckError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # последняя защита от трейсбека в консоли
        print(f"Непредвиденная ошибка: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
