import unittest

from app.states.dashboard_state import DashboardState, EMPTY_RECORD


class LedgerFilteringTests(unittest.TestCase):
    def setUp(self):
        self.state = DashboardState(_reflex_internal_init=True)
        self.records = [
            {
                **EMPTY_RECORD,
                "ticket": "ACTIVE",
                "customer": "Ada",
                "status": "Active",
            },
            {
                **EMPTY_RECORD,
                "ticket": "EXTENDED",
                "customer": "Bola",
                "status": "Extended",
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
