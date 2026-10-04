import reflex as rx

import copy
import asyncio
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
    _settlement_accounting,
    _realized_interest_reporting_month,
    _date_month,
    _primary_date_updates,
    _confirmed_extension_match,
    _extension_confirmation_text,
    _first_valid_mobile,
    DashboardState,
    EMPTY_EXTENSION,
    _unique_headers,
    _historical_row_eligible,
    _verified_cycle_start,
    EXTENSION_COLUMNS,
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
    title = "Extension Payments"

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

    def worksheets(self) -> list[FakePaymentWorksheet]:
        return [] if self.ledger is None else [self.ledger]

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
        self.assertEqual(_date_value("09/04/2026"), date(2026, 9, 4))
        self.assertEqual(_iso_or_raw("09/04/2026"), "2026-09-04")
        self.raw.update(
            Status="Extended", **{"Payment Type": "Interest-only Extension"}
        )
        self.assertEqual(
            _record_due_date(self.raw, date(2026, 9, 3)), date(2026, 9, 4)
        )
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
        self.assertIn("saved and verified", result["message"])
        self.assertTrue(result["primary_verified"])
        self.assertTrue(result["ledger_verified"])
        self.assertEqual(
            sheet.row_values(1)[: len(original_headers)], original_headers
        )
        self.assertEqual(sheet.batches, 1)
        replay = _write_ticket_extension(
            sheet, self.expected, "300.00", self.today
        )
        self.assertIn("saved and verified", replay["message"])
        self.assertEqual(sheet.batches, 1)
        self.assertEqual(sheet.spreadsheet.ledger.append_count, 1)
        payments, _ = _load_extension_payments(sheet.spreadsheet)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]["interest"], 300.0)
        self.assertEqual(payments[0]["principal"], 800.0)

    def test_confirmation_requires_exact_verified_reloaded_transaction(self):
        sheet = FakeWorksheet(self.raw)
        result = _write_ticket_extension(
            sheet, self.expected, "400.00", self.today
        )
        payments, _ = _load_extension_payments(sheet.spreadsheet)
        ticket = dict(self.expected)
        ticket.update(
            status="Extended",
            due_date=payments[0]["new_due"],
            payment_date=payments[0]["payment_date"],
        )
        self.assertEqual(
            _confirmed_extension_match(result, payments, [ticket]), payments[0]
        )
        for field in ("primary_verified", "ledger_verified"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                _confirmed_extension_match(
                    {**result, field: False}, payments, [ticket]
                )
        for loaded in (
            [],
            [{**payments[0], "cash": 999.0}],
            [{**payments[0], "extension_id": "wrong"}],
            payments * 2,
        ):
            with self.subTest(loaded=loaded), self.assertRaises(ValueError):
                _confirmed_extension_match(result, loaded, [ticket])
        with self.assertRaises(ValueError):
            _confirmed_extension_match(
                result, payments, [{**ticket, "extension_pending": True}]
            )
        with self.assertRaises(ValueError):
            _confirmed_extension_match(result, payments, [])

    def test_confirmation_uses_saved_amounts_and_verified_contact(self):
        raw = {
            **self.raw,
            "Full Name - First Name": "Mpho",
            "Full Name - Last Name": "Test",
            "Mobile No.": "+267 7123 4567",
        }
        sheet = FakeWorksheet(raw)
        result = _write_ticket_extension(
            sheet, self.expected, "400.00", self.today
        )
        payments, _ = _load_extension_payments(sheet.spreadsheet)
        ticket = {
            **self.expected,
            "status": "Extended",
            "due_date": payments[0]["new_due"],
            "payment_date": payments[0]["payment_date"],
        }
        state = DashboardState(_reflex_internal_init=True)
        state._keep_extension_confirmation(
            result, {"extension_payments": payments, "records": [ticket]}
        )
        state.selected_ticket = ""
        self.assertEqual(state.last_confirmed_extension, payments[0])
        preview = state.extension_confirmation_preview
        self.assertIn("Hello Mpho Test,", preview)
        self.assertIn("P400.00", preview)
        self.assertIn("2026-10-04", preview)
        self.assertIn("P800.00", preview)
        from urllib.parse import unquote

        url = state.extension_confirmation_url
        self.assertTrue(url.startswith("https://wa.me/26771234567?text="))
        self.assertEqual(unquote(url.split("?text=", 1)[1]), preview)
        for invalid in ("", "—", "+27 71234567", "61234567", "7123456"):
            state.last_extension_mobile = invalid
            state.last_extension_contact = ""
            self.assertEqual(state.extension_confirmation_url, "")
        state.last_extension_contact = "00267 7123 4567"
        self.assertTrue(state.extension_confirmation_url)
        self.assertEqual(
            _first_valid_mobile("invalid", "+267 71234567"), "71234567"
        )
        self.assertTrue(
            _extension_confirmation_text(payments[0], "—").startswith("Hello,")
        )
        state._clear_extension_confirmation()
        self.assertEqual(state.last_confirmed_extension, EMPTY_EXTENSION)
        self.assertEqual(state.extension_confirmation_url, "")
        self.assertEqual(state.extension_confirmation_preview, "")

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
                self.assertIn("saved and verified", result["message"])
                self.assertTrue(result["primary_verified"])
                self.assertTrue(result["ledger_verified"])
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

    def test_settlement_saved_profit_and_partial_legacy_detail(self):
        cases = (
            (
                {
                    "Settlement Realized Profit": "170",
                    "Settlement Interest": "144",
                    "Retained Overpayment": "26",
                },
                170.0,
            ),
            ({"Settlement Realized Profit": "170"}, 170.0),
            (
                {
                    "Settlement Realized Profit": "0",
                    "Settlement Interest": "144",
                },
                0.0,
            ),
            (
                {
                    "Settlement Realized Profit": "-1",
                    "Settlement Interest": "144",
                    "Retained Overpayment": "26",
                },
                170.0,
            ),
            (
                {"Settlement Interest": "144", "Retained Overpayment": "26"},
                170.0,
            ),
            ({"Settlement Interest": "144"}, 144.0),
            ({"Settlement Principal": "1000"}, 624.0),
            ({"Settlement Late Fees": "10"}, 634.0),
            ({}, 624.0),
        )
        for details, expected in cases:
            with self.subTest(details=details):
                raw = {
                    "Payment Amount": "2000",
                    "Extension Excess": "500",
                    **details,
                }
                accounting = _settlement_accounting(raw, "Settled", 624.0)
                self.assertEqual(
                    accounting["settlement_realized_profit"], expected
                )
                record = {
                    **EMPTY_RECORD,
                    **accounting,
                    "status": "Settled",
                    "date_settled": "2026-09-29",
                    "interest": 624.0,
                    "settlement_profit_available": True,
                }
                self.assertEqual(
                    _monthly_realized_interest([record], [], "2026-09"),
                    expected,
                )
                self.assertEqual(
                    _monthly_realized_interest([record], [], "2026-10"), 0.0
                )
                for status, liquidation in (
                    ("Active", ""),
                    ("Settled", "Sold"),
                ):
                    excluded = _settlement_accounting(
                        {**raw, "Liquidation Status": liquidation},
                        status,
                        624.0,
                    )
                    self.assertEqual(
                        excluded["settlement_realized_profit"], 0.0
                    )
        legacy = {
            **EMPTY_RECORD,
            "status": "Settled",
            "date_settled": "2026-09-29",
            "interest": 624.0,
            "settlement_interest": 144.0,
            "retained_overpayment": 26.0,
        }
        self.assertEqual(
            _monthly_realized_interest([legacy], [], "2026-09"), 170.0
        )
        legacy["settlement_interest"] = 0.0
        legacy["retained_overpayment"] = 0.0
        self.assertEqual(
            _monthly_realized_interest([legacy], [], "2026-09"), 624.0
        )

    def test_settlement_date_normalization_and_month_matching(self):
        for text, iso in (
            ("2026-09-29", "2026-09-29"),
            ("29/09/2026", "2026-09-29"),
            ("09/29/2026", "2026-09-29"),
            ("29-09-2026", "2026-09-29"),
            ("09/10/2026", "2026-09-10"),
            ("09-10-2026", "2026-09-10"),
        ):
            with self.subTest(text=text):
                self.assertEqual(_iso_or_raw(text), iso)
                self.assertEqual(_date_month(text), "2026-09")
                record = {
                    **EMPTY_RECORD,
                    "status": "Settled",
                    "date_settled": text,
                    "settlement_realized_profit": 170.0,
                }
                self.assertEqual(
                    _monthly_realized_interest([record], [], "2026-09"), 170.0
                )
        self.assertIsNone(_date_value("02/30/2026"))
        self.assertIsNone(_date_value("2026-09-29Tinvalid"))

    def test_reporting_month_fallback_current_and_explicit_lenses(self):
        today = date(2026, 10, 1)
        september = {
            **EMPTY_RECORD,
            "status": "Settled",
            "date_settled": "2026-09-29",
            "settlement_realized_profit": 170.0,
            "month": "2026-08",
        }
        state = DashboardState(_reflex_internal_init=True)
        state.extension_payments = []
        state.selected_month = "ALL"
        state.records = [september, {**self.expected, "month": "2026-10"}]
        with patch(
            "app.states.dashboard_state._gaborone_date", return_value=today
        ):
            self.assertEqual(state.realized_interest_reporting_month, "2026-09")
            self.assertEqual(state.realized_interest, 170.0)
            self.assertEqual(state.selected_month, "ALL")
            self.assertEqual(len(state.visible_records), 2)
            self.assertEqual(state.deployed_capital, 800.0)
            state.selected_month = "2026-10"
            self.assertEqual(state.realized_interest_reporting_month, "2026-10")
            self.assertEqual(state.realized_interest, 0.0)
            self.assertEqual(len(state.visible_records), 1)
            state.selected_month = "2026-08"
            self.assertEqual(state.realized_interest_reporting_month, "2026-08")
            self.assertEqual(state.realized_interest, 0.0)
        payment = {
            **EMPTY_EXTENSION,
            "extension_id": "TEST-REPORT",
            "status": "Verified",
            "payment_date": "2026-10-01",
            "interest": 300.0,
            "cash": 400.0,
            "excess": 100.0,
        }
        self.assertEqual(
            _realized_interest_reporting_month(
                [september], [payment], "ALL", today
            ),
            "2026-10",
        )
        self.assertEqual(
            _monthly_realized_interest(
                [september], [payment, payment.copy()], "2026-10"
            ),
            300.0,
        )
        self.assertEqual(
            _realized_interest_reporting_month(
                [september], [{**payment, "status": "Pending"}], "ALL", today
            ),
            "2026-09",
        )
        conflict = {**payment, "cash": 500.0}
        self.assertEqual(
            _realized_interest_reporting_month(
                [september], [payment, conflict], "ALL", today
            ),
            "2026-09",
        )
        self.assertEqual(
            _realized_interest_reporting_month([], [], "ALL", today), "2026-10"
        )
        self.assertEqual(
            _realized_interest_reporting_month(
                [], [payment], "ALL", date(2026, 11, 1)
            ),
            "2026-10",
        )
        self.assertEqual(
            _realized_interest_reporting_month(
                [], [payment], "ALL", date(2026, 9, 1)
            ),
            "2026-09",
        )

    def test_october_future_and_overdue_verified_iso_milestones(self):
        for today, expected_due in (
            (date(2026, 10, 1), date(2026, 11, 2)),
            (date(2026, 10, 3), date(2026, 11, 2)),
            (date(2026, 10, 10), date(2026, 11, 9)),
        ):
            with self.subTest(today=today):
                raw = {**self.raw, "Maturity / Due Date": "2026-10-03"}
                expected = {**self.expected, "due_date": "2026-10-03"}
                sheet = FakeWorksheet(raw)
                result = _write_ticket_extension(
                    sheet, expected, "300.00", today
                )
                saved = dict(zip(sheet.row_values(1), sheet.row_values(2)))
                self.assertTrue(
                    result["primary_verified"] and result["ledger_verified"]
                )
                for field, offset in (
                    ("Maturity / Due Date", 0),
                    ("Day 23 Courtesy", -7),
                    ("Day 30 Due Action", 0),
                    ("Day 35 Final Warning", 5),
                ):
                    self.assertEqual(
                        saved[field],
                        (expected_due + timedelta(days=offset)).isoformat(),
                    )
                before = sheet.get_all_values()
                _primary_date_updates(saved)
                self.assertEqual(
                    _record_due_date(saved, self.today), expected_due
                )
                self.assertEqual(sheet.get_all_values(), before)
                self.assertEqual(sheet.batches, 1)

    def test_reminder_queue_reorders_from_reloaded_records(self):
        state = DashboardState(_reflex_internal_init=True)
        overdue = {**self.expected, "due_date": "2026-09-01"}
        other = {**self.expected, "ticket": "TEST-2", "due_date": "2026-09-11"}
        state.records = [other, overdue]
        with patch(
            "app.states.dashboard_state._gaborone_date", return_value=self.today
        ):
            self.assertEqual(
                [r["ticket"] for r in state.reminder_queue],
                ["TEST-1", "TEST-2"],
            )
            sheet = FakeWorksheet(
                {**self.raw, "Maturity / Due Date": overdue["due_date"]}
            )
            _write_ticket_extension(sheet, overdue, "300.00", self.today)
            payments, _ = _load_extension_payments(sheet.spreadsheet)
            state.records = [
                other,
                {
                    **overdue,
                    "status": "Extended",
                    "due_date": payments[0]["new_due"],
                },
            ]
            state.extension_payments = payments
            queue = state.reminder_queue
            self.assertEqual([r["ticket"] for r in queue], ["TEST-2", "TEST-1"])
            self.assertEqual(queue[1]["countdown_days"], 30)
            self.assertEqual(queue[1]["maturity_date"], "2026-10-04")
            self.assertEqual(state.reminder_queue_count, 2)
            self.assertEqual(state.realized_interest, 300.0)

    def historical_fixture(self):
        raw = {
            **self.raw,
            "Pawn / Loan No.": "SC-09-03-01",
            "Date": "2026-09-03",
            "Status": "Extended",
            "Maturity / Due Date": "2026-10-03",
            "Day 23 Courtesy": "2026-09-26",
            "Day 30 Due Action": "2026-10-03",
            "Day 35 Final Warning": "2026-10-08",
            "Day 23 Status": "Sent",
            "Day 30 Status": "Sent",
            "Day 35 Status": "Scheduled",
            "Approved Loan Amount": "1500",
            "Remaining Principal": "",
            "Interest Amount": "450.00",
            "Total Amount Due": "1950.00",
            "Payment Amount": "",
            "Payment Date": "",
            "Payment Type": "",
            "Extension ID": "",
            "Extension Transaction": "",
            "Date Settled": "",
            "Liquidation Status": "",
        }
        sheet = FakeWorksheet(raw)
        snapshot = dict(
            zip(_unique_headers(sheet.row_values(1)), sheet.row_values(2))
        )
        expected = {
            **EMPTY_RECORD,
            "ticket": "SC-09-03-01",
            "submission_id": "TEST-SUBMISSION",
            "issue_date": "2026-09-03",
            "loan_date": "2026-09-03",
            "month": "2026-09",
            "status": "Extended",
            "due_date": "2026-10-03",
            "principal": 1500.0,
            "approved": 1500.0,
            "remaining_principal": 1500.0,
            "interest": 450.0,
            "total_due": 1950.0,
            "source_snapshot": snapshot,
            "historical_extension_eligible": _historical_row_eligible(snapshot),
        }
        return sheet, expected

    def historical_write(
        self,
        sheet,
        expected,
        payment_date="2026-10-03",
        cash="450",
        confirmed=True,
    ):
        return _write_ticket_extension(
            sheet,
            expected,
            cash,
            date(2026, 10, 10),
            historical=True,
            historical_date=payment_date,
            confirmed=confirmed,
        )

    def historical_reload(self, sheet, expected):
        headers = _unique_headers(sheet.row_values(1))
        row = sheet.row_values(2)
        raw = {
            key: row[i] if i < len(row) else "" for i, key in enumerate(headers)
        }
        payments, message = _load_extension_payments(sheet.spreadsheet)
        record = {
            **expected,
            "issue_date": _iso_or_raw(raw["Date"]),
            "due_date": raw["Maturity / Due Date"],
            "payment_date": raw.get("Payment Date", ""),
            "status": raw["Status"],
            "remaining_principal": float(
                raw["Remaining Principal"] or raw["Approved Loan Amount"]
            ),
            "source_snapshot": raw,
            "historical_extension_eligible": _historical_row_eligible(raw),
            "extension_pending": bool(raw.get("Extension ID"))
            and not any(
                p["extension_id"] == raw["Extension ID"] for p in payments
            ),
        }
        return record, payments, message

    def test_historical_receipt_acceptance_milestones_reporting_and_queue(self):
        sheet, expected = self.historical_fixture()
        september = {
            **EMPTY_RECORD,
            "ticket": "SETTLED",
            "status": "Settled",
            "date_settled": "2026-09-29",
            "settlement_realized_profit": 170.0,
        }
        other = {**self.expected, "ticket": "OTHER", "due_date": "2026-10-15"}
        state = DashboardState(_reflex_internal_init=True)
        state.records = [other, expected, september]
        state.active_tab = "ledger"
        state.selected_ticket = expected["ticket"]
        state.payment_amount = "450"
        state.historical_payment_date = "2026-10-03"
        state.historical_cash_confirmed = True
        with patch(
            "app.states.dashboard_state._gaborone_date",
            return_value=date(2026, 10, 10),
        ):
            self.assertTrue(state.historical_extension_eligible)
            self.assertEqual(state.historical_extension_validation, "")
            self.assertIn("Legacy", state.extension_validation)
            self.assertEqual(state.realized_interest_reporting_month, "2026-09")
            self.assertEqual(state.realized_interest, 170.0)
            self.assertEqual(
                [r["ticket"] for r in state.reminder_queue],
                [expected["ticket"], "OTHER"],
            )
            self.assertEqual(
                state.reminder_queue[0]["cycle_start"], "2026-09-03"
            )
            result = self.historical_write(sheet, expected)
            record, payments, message = self.historical_reload(sheet, expected)
            payload = {
                "records": [other, record, september],
                "extension_payments": payments,
                "extension_ledger_message": message,
                "months": ["2026-10", "2026-09"],
                "worksheet": "Fake",
                "calendar_health": "Fake",
            }

            async def consume():
                async for _ in state.extend_ticket(True):
                    pass

            with (
                patch(
                    "app.states.dashboard_state._record_extension",
                    return_value=result,
                ) as write,
                patch(
                    "app.states.dashboard_state._read_live_records",
                    return_value=payload,
                ) as reload,
            ):
                asyncio.run(consume())
                self.assertEqual(
                    write.call_args.args[3:], (True, "2026-10-03", True)
                )
                reload.assert_called_once()
            self.assertEqual(state.realized_interest_reporting_month, "2026-10")
            self.assertEqual(state.realized_interest, 450.0)
            self.assertEqual(state.last_confirmed_extension["cash"], 450.0)
            self.assertIn("no new cash", state.success_message)
            self.assertEqual(
                [r["ticket"] for r in state.reminder_queue],
                ["OTHER", expected["ticket"]],
            )
            self.assertEqual(
                state.reminder_queue[1]["cycle_start"], "2026-10-03"
            )
            self.assertEqual(
                state.reminder_queue[1]["issue_date"], "2026-09-03"
            )
            self.assertEqual(state.reminder_queue[1]["countdown_days"], 23)
            state.selected_month = "2026-09"
            self.assertEqual(state.realized_interest, 170.0)
        raw = record["source_snapshot"]
        for field, value in (
            ("Date", "2026-09-03"),
            ("Maturity / Due Date", "2026-11-02"),
            ("Day 23 Courtesy", "2026-10-26"),
            ("Day 30 Due Action", "2026-11-02"),
            ("Day 35 Final Warning", "2026-11-07"),
            ("Payment Date", "2026-10-03"),
            ("Approved Loan Amount", "1500"),
            ("Remaining Principal", "1500.00"),
            ("Day 23 Status", ""),
            ("Day 30 Status", ""),
            ("Day 35 Status", ""),
        ):
            self.assertEqual(raw[field], value)
        self.assertTrue(
            result["primary_verified"] and result["ledger_verified"]
        )
        self.assertEqual(payments[0]["interest"], 450.0)
        self.assertEqual(payments[0]["cash"], 450.0)
        self.assertEqual(payments[0]["excess"], 0.0)
        self.assertEqual(record["month"], "2026-09")
        self.assertEqual(
            _confirmed_extension_match(result, payments, [record]), payments[0]
        )

    def test_historical_dates_confirmation_and_actual_cash_required(self):
        for value, confirmed in (
            ("", True),
            ("10/03/2026", True),
            ("2026-02-30", True),
            ("2026-10-11", True),
            ("2026-09-02", True),
            ("2026-10-03", False),
        ):
            with self.subTest(value=value, confirmed=confirmed):
                sheet, expected = self.historical_fixture()
                with self.assertRaises(ValueError):
                    self.historical_write(
                        sheet, expected, value, confirmed=confirmed
                    )
                self.assertEqual(sheet.batches, 0)
                self.assertEqual(sheet.spreadsheet.creations, 0)
        for cash in ("", "0", "449.99", "NaN", "450.001"):
            sheet, expected = self.historical_fixture()
            with self.subTest(cash=cash), self.assertRaises(ValueError):
                self.historical_write(sheet, expected, cash=cash)
            self.assertEqual(sheet.batches, 0)
        for value, due in (
            ("2026-09-03", "2026-11-02"),
            ("2026-10-10", "2026-11-09"),
        ):
            sheet, expected = self.historical_fixture()
            result = self.historical_write(sheet, expected, value)
            self.assertEqual(result["payment"]["new_due"], due)
            self.assertEqual(result["payment"]["payment_date"], value)

    def test_historical_repeat_reconciliation_and_conflicting_retry(self):
        sheet, expected = self.historical_fixture()
        first = self.historical_write(sheet, expected)
        replay = self.historical_write(sheet, expected)
        self.assertEqual(first["payment"], replay["payment"])
        self.assertEqual(sheet.batches, 1)
        self.assertEqual(sheet.spreadsheet.ledger.append_count, 1)
        for value, cash in (("2026-10-04", "450"), ("2026-10-03", "451")):
            with self.assertRaises(ValueError):
                self.historical_write(sheet, expected, value, cash)
        record, _, _ = self.historical_reload(sheet, expected)
        with self.assertRaises(ValueError):
            self.historical_write(sheet, record)
        next_result = _write_ticket_extension(
            sheet, record, "450", date(2026, 10, 10)
        )
        self.assertEqual(next_result["payment"]["new_due"], "2026-12-02")
        self.assertEqual(next_result["payment"]["payment_date"], "2026-10-10")
        self.assertEqual(sheet.spreadsheet.ledger.append_count, 2)
        for lost_response in (False, True):
            sheet, expected = self.historical_fixture()
            ledger = sheet.spreadsheet.add_worksheet(
                "Extension Payments", 1000, 13
            )
            ledger.fail_before_append = not lost_response
            ledger.fail_after_append = lost_response
            with self.assertRaises(RuntimeError):
                self.historical_write(sheet, expected)
            ledger.fail_before_append = ledger.fail_after_append = False
            repaired = _write_ticket_extension(
                sheet, expected, "", date(2026, 10, 10), repair=True
            )
            self.assertEqual(repaired["payment"]["payment_date"], "2026-10-03")
            self.assertEqual(sheet.batches, 1)
            self.assertEqual(ledger.append_count, 1)

    def test_historical_receipts_status_snapshot_and_duplicate_guards(self):
        for key, value in (
            ("Status", "Active"),
            ("Status", "Settled"),
            ("Status", "Defaulted"),
            ("Liquidation Status", "Sold"),
            ("Date Settled", "2026-10-03"),
            ("Payment Amount", "0"),
            ("Payment Amount", "450"),
            ("Payment Date", "invalid"),
            ("Payment Type", "Interest Extension"),
            ("Extension ID", "false-id"),
            ("Extension Transaction", "{}"),
            ("Interest Amount", "451"),
            ("Date", "2026-09-04"),
            ("Day 23 Status", "Changed"),
        ):
            with self.subTest(key=key, value=value):
                sheet, expected = self.historical_fixture()
                sheet.values[1][sheet.values[0].index(key)] = value
                with self.assertRaises(ValueError):
                    self.historical_write(sheet, expected)
                self.assertEqual(sheet.batches, 0)
                self.assertEqual(sheet.spreadsheet.creations, 0)
        sheet, expected = self.historical_fixture()
        with self.assertRaises(ValueError):
            _write_ticket_extension(sheet, expected, "450", date(2026, 10, 10))
        self.assertEqual(sheet.batches, 0)
        for status in ("Verified", "Pending", "Invalid"):
            sheet, expected = self.historical_fixture()
            ledger = sheet.spreadsheet.add_worksheet(
                "Extension Payments", 1000, 13
            )
            row = {key: "" for key in EXTENSION_COLUMNS}
            row.update(
                {
                    "Extension ID": "different-submission-or-false",
                    "Ticket": expected["ticket"],
                    "Old Due": "2026-10-03",
                    "Status": status,
                }
            )
            ledger.values = [
                list(EXTENSION_COLUMNS),
                [row[key] for key in EXTENSION_COLUMNS],
            ]
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.historical_write(sheet, expected)
            self.assertEqual(sheet.batches, 0)
            self.assertEqual(ledger.append_count, 0)
        sheet, expected = self.historical_fixture()
        sheet.change_before_write = True
        with self.assertRaises(ValueError):
            self.historical_write(sheet, expected)
        self.assertEqual(sheet.batches, 0)

    def test_historical_failed_verification_never_counts_or_confirms(self):
        sheet, expected = self.historical_fixture()
        sheet.corrupt = True
        with self.assertRaises(RuntimeError):
            self.historical_write(sheet, expected)
        payments, _ = _load_extension_payments(sheet.spreadsheet)
        self.assertEqual(payments, [])
        self.assertEqual(
            _monthly_realized_interest([expected], payments, "2026-10"), 0.0
        )
        self.assertEqual(_verified_cycle_start(expected, payments), "")
        sheet, expected = self.historical_fixture()
        result = self.historical_write(sheet, expected)
        record, payments, _ = self.historical_reload(sheet, expected)
        for invalid in (
            [{**payments[0], "status": "Pending"}],
            [{**payments[0], "new_due": "2026-11-03"}],
            [payments[0], {**payments[0], "cash": 451.0}],
        ):
            self.assertEqual(_verified_cycle_start(record, invalid), "")
        with self.assertRaises(ValueError):
            _confirmed_extension_match(
                {**result, "ledger_verified": False}, payments, [record]
            )

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
