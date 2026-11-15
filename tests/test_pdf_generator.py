"""Тесты генератора PDF-счетов.

Запуск из корня проекта:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pdf_generator as pg  # noqa: E402

TEMPLATE_PATH = PROJECT_ROOT / "templates" / "invoice.html"


def make_invoice(
    invoice_id: str = "INV-2026-001",
    customer: str = "ООО «Тест»",
    items: list[pg.InvoiceItem] | None = None,
) -> pg.Invoice:
    return pg.Invoice(
        invoice_id=invoice_id,
        customer_name=customer,
        date="2026-11-01",
        items=items
        or [
            pg.InvoiceItem("Бумага офисная А4", 10, Decimal("349.90")),
            pg.InvoiceItem("Ручка шариковая синяя", 25, Decimal("59.50")),
        ],
    )


def write_csv(directory: Path, content: str, name: str = "data.csv") -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8-sig", newline="")
    return path


def write_json(directory: Path, payload: object, name: str = "data.json") -> Path:
    path = directory / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="",
    )
    return path


def weasyprint_importable() -> bool:
    try:
        from weasyprint import HTML  # noqa: F401
    except Exception:
        return False
    return True


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp_path = Path(self.temp.name)


class CsvLoadingTests(TempDirTestCase):
    def test_csv_groups_rows_and_calculates_totals(self) -> None:
        path = write_csv(
            self.tmp_path,
            "invoice_id,customer_name,date,product,qty,price\n"
            'INV-002,ООО «Второй»,2026-11-05,Стол,1,"18 900,00"\n'
            'INV-001,ООО «Первый»,2026-11-01,Бумага,10,"349,90"\n'
            'INV-001,ООО «Первый»,2026-11-01,Ручка,25,"59,50"\n'
            'INV-001,ООО «Первый»,2026-11-01,Папка,5,"1 250,00"\n'
            'INV-002,ООО «Второй»,2026-11-05,Кресло,2,"12 490,00"\n',
        )

        invoices = pg.load_csv_invoices(path)

        self.assertEqual([item.invoice_id for item in invoices], ["INV-001", "INV-002"])
        self.assertEqual(len(invoices[0].items), 3)
        self.assertEqual(len(invoices[1].items), 2)
        self.assertEqual(invoices[0].total, Decimal("11236.50"))
        self.assertEqual(invoices[1].total, Decimal("43880.00"))

    def test_csv_reads_decimal_comma_and_thousands_spaces(self) -> None:
        path = write_csv(
            self.tmp_path,
            "invoice_id,customer_name,date,product,qty,price\n"
            'INV-003,ИП Тестов,2026-11-02,Товар,2,"1 234,56"\n',
        )

        invoice = pg.load_csv_invoices(path)[0]

        self.assertEqual(invoice.items[0].price, Decimal("1234.56"))
        self.assertEqual(invoice.total, Decimal("2469.12"))

    def test_csv_missing_required_column_raises_clear_error(self) -> None:
        path = write_csv(
            self.tmp_path,
            "invoice_id,customer_name,date,product,qty\n"
            "INV-001,Тест,2026-11-01,Товар,1\n",
        )

        with self.assertRaises(pg.DataError) as context:
            pg.load_csv_invoices(path)

        self.assertIn("price", str(context.exception))
        self.assertIn("колонок", str(context.exception))

    def test_csv_invalid_price_reports_line_and_value(self) -> None:
        path = write_csv(
            self.tmp_path,
            "invoice_id,customer_name,date,product,qty,price\n"
            "INV-001,Тест,2026-11-01,Товар,1,дорого\n",
        )

        with self.assertRaises(pg.DataError) as context:
            pg.load_csv_invoices(path)

        message = str(context.exception)
        self.assertIn("Строка 2", message)
        self.assertIn("дорого", message)

    def test_csv_empty_file_raises(self) -> None:
        path = write_csv(self.tmp_path, "")

        with self.assertRaises(pg.DataError) as context:
            pg.load_csv_invoices(path)

        self.assertIn("пуст", str(context.exception))

    def test_csv_header_only_raises(self) -> None:
        path = write_csv(
            self.tmp_path,
            "invoice_id,customer_name,date,product,qty,price\n",
        )

        with self.assertRaises(pg.DataError) as context:
            pg.load_csv_invoices(path)

        self.assertIn("ни одной позиции", str(context.exception))

    def test_csv_inconsistent_customer_for_one_invoice_raises(self) -> None:
        path = write_csv(
            self.tmp_path,
            "invoice_id,customer_name,date,product,qty,price\n"
            "INV-001,Первый,2026-11-01,Товар,1,100.00\n"
            "INV-001,Второй,2026-11-01,Товар,1,100.00\n",
        )

        with self.assertRaises(pg.DataError) as context:
            pg.load_csv_invoices(path)

        self.assertIn("покупатель", str(context.exception))

    def test_csv_zero_or_fractional_quantity_raises(self) -> None:
        for qty in ("0", "1.5"):
            with self.subTest(qty=qty):
                path = write_csv(
                    self.tmp_path,
                    "invoice_id,customer_name,date,product,qty,price\n"
                    f"INV-001,Тест,2026-11-01,Товар,{qty},100.00\n",
                    name=f"qty_{qty.replace('.', '_')}.csv",
                )
                with self.assertRaises(pg.DataError) as context:
                    pg.load_csv_invoices(path)
                self.assertIn("количество", str(context.exception))


class JsonLoadingTests(TempDirTestCase):
    def _payload(self) -> list[dict]:
        return [
            {
                "invoice_id": "INV-101",
                "customer_name": "ООО «Вектор»",
                "date": "2026-11-07",
                "items": [
                    {"product": "Монитор", "qty": 2, "price": 24990.00},
                    {"product": "Кабель", "qty": 4, "price": "790,50"},
                ],
            },
            {
                "invoice_id": "INV-102",
                "customer_name": "Студия «Лаванда»",
                "date": "2026-11-08",
                "items": [{"product": "Лампа", "qty": 3, "price": 4590.00}],
            },
        ]

    def test_json_list_root_is_supported(self) -> None:
        path = write_json(self.tmp_path, self._payload())

        invoices = pg.load_json_invoices(path)

        self.assertEqual([item.invoice_id for item in invoices], ["INV-101", "INV-102"])
        self.assertEqual(invoices[0].total, Decimal("53142.00"))
        self.assertEqual(invoices[1].total, Decimal("13770.00"))

    def test_json_object_with_invoices_key_is_supported(self) -> None:
        path = write_json(self.tmp_path, {"invoices": self._payload()})

        invoices = pg.load_json_invoices(path)

        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].items[1].price, Decimal("790.50"))

    def test_json_without_invoices_key_raises(self) -> None:
        path = write_json(self.tmp_path, {"orders": []})

        with self.assertRaises(pg.DataError) as context:
            pg.load_json_invoices(path)

        self.assertIn("invoices", str(context.exception))

    def test_json_with_empty_items_raises(self) -> None:
        payload = self._payload()
        payload[0]["items"] = []
        path = write_json(self.tmp_path, {"invoices": payload})

        with self.assertRaises(pg.DataError) as context:
            pg.load_json_invoices(path)

        self.assertIn("список позиций пуст", str(context.exception))

    def test_json_missing_customer_raises(self) -> None:
        payload = self._payload()
        del payload[0]["customer_name"]
        path = write_json(self.tmp_path, payload)

        with self.assertRaises(pg.DataError) as context:
            pg.load_json_invoices(path)

        self.assertIn("customer_name", str(context.exception))

    def test_json_duplicate_invoice_id_raises(self) -> None:
        payload = self._payload()
        payload[1]["invoice_id"] = payload[0]["invoice_id"]
        path = write_json(self.tmp_path, payload)

        with self.assertRaises(pg.DataError) as context:
            pg.load_json_invoices(path)

        self.assertIn("несколько раз", str(context.exception))

    def test_json_syntax_error_has_line_and_column(self) -> None:
        path = self.tmp_path / "broken.json"
        path.write_text('{"invoices": [}', encoding="utf-8")

        with self.assertRaises(pg.DataError) as context:
            pg.load_json_invoices(path)

        self.assertIn("строка", str(context.exception))
        self.assertIn("колонка", str(context.exception))


class TemplateRenderingTests(TempDirTestCase):
    def test_render_html_substitutes_invoice_fields(self) -> None:
        invoice = make_invoice()

        html = pg.render_html(TEMPLATE_PATH, invoice)

        self.assertIn("INV-2026-001", html)
        self.assertIn("ООО «Тест»", html)
        self.assertIn("2026-11-01", html)
        self.assertIn("4 986,50", html)
        self.assertIn("assets/DejaVuSans.ttf", html)

    def test_render_html_renders_all_items_and_line_totals(self) -> None:
        invoice = make_invoice(
            items=[
                pg.InvoiceItem("Первый товар", 1, Decimal("100.00")),
                pg.InvoiceItem("Второй товар", 2, Decimal("250.50")),
            ]
        )

        html = pg.render_html(TEMPLATE_PATH, invoice)

        self.assertIn("Первый товар", html)
        self.assertIn("Второй товар", html)
        self.assertIn("100,00", html)
        self.assertIn("501,00", html)
        self.assertIn("601,00", html)

    def test_render_html_escapes_user_supplied_html(self) -> None:
        invoice = make_invoice(customer="<script>alert(1)</script>")

        html = pg.render_html(TEMPLATE_PATH, invoice)

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_render_html_missing_template_raises(self) -> None:
        with self.assertRaises(pg.DataError) as context:
            pg.render_html(self.tmp_path / "missing.html", make_invoice())

        self.assertIn("не найден", str(context.exception))


class FilenameAndFormattingTests(unittest.TestCase):
    def test_safe_filename_removes_path_separators_and_traversal(self) -> None:
        result = pg.safe_filename("../../etc/passwd")

        self.assertEqual(result, "etc_passwd")
        self.assertNotIn("/", result)
        self.assertNotIn("\\", result)
        self.assertNotIn("..", result)

    def test_safe_filename_returns_fallback_for_empty_result(self) -> None:
        self.assertEqual(pg.safe_filename("***"), "invoice")
        self.assertEqual(pg.safe_filename("..."), "invoice")

    def test_safe_filename_handles_reserved_windows_name(self) -> None:
        self.assertEqual(pg.safe_filename("CON"), "CON_file")

    def test_safe_filename_keeps_cyrillic_letters(self) -> None:
        self.assertEqual(pg.safe_filename("Счёт № 7"), "Счёт_7")

    def test_format_money_uses_spaces_and_decimal_comma(self) -> None:
        self.assertEqual(pg.format_money(Decimal("1234567.5")), "1 234 567,50")
        self.assertEqual(pg.format_money("0"), "0,00")
        self.assertEqual(pg.format_money(Decimal("-1234.00")), "-1 234,00")

    def test_invoice_total_is_decimal_with_two_places(self) -> None:
        invoice = make_invoice(
            items=[pg.InvoiceItem("Товар", 3, Decimal("0.10"))]
        )

        self.assertEqual(invoice.total, Decimal("0.30"))
        self.assertIsInstance(invoice.total, Decimal)


class RenderPdfTests(TempDirTestCase):
    def _render_sample(self) -> tuple[str, Path, str]:
        invoice = make_invoice(
            invoice_id="INV-2026-777",
            customer="ООО «Кириллица»",
            items=[
                pg.InvoiceItem(
                    "Очень длинное наименование товара для проверки переноса строк "
                    "в таблице PDF-документа",
                    2,
                    Decimal("1234.50"),
                )
            ],
        )
        html = pg.render_html(TEMPLATE_PATH, invoice)
        output = self.tmp_path / "sample.pdf"
        errors = io.StringIO()
        with redirect_stderr(errors):
            engine = pg.render_pdf(html, output, PROJECT_ROOT)
        return engine, output, errors.getvalue()

    def test_render_pdf_creates_nonempty_pdf_with_text(self) -> None:
        engine, output, _ = self._render_sample()

        self.assertIn(engine, {"xhtml2pdf", "weasyprint"})
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 1024)
        self.assertEqual(output.read_bytes()[:4], b"%PDF")
        text = "".join(page.extract_text() or "" for page in PdfReader(output).pages)
        self.assertIn("INV-2026-777", text)
        self.assertIn("Кириллица", text)
        self.assertIn("2 469,00", text)

    @unittest.skipIf(weasyprint_importable(), "WeasyPrint доступен, fallback не проверить")
    def test_render_pdf_falls_back_to_xhtml2pdf_with_reason(self) -> None:
        engine, output, errors = self._render_sample()

        self.assertEqual(engine, "xhtml2pdf")
        self.assertTrue(output.is_file())
        self.assertIn("WeasyPrint", errors)
        self.assertIn("Причина", errors)

    def test_render_pdf_creates_parent_directory(self) -> None:
        output = self.tmp_path / "nested" / "result.pdf"
        invoice = make_invoice()
        html = pg.render_html(TEMPLATE_PATH, invoice)

        with redirect_stderr(io.StringIO()):
            pg.render_pdf(html, output, PROJECT_ROOT)

        self.assertTrue(output.is_file())


class CliTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.csv_path = write_csv(
            self.tmp_path,
            "invoice_id,customer_name,date,product,qty,price\n"
            'INV-2026-001,ООО «Ромашка»,2026-11-01,Бумага,10,"349,90"\n'
            'INV-2026-001,ООО «Ромашка»,2026-11-01,Ручка,25,"59,50"\n',
        )
        self.json_path = write_json(
            self.tmp_path,
            {
                "invoices": [
                    {
                        "invoice_id": "INV-2026-101",
                        "customer_name": "ООО «Вектор»",
                        "date": "2026-11-07",
                        "items": [
                            {"product": "Монитор", "qty": 1, "price": 24990.00}
                        ],
                    }
                ]
            },
        )
        self.output_dir = self.tmp_path / "output"

    def test_cli_csv_with_no_open_returns_zero_and_creates_pdf(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(pg, "OUTPUT_DIR", self.output_dir),
            patch.object(pg, "open_pdf") as open_mock,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = pg.main(
                [
                    "--data",
                    str(self.csv_path),
                    "--template",
                    str(TEMPLATE_PATH),
                    "--invoice",
                    "INV-2026-001",
                    "--no-open",
                ]
            )

        self.assertEqual(code, 0, stderr.getvalue())
        open_mock.assert_not_called()
        pdf_path = self.output_dir / "invoice_INV-2026-001.pdf"
        self.assertTrue(pdf_path.is_file())
        self.assertEqual(pdf_path.read_bytes()[:4], b"%PDF")
        self.assertIn("Движок:", stdout.getvalue())

    def test_cli_json_with_no_open_returns_zero_and_creates_pdf(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(pg, "OUTPUT_DIR", self.output_dir),
            patch.object(pg, "open_pdf") as open_mock,
            redirect_stdout(io.StringIO()),
            redirect_stderr(stderr),
        ):
            code = pg.main(
                [
                    "--data",
                    str(self.json_path),
                    "--template",
                    str(TEMPLATE_PATH),
                    "--invoice",
                    "INV-2026-101",
                    "--no-open",
                ]
            )

        self.assertEqual(code, 0, stderr.getvalue())
        open_mock.assert_not_called()
        self.assertTrue((self.output_dir / "invoice_INV-2026-101.pdf").is_file())

    def test_cli_unknown_invoice_returns_one_without_traceback(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(pg, "OUTPUT_DIR", self.output_dir),
            redirect_stdout(io.StringIO()),
            redirect_stderr(stderr),
        ):
            code = pg.main(
                [
                    "--data",
                    str(self.csv_path),
                    "--template",
                    str(TEMPLATE_PATH),
                    "--invoice",
                    "НЕТ-ТАКОГО",
                    "--no-open",
                ]
            )

        self.assertEqual(code, 1)
        message = stderr.getvalue()
        self.assertIn("Ошибка", message)
        self.assertIn("не найден", message)
        self.assertNotIn("Traceback", message)

    def test_cli_incomplete_arguments_returns_one(self) -> None:
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            code = pg.main(["--data", str(self.csv_path), "--no-open"])

        self.assertEqual(code, 1)
        self.assertIn("все три аргумента", stderr.getvalue())

    def test_cli_list_returns_zero_and_shows_project_files(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = pg.main(["--list"])

        self.assertEqual(code, 0)
        self.assertIn("invoices.csv", stdout.getvalue())
        self.assertIn("invoice.html", stdout.getvalue())

    def test_init_directories_creates_expected_folders(self) -> None:
        root = self.tmp_path / "project"
        with (
            patch.object(pg, "DATA_DIR", root / "data"),
            patch.object(pg, "TEMPLATES_DIR", root / "templates"),
            patch.object(pg, "OUTPUT_DIR", root / "output"),
        ):
            pg.init_directories()

        self.assertTrue((root / "data").is_dir())
        self.assertTrue((root / "templates").is_dir())
        self.assertTrue((root / "output").is_dir())

    def test_list_data_files_sorts_and_ignores_foreign_files(self) -> None:
        data_dir = self.tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "b.csv").write_text("", encoding="utf-8")
        (data_dir / "a.json").write_text("{}", encoding="utf-8")
        (data_dir / "note.txt").write_text("", encoding="utf-8")
        (data_dir / "nested").mkdir()
        (data_dir / "nested" / "hidden.csv").write_text("", encoding="utf-8")

        with patch.object(pg, "DATA_DIR", data_dir):
            files = pg.list_data_files()

        self.assertEqual([path.name for path in files], ["a.json", "b.csv"])


if __name__ == "__main__":
    unittest.main()
