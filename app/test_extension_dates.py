import reflex as rx

import copy
import re
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from app.states.dashboard_state import (
    EMPTY_RECORD,
    _date_value,
    _extension_cash,
    _extension_updates,
    _iso_or_raw,
    _parse_jotform_source_date,
    _record_due_date,
    _resolved_due_date,
    _write_ticket_extension,
    _load_extension_payments,
    _monthly_realized_interest,
)


class FakeWorksheet:
    def __init__(self, raw: dict[str, str]):
        self.values = [list(raw), list(raw.values())]
        self.values[0].append("Category")
        self.values[1].append("Duplicate header preserved")
        self.col_count = len(self.values[0])
        self.batches = 0
        self.corrupt = False
        self.change_before_write = False
        self.spreadsheet = FakeSpreadsheet()

    def get_all_values(self):
        return copy.deepcopy(self.values)

    def row_values(self, row: int):
        if row == 2 and self.change_before_write and not self.batches:
            self.values[1][self.values[0].index("Interest Amount")] = "301.00"
        return self.values[row - 1].copy()

    def add_cols(self, count: int):
        self.col_count += count

    def update(
        self, range_name: str, values: list[list[str]], value_input_option: str
    ):
        assert value_input_option == "RAW"
        self.values[0].extend(values[0])

    def batch_update(self, cells: list[dict], value_input_option: str):
        assert value_input_option == "RAW"
        self.batches += 1
        for cell in cells:
            match = re.fullmatch(r"([A-Z]+)(\d+)", cell["range"])
            letters, row = match.groups()
            column = 0
            for letter in letters:
                column = column * 26 + ord(letter) - ord("A") + 1
            target = self.values[int(row) - 1]
            target.extend([""] * max(0, column - len(target)))
            target[column - 1] = cell["values"][0][0]
        if self.corrupt:
            self.values[1][self.values[0].index("Payment Amount")] = "0.00"


class FakePaymentWorksheet:
    def __init__(self):
        self.values = []
        self.fail_after_append = False
        self.fail_before_append = False
        self.append_count = 0

    def get_all_values(self):
        return copy.deepcopy(self.values)

    def row_values(self, row):
        return self.values[row - 1].copy()

    def update(self, range_name, values, value_input_option):
        self.values = copy.deepcopy(values)

    def append_row(self, values, value_input_option):
        if self.fail_before_append:
            raise RuntimeError("Simulated append failure")
        self.values.append(values.copy())
        self.append_count += 1
        if self.fail_after_append:
            raise RuntimeError("Simulated lost append response")


class FakeSpreadsheet:
    def __init__(self):
        self.ledger = None
        self.creations = 0

    def worksheet(self, title):
        import gspread

        if self.ledger is None:
            raise gspread.WorksheetNotFound(title)
        return self.ledger

    def add_worksheet(self, title, rows, cols):
        self.creations += 1
        self.ledger = FakePaymentWorksheet()
        return self.ledger


class ExtensionDateTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 9, 4)
        self.raw = {
            "Pawn / Loan No.": "TEST-1",
            "Submission ID": "TEST-SUBMISSION",
            "Date": "09-03-2026",
            "Maturity / Due Date": "09/04/2026",
            "Status": "Active",
            "Approved Loan Amount": "1000.00",
            "Remaining Principal": "800.00",
            "Interest Amount": "300.00",
            "Payment Date": "",
            "Category": "Test only",
        }
        self.expected = dict(EMPTY_RECORD)
        self.expected.update(
            ticket="TEST-1",
            submission_id="TEST-SUBMISSION",
            status="Active",
            principal=1000.0,
            remaining_principal=800.0,
            interest=300.0,
            due_date="2026-09-04",
            issue_date="2026-09-03",
            payment_date="",
        )

    def test_source_dates_and_iso(self):
        for text, expected in (
            ("09-03-2026", date(2026, 9, 3)),
            ("09/04/2026", date(2026, 9, 4)),
            ("2026-09-03", date(2026, 9, 3)),
        ):
            self.assertEqual(_parse_jotform_source_date(text), expected)
        self.assertEqual(
            _resolved_due_date("09/04/2026", self.today), self.today
        )
        self.assertEqual(_date_value("2026-09-03"), date(2026, 9, 3))
        self.assertIsNone(_date_value("09/04/2026"))
        self.assertEqual(_iso_or_raw("09/04/2026"), "09/04/2026")
        self.raw.update(
            Status="Extended", **{"Payment Type": "Interest-only Extension"}
        )
        self.assertIsNone(_record_due_date(self.raw, date(2026, 9, 3)))
        self.raw["Maturity / Due Date"] = "2026-09-03"
        self.assertEqual(
            _record_due_date(self.raw, self.today), date(2026, 9, 3)
        )

    def test_cash_validation(self):
        for cash in ("", "0", "-1", "NaN", "Infinity", "300.001", "299.99"):
            with self.subTest(cash=cash), self.assertRaises(ValueError):
                _extension_cash(cash, 300.0)
        self.assertEqual(str(_extension_cash("300", 300.0)), "300.00")

    def test_due_today_past_and_future(self):
        for old_due in (date(2026, 9, 1), self.today, date(2026, 9, 20)):
            self.raw["Maturity / Due Date"] = old_due.isoformat()
            self.expected["due_date"] = old_due.isoformat()
            updates = _extension_updates(
                self.raw, self.expected, "300.00", self.today
            )
            new_due = max(old_due, self.today) + timedelta(days=30)
            self.assertEqual(
                updates["Maturity / Due Date"], new_due.isoformat()
            )
            self.assertEqual(
                updates["Day 23 Courtesy"],
                (new_due - timedelta(days=7)).isoformat(),
            )
            self.assertEqual(
                updates["Day 35 Final Warning"],
                (new_due + timedelta(days=5)).isoformat(),
            )
            self.assertEqual(updates["Day 30 Due Action"], new_due.isoformat())
            self.assertEqual(updates["Remaining Principal"], "800.00")
            self.assertEqual(updates["Interest Amount"], "240.00")
            self.assertEqual(updates["Total Amount Due"], "1040.00")
            self.assertEqual(updates["Payment Date"], self.today.isoformat())

    def test_stale_and_ineligible_records(self):
        for key, value in (
            ("Submission ID", "OTHER"),
            ("Status", "Settled"),
            ("Status", "Extended"),
            ("Liquidation Status", "Sold"),
            ("Maturity / Due Date", "2026-09-05"),
            ("Remaining Principal", "799.00"),
            ("Interest Amount", "301.00"),
        ):
            raw = self.raw.copy()
            raw[key] = value
            with (
                self.subTest(key=key, value=value),
                self.assertRaises(ValueError),
            ):
                _extension_updates(raw, self.expected, "400.00", self.today)

    def test_fake_verified_write_and_replay(self):
        sheet = FakeWorksheet(self.raw)
        original_headers = sheet.row_values(1)
        with patch(
            "app.states.dashboard_state._gaborone_now",
            return_value="2026-09-04T09:00:00+02:00",
        ):
            result = _write_ticket_extension(
                sheet, self.expected, "300.00", self.today
            )
        self.assertIn("saved and verified", result)
        self.assertEqual(
            sheet.row_values(1)[: len(original_headers)], original_headers
        )
        self.assertEqual(sheet.batches, 1)
        replay = _write_ticket_extension(
            sheet, self.expected, "300.00", self.today
        )
        self.assertIn("saved and verified", replay)
        self.assertEqual(sheet.batches, 1)
        self.assertEqual(sheet.spreadsheet.ledger.append_count, 1)
        payments, _ = _load_extension_payments(sheet.spreadsheet)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]["interest"], 300.0)
        self.assertEqual(payments[0]["principal"], 800.0)

    def test_missing_ledger_read_is_read_only(self):
        spreadsheet = FakeSpreadsheet()
        payments, message = _load_extension_payments(spreadsheet)
        self.assertEqual(payments, [])
        self.assertIn("operator", message)
        self.assertEqual(spreadsheet.creations, 0)

    def test_interrupted_append_reconciliation(self):
        for lost_response in (False, True):
            with self.subTest(lost_response=lost_response):
                sheet = FakeWorksheet(self.raw)
                ledger = sheet.spreadsheet.add_worksheet(
                    "Extension Payments", 1000, 13
                )
                ledger.fail_after_append = lost_response
                ledger.fail_before_append = not lost_response
                with self.assertRaises(RuntimeError):
                    _write_ticket_extension(
                        sheet, self.expected, "400.00", self.today
                    )
                self.assertEqual(sheet.batches, 1)
                ledger.fail_after_append = False
                ledger.fail_before_append = False
                result = _write_ticket_extension(
                    sheet, self.expected, "", self.today, repair=True
                )
                self.assertIn("saved and verified", result)
                self.assertEqual(sheet.batches, 1)
                self.assertEqual(ledger.append_count, 1)
                payments, _ = _load_extension_payments(sheet.spreadsheet)
                self.assertEqual(payments[0]["cash"], 400.0)
                self.assertEqual(payments[0]["interest"], 300.0)
                self.assertEqual(payments[0]["excess"], 100.0)

    def test_conflicting_retry_preserves_history(self):
        sheet = FakeWorksheet(self.raw)
        _write_ticket_extension(sheet, self.expected, "300.00", self.today)
        before = sheet.spreadsheet.ledger.get_all_values()
        with self.assertRaises(ValueError):
            _write_ticket_extension(sheet, self.expected, "400.00", self.today)
        self.assertEqual(before, sheet.spreadsheet.ledger.get_all_values())
        self.assertEqual(sheet.batches, 1)

    def test_monthly_accounting_and_duplicates(self):
        sheet = FakeWorksheet(self.raw)
        _write_ticket_extension(sheet, self.expected, "400.00", self.today)
        payments, _ = _load_extension_payments(sheet.spreadsheet)
        settled = dict(self.expected)
        settled.update(
            status="Settled",
            date_settled="2026-10-05",
            month="2026-08",
            settlement_realized_profit=240.0,
        )
        self.assertEqual(
            _monthly_realized_interest([settled], payments, "2026-09"), 300.0
        )
        self.assertEqual(
            _monthly_realized_interest([settled], payments, "2026-10"), 240.0
        )
        self.assertEqual(
            _monthly_realized_interest([settled], payments, "2026-08"), 0.0
        )
        ledger = sheet.spreadsheet.ledger
        ledger.values.append(ledger.values[1].copy())
        payments, message = _load_extension_payments(sheet.spreadsheet)
        self.assertEqual(len(payments), 1)
        self.assertIn("duplicate", message)
        self.assertEqual(
            _monthly_realized_interest([], payments, "2026-09"), 300.0
        )
        with self.assertRaises(ValueError):
            _write_ticket_extension(sheet, self.expected, "300.00", self.today)
        self.assertEqual(len(ledger.values), 3)

    def test_unverified_write_and_prewrite_conflict(self):
        sheet = FakeWorksheet(self.raw)
        sheet.corrupt = True
        with self.assertRaises(RuntimeError):
            _write_ticket_extension(sheet, self.expected, "300.00", self.today)
        sheet = FakeWorksheet(self.raw)
        sheet.change_before_write = True
        with self.assertRaises(ValueError):
            _write_ticket_extension(sheet, self.expected, "300.00", self.today)
        self.assertEqual(sheet.batches, 0)


if __name__ == "__main__":
    unittest.main()
