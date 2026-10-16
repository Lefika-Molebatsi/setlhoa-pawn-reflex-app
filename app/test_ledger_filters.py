import unittest

from app.states.dashboard_state import (
    DashboardState,
    EMPTY_RECORD,
    _ledger_record_matches,
    _record_date_settled,
)


class LedgerFilteringTests(unittest.TestCase):
    def setUp(self):
        self.state = DashboardState(_reflex_internal_init=True)
        self.state.ledger_search = ""
        self.state.status_filter = "ALL"
        self.state.active_tab = "dashboard"
        self.state.selected_ticket = ""
        self.records = [
            {
                **EMPTY_RECORD,
                "ticket": "ACTIVE",
                "customer": "Ada",
                "status": "Active",
                "date_settled": "—",
            },
            {
                **EMPTY_RECORD,
                "ticket": "EXTENDED",
                "customer": "Bola",
                "status": "Extended",
                "date_settled": _record_date_settled(
                    {"Payment Date": "2026-10-03"}, "Extended"
                ),
                "payment_date": "2026-10-03",
            },
            {**EMPTY_RECORD, "ticket": "SETTLED", "status": "Settled"},
            {**EMPTY_RECORD, "ticket": "DEFAULTED", "status": "Defaulted"},
            {
                **EMPTY_RECORD,
                "ticket": "STALE-SETTLED",
                "status": "Active",
                "date_settled": "2026-09-10",
            },
            {
                **EMPTY_RECORD,
                "ticket": "SOLD",
                "status": "Extended",
                "liquidation_status": "Sold",
            },
        ]
        self.state.records = self.records

    def test_active_ledger_defaults_to_open_on_navigation(self):
        self.state.status_filter = "Settled"
        self.state.choose_tab("ledger")
        self.assertEqual(self.state.active_tab, "ledger")
        self.assertEqual(self.state.status_filter, "OPEN")
        self.assertEqual(
            [record["ticket"] for record in self.state.filtered_records],
            ["ACTIVE", "EXTENDED"],
        )

    def test_open_filter_includes_extended_and_excludes_settled_or_sold(self):
        self.state.status_filter = "OPEN"
        tickets = {record["ticket"] for record in self.state.filtered_records}
        self.assertEqual(tickets, {"ACTIVE", "EXTENDED"})

    def test_em_dash_settlement_placeholder_does_not_hide_active_record(self):
        active = self.records[0]
        self.assertEqual(active["date_settled"], "—")
        self.assertTrue(_ledger_record_matches(active, "OPEN", ""))

    def test_extended_payment_date_is_not_normalized_as_settlement_date(self):
        extended = self.records[1]
        self.assertEqual(extended["payment_date"], "2026-10-03")
        self.assertEqual(extended["date_settled"], "—")
        self.assertTrue(_ledger_record_matches(extended, "OPEN", ""))

    def test_settlement_date_normalization_preserves_settled_payment_fallback(
        self,
    ):
        self.assertEqual(
            _record_date_settled({"Payment Date": "2026-10-03"}, "Settled"),
            "2026-10-03",
        )
        self.assertEqual(
            _record_date_settled(
                {"Date Settled": "2026-09-29", "Payment Date": "2026-10-03"},
                "Settled",
            ),
            "2026-09-29",
        )

    def test_real_settlement_marker_excludes_open_status_even_if_active(self):
        stale_settled = next(
            record
            for record in self.records
            if record["ticket"] == "STALE-SETTLED"
        )
        self.assertFalse(_ledger_record_matches(stale_settled, "OPEN", ""))

    def test_all_statuses_shows_every_source_record(self):
        self.state.status_filter = "ALL"
        self.assertEqual(
            {record["ticket"] for record in self.state.filtered_records},
            {record["ticket"] for record in self.records},
        )

    def test_payment_tab_defaults_to_all_and_switch_resets_filter(self):
        self.state.choose_tab("ledger")
        self.state.choose_tab("payments")
        self.assertEqual(self.state.status_filter, "ALL")
        self.assertEqual(len(self.state.filtered_records), len(self.records))
        self.state.set_status_filter("Settled")
        self.state.choose_tab("ledger")
        self.assertEqual(self.state.status_filter, "OPEN")
        self.state.choose_tab("payments")
        self.assertEqual(self.state.status_filter, "ALL")

    def test_status_selection_and_text_search_are_applied(self):
        self.state.set_status_filter("Extended")
        self.assertEqual(
            [record["ticket"] for record in self.state.filtered_records],
            ["EXTENDED", "SOLD"],
        )
        self.state.set_search("bola")
        self.assertEqual(
            [record["ticket"] for record in self.state.filtered_records],
            ["EXTENDED"],
        )
        self.state.set_status_filter("Settled")
        self.assertEqual(self.state.status_filter, "Settled")
        self.assertEqual(self.state.filtered_records, [])

    def test_filter_and_search_clear_selection_when_ticket_is_hidden(self):
        self.state.select_ticket("SETTLED")
        self.state.set_status_filter("OPEN")
        self.assertEqual(self.state.selected_ticket, "")

        self.state.set_status_filter("ALL")
        self.state.select_ticket("ACTIVE")
        self.state.set_search("no match")
        self.assertEqual(self.state.selected_ticket, "")

    def test_navigation_clears_selected_ticket_between_operations_tabs(self):
        self.state.choose_tab("ledger")
        self.state.select_ticket("ACTIVE")
        self.state.choose_tab("payments")
        self.assertEqual(self.state.selected_ticket, "")
        self.assertEqual(self.state.status_filter, "ALL")

    def test_unrecognized_status_filter_does_not_change_applied_filter(self):
        self.state.set_status_filter("Unknown")
        self.assertEqual(self.state.status_filter, "ALL")


if __name__ == "__main__":
    unittest.main()
