import reflex as rx

import copy
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from app.states.dashboard_state import (
    DashboardState,
    EMPTY_RECORD,
    EMPTY_EXTENSION,
    _financial_month_rows,
    _financial_expected_inflows,
    _monthly_realized_interest,
)


class FinancialReportTests(unittest.TestCase):
    def setUp(self):
        self.state = DashboardState(_reflex_internal_init=True)
        self.state.financial_month = "ALL"
        self.loan = {
            **EMPTY_RECORD,
            "ticket": "ORIGINAL",
            "submission_id": "ONE",
            "issue_date": "2026-09-03",
            "loan_date": "2026-09-03",
            "month": "2099-01",
            "approved": 1500.0,
            "principal": 1500.0,
            "remaining_principal": 900.0,
            "status": "Extended",
            "total_due": 1950.0,
            "due_date": "2026-11-02",
            "payment_date": "2026-10-03",
        }
        self.settled = {
            **EMPTY_RECORD,
            "ticket": "SETTLED",
            "status": "Settled",
            "date_settled": "2026-09-29",
            "settlement_realized_profit": 170.0,
            "month": "2099-01",
        }
        self.payment = {
            **EMPTY_EXTENSION,
            "extension_id": "HISTORICAL-ONE",
            "ticket": "ORIGINAL",
            "status": "Verified",
            "payment_date": "2026-10-03",
            "cash": 500.0,
            "interest": 450.0,
            "excess": 50.0,
            "principal": 1500.0,
        }
        self.state.records = [self.loan, self.settled]
        self.state.extension_payments = [self.payment]

    def test_known_example_filters_and_chart_source_months(self):
        state = self.state
        self.assertEqual(state.financial_month, "ALL")
        self.assertEqual(state.financial_total_deployed, 1500.0)
        self.assertEqual(state.financial_cumulative_profit, 620.0)
        self.assertEqual(state.financial_subtotals["total"], 620.0)
        self.assertEqual(state.financial_months, ["2026-10", "2026-09"])
        self.assertEqual(
            state._financial_chart_columns(),
            {
                "month": ["2026-09", "2026-10"],
                "deployed": [1500.0, 0.0],
                "profit": [170.0, 450.0],
            },
        )
        state.selected_month = "2026-08"
        state.choose_financial_month("2026-10")
        self.assertEqual(state.financial_subtotals["total"], 450.0)
        self.assertEqual(len(state.financial_filtered_rows), 1)
        state.choose_financial_month("2026-09")
        self.assertEqual(state.financial_subtotals["total"], 170.0)
        self.assertEqual(state.selected_month, "2026-08")
        self.assertEqual(state.financial_cumulative_profit, 620.0)
        self.assertEqual(
            state._financial_chart_columns()["profit"], [170.0, 450.0]
        )
        state.choose_financial_month("invalid")
        self.assertEqual(state.financial_month, "2026-09")
        state.choose_financial_month("ALL")
        self.assertEqual(state.financial_subtotals["total"], 620.0)
        with patch(
            "app.states.dashboard_state._gaborone_date",
            return_value=date(2026, 10, 3),
        ):
            self.assertEqual(state.financial_expected_inflows, 1950.0)

    def test_verified_receipt_dedup_conflicts_and_validation(self):
        receipts = [self.payment, self.payment.copy()]
        self.assertEqual(
            _financial_month_rows([], receipts)[0]["extension"], 450.0
        )
        for extra in (
            {**self.payment, "cash": 501.0},
            {**self.payment, "status": "Pending"},
        ):
            self.assertEqual(
                _financial_month_rows([], [self.payment, extra])[0][
                    "extension"
                ],
                0.0,
            )
        for update in (
            {"extension_id": ""},
            {"status": "Pending"},
            {"interest": 501.0},
            {"interest": float("nan")},
            {"cash": float("inf")},
            {"payment_date": "invalid"},
        ):
            rows = _financial_month_rows([], [{**self.payment, **update}])
            self.assertEqual(sum(row["extension"] for row in rows), 0.0)
        normalized = {**self.payment, "payment_date": "10/03/2026"}
        rows = _financial_month_rows([], [self.payment, normalized])
        self.assertEqual(
            rows[0]["extension"],
            _monthly_realized_interest(
                [], [self.payment, normalized], "2026-10"
            ),
        )
        self.assertEqual(rows[0]["extension"], 450.0)

    def test_liquidation_separate_and_all_zero_source_months(self):
        sold = {
            **self.settled,
            "ticket": "SOLD",
            "issue_date": "2026-07-01",
            "approved": 1000.0,
            "principal": 1000.0,
            "liquidation_status": "Sold",
            "sale_date": "2026-11-05",
            "final_revenue": 800.0,
            "settlement_realized_profit": 999.0,
        }
        zero = {**EMPTY_RECORD, "ticket": "ZERO", "issue_date": "2026-06-01"}
        rows = _financial_month_rows(
            [self.loan, self.settled, sold, zero], [self.payment]
        )
        self.assertEqual(
            [row["month"] for row in rows],
            ["2026-11", "2026-10", "2026-09", "2026-07", "2026-06"],
        )
        self.assertEqual(rows[0]["liquidation"], -200.0)
        self.assertEqual(rows[0]["settlement"], 0.0)
        self.assertEqual(rows[2]["settlement"], 170.0)
        self.assertEqual(sum(row["total"] for row in rows), 420.0)
        self.assertEqual(rows[-1]["total"], 0.0)

    def test_forecast_boundaries_exclusions_and_no_duplicate_loans(self):
        today = date(2026, 10, 3)
        records = []
        for index, offset in enumerate((0, 30, -1, 31)):
            records.append(
                {
                    **self.loan,
                    "ticket": str(index),
                    "due_date": (today + timedelta(days=offset)).isoformat(),
                    "total_due": 100.0,
                }
            )
        records.extend(
            [
                records[0].copy(),
                {**self.loan, "ticket": "bad", "due_date": "invalid"},
                {**self.loan, "ticket": "settled", "status": "Settled"},
                {**self.loan, "ticket": "sold", "liquidation_status": "Sold"},
                {**self.loan, "ticket": "default", "status": "Defaulted"},
                {
                    **self.loan,
                    "ticket": "date-settled",
                    "date_settled": "2026-10-01",
                },
                {**self.loan, "ticket": "nan", "total_due": float("nan")},
            ]
        )
        self.assertEqual(_financial_expected_inflows(records, today), 200.0)
        self.state.records = [self.loan, self.loan.copy()]
        self.assertEqual(self.state.financial_total_deployed, 1500.0)

    def test_empty_and_read_only_reporting(self):
        records = copy.deepcopy(self.state.records)
        payments = copy.deepcopy(self.state.extension_payments)
        with patch(
            "app.states.dashboard_state._read_live_records",
            side_effect=AssertionError("No external reads"),
        ):
            self.assertEqual(self.state.financial_cumulative_profit, 620.0)
            self.state.choose_financial_month("2026-10")
            self.state._financial_chart_columns()
        self.assertEqual(self.state.records, records)
        self.assertEqual(self.state.extension_payments, payments)
        self.state.records = []
        self.state.extension_payments = []
        self.assertEqual(self.state.financial_rows, [])
        self.assertEqual(self.state.financial_cumulative_profit, 0.0)
        self.assertEqual(self.state.financial_total_deployed, 0.0)
        self.assertEqual(
            self.state.financial_subtotals,
            {
                "settlement": 0.0,
                "extension": 0.0,
                "liquidation": 0.0,
                "total": 0.0,
            },
        )
        self.assertEqual(
            self.state._financial_chart_columns(),
            {"month": [], "deployed": [], "profit": []},
        )


if __name__ == "__main__":
    unittest.main()
