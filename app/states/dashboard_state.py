import asyncio
import hashlib
import json
import logging
import os
import re
import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from typing import Iterable, TypedDict
from urllib.parse import quote
from zoneinfo import ZoneInfo

import reflex as rx


class LoanRecord(TypedDict):
    ticket: str
    issue_date: str
    contact: str
    item_category: str
    description: str
    interest_rate: float
    interest_rate_display: str
    day_23: str
    day_23_status: str
    day_30_action: str
    day_30_status: str
    day_35: str
    day_35_status: str
    daily_penalty: float
    days_overdue: int
    late_fees: float
    final_payout: float
    cash_tendered: float
    settlement_principal: float
    settlement_interest: float
    settlement_late_fees: float
    retained_overpayment: float
    settlement_realized_profit: float
    settlement_required_total: float
    date_settled: str
    remarks: str
    loan_date: str
    due_date: str
    month: str
    customer: str
    omang: str
    mobile: str
    category: str
    item: str
    estimated_value: float
    principal: float
    approved: float
    interest: float
    total_due: float
    remaining_principal: float
    status: str
    payment_date: str
    liquidation_status: str
    sale_date: str
    final_revenue: float
    realized_profit: float
    recommended_price: float
    submission_id: str
    extension_pending: bool


NOTICE_TEMPLATES: dict[str, str] = {
    "Pre-Due": "Hello. A friendly reminder that your loan {ticket} is due in 7 days. To settle or extend your loan, please contact us at 74927495/72796888.",
    "Due Today": "Hello. Your loan {ticket} is due Today. Please arrange payment today to maintain your loan in good standing. Call/WhatsApp 74927495/72796888 for bank/e-wallet details.",
    "Final Warning": "Hello. Your loan ticket {ticket} is now 5 days overdue. Please settle by the end of the day to safeguard your item from liquidation. Contact us immediately at 74927495/72796888.",
}


def _notice_text(notice_type: str, ticket: str) -> str:
    template = NOTICE_TEMPLATES.get(notice_type, NOTICE_TEMPLATES["Pre-Due"])
    return template.format(ticket=ticket)


EMPTY_RECORD: LoanRecord = {
    "ticket": "",
    "issue_date": "",
    "contact": "",
    "item_category": "",
    "description": "",
    "interest_rate": 0.0,
    "interest_rate_display": "0%",
    "day_23": "",
    "day_23_status": "",
    "day_30_action": "",
    "day_30_status": "",
    "day_35": "",
    "day_35_status": "",
    "daily_penalty": 0.0,
    "days_overdue": 0,
    "late_fees": 0.0,
    "final_payout": 0.0,
    "cash_tendered": 0.0,
    "settlement_principal": 0.0,
    "settlement_interest": 0.0,
    "settlement_late_fees": 0.0,
    "retained_overpayment": 0.0,
    "settlement_realized_profit": 0.0,
    "settlement_required_total": 0.0,
    "date_settled": "",
    "remarks": "",
    "loan_date": "",
    "due_date": "",
    "month": "",
    "customer": "",
    "omang": "",
    "mobile": "",
    "category": "",
    "item": "",
    "estimated_value": 0.0,
    "principal": 0.0,
    "approved": 0.0,
    "interest": 0.0,
    "total_due": 0.0,
    "remaining_principal": 0.0,
    "status": "",
    "payment_date": "",
    "liquidation_status": "",
    "sale_date": "",
    "final_revenue": 0.0,
    "realized_profit": 0.0,
    "recommended_price": 0.0,
    "submission_id": "",
    "extension_pending": False,
}


class ExtensionPayment(TypedDict):
    extension_id: str
    ticket: str
    submission_id: str
    payment_date: str
    old_due: str
    new_due: str
    cash: float
    interest: float
    excess: float
    principal: float
    status: str


class SettlementAmounts(TypedDict):
    principal: Decimal
    interest: Decimal
    late_fees: Decimal
    required: Decimal
    tender: Decimal
    retained: Decimal
    profit: Decimal


class SettlementDisplay(TypedDict):
    principal: str
    interest: str
    late_fees: str
    required: str
    tender: str
    retained: str
    profit: str
    error: str


CENT = Decimal("0.01")


def _settlement_money(value: str | float | Decimal) -> Decimal:
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or amount < 0:
            raise ValueError("Amount must be a finite, non-negative number.")
        return amount.quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as e:
        logging.exception("Unexpected error")
        raise ValueError("Amount must be a finite, non-negative number.") from e


def _settlement_cash(value: str) -> Decimal:
    text = str(value or "").strip()
    if not text:
        return Decimal("0.00")
    if not re.fullmatch(
        r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?|\.\d{1,2}", text
    ):
        raise ValueError(
            "Enter a valid non-negative cash amount with at most two decimal places."
        )
    return _settlement_money(text.replace(",", ""))


def _calculate_settlement(
    principal: Decimal,
    interest: Decimal,
    late_fees: Decimal,
    tender: Decimal,
    enforce_required: bool = True,
) -> SettlementAmounts:
    """Pure two-decimal settlement accounting; retained cash is not refunded change."""
    principal = _settlement_money(principal)
    interest = _settlement_money(interest)
    late_fees = _settlement_money(late_fees)
    tender = _settlement_money(tender)
    required = principal + interest + late_fees
    if enforce_required and tender < required:
        raise ValueError(
            f"Cash tendered is short by P{required - tender:,.2f}. Required: P{required:,.2f}."
        )
    retained = max(Decimal("0.00"), tender - required)
    return {
        "principal": principal,
        "interest": interest,
        "late_fees": late_fees,
        "required": required,
        "tender": tender,
        "retained": retained,
        "profit": interest + late_fees + retained,
    }


def _settlement_display(
    record: LoanRecord, cash: str, today: date
) -> SettlementDisplay:
    display: SettlementDisplay = {
        "principal": "—",
        "interest": "—",
        "late_fees": "—",
        "required": "—",
        "tender": "P0.00",
        "retained": "P0.00",
        "profit": "P0.00",
        "error": "",
    }
    try:
        principal = _settlement_money(record["remaining_principal"])
        interest = _settlement_money(record["interest"])
        due = _date_value(record["due_date"])
        late_fees = (
            _settlement_money(
                record["daily_penalty"] * max(0, (today - due).days)
            )
            if due
            else _settlement_money(record["late_fees"])
        )
        required = principal + interest + late_fees
        display.update(
            {
                "principal": f"P{principal:,.2f}",
                "interest": f"P{interest:,.2f}",
                "late_fees": f"P{late_fees:,.2f}",
                "required": f"P{required:,.2f}",
            }
        )
        tender = _settlement_cash(cash)
        amounts = _calculate_settlement(
            principal, interest, late_fees, tender, enforce_required=False
        )
        display["tender"] = f"P{amounts['tender']:,.2f}"
        display["retained"] = f"P{amounts['retained']:,.2f}"
        display["profit"] = f"P{amounts['profit']:,.2f}"
        if tender < amounts["required"]:
            display["error"] = (
                f"Cash tendered is short by P{amounts['required'] - tender:,.2f}. "
                f"Enter at least P{amounts['required']:,.2f} to settle."
            )
    except ValueError as e:
        display["error"] = str(e)
    return display


class ReminderRow(TypedDict):
    ticket: str
    customer: str
    contact: str
    issue_date: str
    maturity_date: str
    description: str
    total_due: float
    countdown_days: int
    countdown_label: str
    countdown_stage: str
    badge_color: str
    whatsapp_url: str
    whatsapp_available: bool
    valid_contact: bool


def _queue_stage(countdown_days: int) -> tuple[str, str, str]:
    """Return the strict milestone stage or a neutral queue display state."""
    if countdown_days == 7:
        return ("Day 23 Courtesy", "blue", "Day 23 · 7 days remaining")
    if countdown_days == 0:
        return ("Day 30 Due Today", "red", "Day 30 · Due today")
    if countdown_days == -5:
        return ("Day 35 Final Warning", "dark-red", "Day 35 · 5 days overdue")
    if countdown_days > 7:
        return (
            "On Track",
            "green",
            f"{countdown_days} days remaining · On Track",
        )
    return (
        "Between Milestones",
        "orange",
        f"{abs(countdown_days)} days from next milestone · Between Milestones",
    )


def _queue_notice_type(countdown_days: int) -> str:
    """Return a notice key only for an exact actionable countdown."""
    return {7: "Pre-Due", 0: "Due Today", -5: "Final Warning"}.get(
        countdown_days, ""
    )


def _whatsapp_link(mobile: str, ticket: str, countdown_days: int) -> str:
    """Build a wa.me link with normalized Botswana mobile and exact notice text."""
    normalized = _normalize_mobile(mobile)
    if not normalized:
        return ""
    notice_type = _queue_notice_type(countdown_days)
    if not notice_type:
        return ""
    message = _notice_text(notice_type, ticket)
    return f"https://wa.me/267{normalized}?text={quote(message)}"


class ReminderStage(TypedDict):
    reminder_type: str
    title_prefix: str
    day_label: str
    offset: int
    summary_key: str
    notice_key: str
    milestone_field: str


REMINDER_STAGES: tuple[ReminderStage, ...] = (
    {
        "reminder_type": "Day 23 Courtesy",
        "title_prefix": "COURTESY REMINDER",
        "day_label": "Day 23",
        "offset": -7,
        "summary_key": "day_23",
        "notice_key": "Pre-Due",
        "milestone_field": "day_23",
    },
    {
        "reminder_type": "Day 30 Due Today",
        "title_prefix": "DUE TODAY",
        "day_label": "Day 30",
        "offset": 0,
        "summary_key": "day_30",
        "notice_key": "Due Today",
        "milestone_field": "day_30_action",
    },
    {
        "reminder_type": "Day 35 Final Warning",
        "title_prefix": "FINAL WARNING",
        "day_label": "Day 35",
        "offset": 5,
        "summary_key": "day_35",
        "notice_key": "Final Warning",
        "milestone_field": "day_35",
    },
)

CALENDAR_TIMEZONE: str = "Africa/Gaborone"


def _reminder_display(value: str) -> str:
    """Safe display fallback for calendar payload fields."""
    text = str(value or "").strip()
    return text if text and text != "—" else "—"


def _reminder_event_title(
    stage: ReminderStage, customer: str, ticket: str
) -> str:
    return (
        f"{stage['title_prefix']} ({stage['day_label']}): "
        f"{_reminder_display(customer)} ({ticket})"
    )


def _reminder_event_description(
    stage: ReminderStage, record: LoanRecord, due: date
) -> str:
    ticket = record["ticket"]
    return (
        f"Customer: {_reminder_display(record['customer'])}\n"
        f"Phone: {_reminder_display(record['contact'] or record['mobile'])}\n"
        f"Item: {_reminder_display(record['description'] or record['item'])}\n"
        f"Total Due: P{record['total_due']:,.2f}\n"
        f"Due Date: {due.isoformat()} ({record['days_overdue']} days overdue)\n"
        f"Ticket: {ticket}\n\n"
        "--- READY TO SEND MSG ---\n"
        f"{_notice_text(stage['notice_key'], ticket)}"
    )


def _reminder_event_window(event_date: date) -> tuple[str, str]:
    """Timezone-aware RFC3339 09:00-09:15 window with a real UTC offset."""
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(CALENDAR_TIMEZONE)
        start = datetime(
            event_date.year, event_date.month, event_date.day, 9, 0, tzinfo=tz
        )
        end = start + timedelta(minutes=15)
        return start.isoformat(), end.isoformat()
    except Exception as e:
        logging.exception(f"Error: {e}")
        return (
            f"{event_date.isoformat()}T09:00:00+02:00",
            f"{event_date.isoformat()}T09:15:00+02:00",
        )


def _reminder_stage_date(
    stage: ReminderStage, record: LoanRecord, issue: date | None, due: date
) -> date | None:
    """All milestone dates are derived from the resolved due date."""
    return due + timedelta(days=stage["offset"])


def _reminder_event_payload(
    stage: ReminderStage, record: LoanRecord, event_date: date, due: date
) -> dict[str, object]:
    """Pure Google Calendar event body; issues no API calls."""
    start, end = _reminder_event_window(event_date)
    return {
        "summary": _reminder_event_title(
            stage, record["customer"], record["ticket"]
        ),
        "description": _reminder_event_description(stage, record, due),
        "start": {"dateTime": start, "timeZone": CALENDAR_TIMEZONE},
        "end": {"dateTime": end, "timeZone": CALENDAR_TIMEZONE},
        "extendedProperties": {
            "private": {
                "setlhoa_managed": "true",
                "ticket": record["ticket"],
                "reminder_type": stage["reminder_type"],
            }
        },
    }


def _reminder_payloads_for_record(
    record: LoanRecord,
) -> list[tuple[ReminderStage, dict[str, object]]]:
    "All three stage payloads for one Active, resolvable loan record."
    if record["status"] != "Active" or not record["ticket"]:
        return []
    issue = _date_value(record["issue_date"]) or _date_value(
        record["loan_date"]
    )
    due = _resolved_due_date(record["due_date"], issue, "normalized")
    if due is None:
        return []
    payloads: list[tuple[ReminderStage, dict[str, object]]] = []
    for stage in REMINDER_STAGES:
        event_date = _reminder_stage_date(stage, record, issue, due)
        if event_date is None:
            continue
        payloads.append(
            (stage, _reminder_event_payload(stage, record, event_date, due))
        )
    return payloads


def _match_managed_event(
    events: list[dict[str, object]], ticket: str, reminder_type: str
) -> dict[str, object] | None:
    """Exact in-Python match; list filters may use OR semantics."""
    for event in events:
        props = (
            (event.get("extendedProperties") or {}).get("private") or {}
            if isinstance(event, dict)
            else {}
        )
        if (
            str(props.get("setlhoa_managed", "")) == "true"
            and str(props.get("ticket", "")) == ticket
            and str(props.get("reminder_type", "")) == reminder_type
        ):
            return event
    return None


class ReminderSummary(TypedDict):
    day_23: int
    day_30: int
    day_35: int
    managed: int
    message: str


class DashboardState(rx.State):
    records: list[LoanRecord] = []
    extension_payments: list[ExtensionPayment] = []
    extension_ledger_message: str = (
        "Refresh Sheets to load persisted extension payments."
    )
    months: list[str] = []
    selected_month: str = "ALL"
    is_loading: bool = False
    is_reconciling: bool = False
    error_message: str = ""
    success_message: str = ""
    sheets_health: str = "Not checked"
    calendar_health: str = "Not checked"
    worksheet_name: str = ""
    last_refresh: str = "Not yet refreshed"
    reminder_summary: ReminderSummary = {
        "day_23": 0,
        "day_30": 0,
        "day_35": 0,
        "managed": 0,
        "message": "Not reconciled",
    }
    active_tab: str = "dashboard"
    ledger_search: str = ""
    status_filter: str = "ALL"
    selected_ticket: str = ""
    notice_type: str = "Pre-Due"
    payment_amount: str = ""
    payment_date: str = ""
    confirmation_text: str = ""
    delete_confirmed: bool = False
    operation_loading: bool = False
    extension_error: str = ""
    liquidation_search: str = ""
    liquidation_sort: str = "profit"
    inventory_search: str = ""
    history_search: str = ""
    selected_customer_key: str = ""
    sale_revenue: str = ""
    sale_date: str = ""
    sale_confirmed: bool = False
    vehicle_market_value: str = ""
    electronics_market_value: str = ""
    vehicle_value_error: str = ""
    electronics_value_error: str = ""

    @rx.var
    def vehicle_market_amount(self) -> float:
        return self._calculator_amount(self.vehicle_market_value)

    @rx.var
    def electronics_market_amount(self) -> float:
        return self._calculator_amount(self.electronics_market_value)

    @rx.var
    def vehicle_safe_loan(self) -> float:
        return self.vehicle_market_amount * 0.4

    @rx.var
    def electronics_safe_loan(self) -> float:
        return self.electronics_market_amount * 0.4

    @rx.var
    def vehicle_interest_amount(self) -> float:
        return self.vehicle_safe_loan * 0.15

    @rx.var
    def electronics_interest_amount(self) -> float:
        return self.electronics_safe_loan * 0.3

    @rx.var
    def vehicle_repayment(self) -> float:
        return self.vehicle_safe_loan + self.vehicle_interest_amount

    @rx.var
    def electronics_repayment(self) -> float:
        return self.electronics_safe_loan + self.electronics_interest_amount

    @rx.var
    def vehicle_default_profit(self) -> float:
        return self.vehicle_market_amount - self.vehicle_safe_loan

    @rx.var
    def electronics_default_profit(self) -> float:
        return self.electronics_market_amount - self.electronics_safe_loan

    @rx.event
    def set_vehicle_market_value(self, value: str):
        self.vehicle_market_value = value
        self.vehicle_value_error = self._calculator_error(value)

    @rx.event
    def set_electronics_market_value(self, value: str):
        self.electronics_market_value = value
        self.electronics_value_error = self._calculator_error(value)

    @rx.event
    def reset_vehicle_calculator(self):
        self.vehicle_market_value = ""
        self.vehicle_value_error = ""

    @rx.event
    def reset_electronics_calculator(self):
        self.electronics_market_value = ""
        self.electronics_value_error = ""

    def _calculator_amount(self, value: str) -> float:
        try:
            amount = float(value.replace(",", "").strip() or 0)
            return amount if amount >= 0 else 0.0
        except (ValueError, TypeError) as e:
            logging.exception(f"Error: {e}")
            return 0.0

    def _calculator_error(self, value: str) -> str:
        try:
            amount = float(value.replace(",", "").strip() or 0)
            return "" if amount >= 0 else "Enter a non-negative pula amount."
        except (ValueError, TypeError) as e:
            logging.exception(f"Error: {e}")
            return "Enter a valid non-negative pula amount."

    @rx.var
    def filtered_records(self) -> list[LoanRecord]:
        query = self.ledger_search.lower().strip()
        return [
            record
            for record in self.records
            if (
                self.status_filter == "ALL"
                or record["status"] == self.status_filter
            )
            and (
                not query
                or query
                in f"{record['ticket']} {record['customer']} {record['mobile']} {record['category']} {record['item']}".lower()
            )
        ]

    @rx.var
    def reminder_queue(self) -> list[ReminderRow]:
        today = _gaborone_date()
        rows: list[ReminderRow] = []
        for record in self.records:
            if record["status"] not in {"Active", "Extended"}:
                continue
            issue = _date_value(record["issue_date"]) or _date_value(
                record["loan_date"]
            )
            due = _resolved_due_date(record["due_date"], issue, "normalized")
            if due is None:
                continue
            countdown = (due - today).days
            stage, color, label = _queue_stage(countdown)
            url = _whatsapp_link(
                _first_valid_mobile(record["mobile"], record["contact"]),
                record["ticket"],
                countdown,
            )
            rows.append(
                {
                    "ticket": record["ticket"],
                    "customer": record["customer"] or "—",
                    "contact": record["contact"] or record["mobile"] or "—",
                    "issue_date": issue.isoformat() if issue else "—",
                    "maturity_date": due.isoformat(),
                    "description": record["description"]
                    or record["item"]
                    or "—",
                    "total_due": record["total_due"],
                    "countdown_days": countdown,
                    "countdown_label": label,
                    "countdown_stage": stage,
                    "badge_color": color,
                    "whatsapp_url": url,
                    "whatsapp_available": bool(url),
                    "valid_contact": bool(
                        _first_valid_mobile(record["mobile"], record["contact"])
                    ),
                }
            )
        rows.sort(
            key=lambda row: (
                row["countdown_days"],
                row["maturity_date"],
                row["ticket"],
            )
        )
        return rows

    @rx.var
    def reminder_queue_count(self) -> int:
        return len(self.reminder_queue)

    @rx.var
    def inventory_records(self) -> list[LoanRecord]:
        query = self.inventory_search.lower().strip()
        return sorted(
            [
                record
                for record in self.records
                if record["status"] == "Defaulted"
                and not _is_sold(record["liquidation_status"])
                and query
                in f"{record['ticket']} {record['customer']} {record['item']} {record['description']}".lower()
            ],
            key=lambda record: (
                record["recommended_price"] - record["principal"]
            ),
            reverse=True,
        )

    @rx.var
    def selected_inventory_item(self) -> bool:
        record = self.selected_record
        return (
            bool(record["ticket"])
            and record["status"] == "Defaulted"
            and not _is_sold(record["liquidation_status"])
        )

    @rx.var
    def liquidation_records(self) -> list[LoanRecord]:
        query = self.liquidation_search.lower().strip()
        records: list[LoanRecord] = []
        for record in self.records:
            if (
                _is_sold(record["liquidation_status"])
                and query
                in f"{record['ticket']} {record['customer']} {record['item']} {record['description']}".lower()
            ):
                sold = record.copy()
                sold["realized_profit"] = (
                    record["final_revenue"] - record["principal"]
                )
                records.append(sold)
        if self.liquidation_sort == "newest":
            return sorted(
                records,
                key=lambda r: (
                    _date_value(r["sale_date"]) or date.min,
                    r["ticket"],
                ),
                reverse=True,
            )
        return sorted(
            records,
            key=lambda r: (r["realized_profit"], r["ticket"]),
            reverse=True,
        )

    @rx.var
    def sold_count(self) -> int:
        return len(self.liquidation_records)

    @rx.var
    def sold_sales(self) -> float:
        return _sum_cents(r["final_revenue"] for r in self.liquidation_records)

    @rx.var
    def sold_principal(self) -> float:
        return _sum_cents(r["principal"] for r in self.liquidation_records)

    @rx.var
    def sold_profit(self) -> float:
        return _sum_cents(
            r["realized_profit"] for r in self.liquidation_records
        )

    @rx.var
    def sale_profit_preview(self) -> float:
        revenue = _money(self.sale_revenue)
        return (
            revenue - self.selected_record["principal"]
            if math.isfinite(revenue)
            else 0.0
        )

    @rx.event
    def set_inventory_search(self, value: str):
        self.inventory_search = value

    @rx.event
    def select_inventory_ticket(self, ticket: str):
        self.selected_ticket = ticket
        self.sale_revenue = ""
        self.sale_date = _gaborone_date().isoformat()
        self.sale_confirmed = False
        self.error_message = ""
        self.success_message = ""

    @rx.var
    def history_records(self) -> list[LoanRecord]:
        query = self.history_search.lower().strip()
        if not query:
            return []
        return [
            record
            for record in self.records
            if (
                record["omang"] not in {"", "—"}
                and query in record["omang"].lower()
            )
            or query in _normalize_mobile(record["mobile"])
        ]

    @rx.var
    def selected_customer_records(self) -> list[LoanRecord]:
        if not self.selected_customer_key:
            return []
        return [
            record
            for record in self.records
            if (
                record["omang"] not in {"", "—"}
                and record["omang"] == self.selected_customer_key
            )
            or (
                not self.selected_customer_key.startswith("omang:")
                and _normalize_mobile(record["mobile"])
                == self.selected_customer_key
            )
        ]

    @rx.var
    def customer_risk(self) -> str:
        records = self.selected_customer_records
        if any(record["status"] == "Defaulted" for record in records):
            return "High Risk"
        if any(record["status"] == "Extended" for record in records) or not any(
            record["status"] == "Settled" for record in records
        ):
            return "Moderate Risk"
        return "Good Standing"

    @rx.var
    def customer_risk_reason(self) -> str:
        records = self.selected_customer_records
        if any(record["status"] == "Defaulted" for record in records):
            return "A default is present in the matched loan history."
        if any(record["status"] == "Extended" for record in records):
            return "No defaults, but one or more extensions are recorded."
        if not any(record["status"] == "Settled" for record in records):
            return "No default is recorded, but no settled loan history is available."
        return "At least one settled loan and no extensions or defaults."

    @rx.event
    def set_liquidation_search(self, value: str):
        self.liquidation_search = value

    @rx.event
    def set_liquidation_sort(self, value: str):
        self.liquidation_sort = value

    @rx.event
    def set_history_search(self, value: str):
        self.history_search = value
        self.selected_customer_key = ""

    @rx.event
    def select_customer(self, key: str):
        for record in self.history_records:
            if record["omang"] not in {"", "—"} and key == record["omang"]:
                self.selected_customer_key = key
                return
            mobile = _normalize_mobile(record["mobile"])
            if mobile and _normalize_mobile(key) == mobile:
                self.selected_customer_key = mobile
                return

    @rx.event
    def set_sale_revenue(self, value: str):
        self.sale_revenue = value
        self.sale_confirmed = False

    @rx.event
    def set_sale_date(self, value: str):
        self.sale_date = value
        self.sale_confirmed = False

    @rx.event
    def toggle_sale_confirmation(self):
        self.sale_confirmed = not self.sale_confirmed

    @rx.event
    async def submit_sale(self):
        if self.operation_loading:
            return
        if not self.selected_inventory_item or not self.sale_confirmed:
            self.error_message = (
                "Select a defaulted ticket and confirm the sale write."
            )
            return
        self.operation_loading = True
        self.error_message = ""
        self.success_message = ""
        try:
            revenue = _money(self.sale_revenue)
            if (
                not math.isfinite(revenue)
                or revenue <= 0
                or not _date_value(self.sale_date)
            ):
                raise ValueError(
                    "Enter a positive final sale price and valid sale date."
                )
            result = await asyncio.to_thread(
                _record_sale, self.selected_ticket, revenue, self.sale_date
            )
            self.sale_confirmed = False
            self.selected_ticket = ""
            self.sale_revenue = ""
            self.sale_date = ""
            await self.refresh_sheets()
            self.success_message = result
        except ValueError as e:
            logging.exception(f"Error: {e}")
            self.error_message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error_message = "Sale write failed; refresh Sheets to verify the item before retrying."
        finally:
            self.operation_loading = False

    @rx.var
    def selected_record(self) -> LoanRecord:
        for record in self.records:
            if record["ticket"] == self.selected_ticket:
                return record
        return dict(EMPTY_RECORD)

    @rx.var
    def settlement_eligible(self) -> bool:
        record = self.selected_record
        return (
            bool(record["ticket"])
            and record["status"] in {"Active", "Extended"}
            and not _is_sold(record["liquidation_status"])
        )

    @rx.var
    def settlement_preview(self) -> SettlementDisplay:
        if not self.settlement_eligible:
            return {
                "principal": "—",
                "interest": "—",
                "late_fees": "—",
                "required": "—",
                "tender": "—",
                "retained": "—",
                "profit": "—",
                "error": "",
            }
        return _settlement_display(
            self.selected_record, self.payment_amount, _gaborone_date()
        )

    @rx.var
    def extension_validation(self) -> str:
        if self.extension_error:
            return self.extension_error
        if self.selected_record["extension_pending"]:
            return "Saved extension needs reconciliation before another payment. No additional cash is required."
        if not self.settlement_eligible:
            return "Select an unsold Active or Extended ticket to extend."
        try:
            _extension_cash(
                self.payment_amount, self.selected_record["interest"]
            )
            if _date_value(self.selected_record["due_date"]) is None:
                return "Due date is unresolved. Correct the worksheet to ISO and refresh before extending."
        except ValueError as e:
            return str(e)
        return ""

    @rx.event
    async def extend_ticket(self):
        if self.operation_loading or self.is_loading:
            return
        self.error_message = ""
        self.success_message = ""
        self.extension_error = ""
        if not self.settlement_eligible:
            self.extension_error = (
                "Select an unsold Active or Extended ticket before extending."
            )
            return
        expected = self.selected_record.copy()
        if expected["extension_pending"]:
            self.extension_error = "Reconcile the saved extension first; do not collect another payment."
            return
        try:
            _extension_cash(self.payment_amount, expected["interest"])
            if _date_value(expected["due_date"]) is None:
                raise ValueError(
                    "Due date is unresolved. Correct it to ISO in Sheets and refresh first."
                )
            self.operation_loading = True
            yield
            result = await asyncio.to_thread(
                _record_extension, expected, self.payment_amount
            )
            self.success_message = result
            self.payment_amount = ""
            self.selected_ticket = ""
            try:
                payload = await asyncio.to_thread(_read_live_records)
                self.records = payload["records"]
                self.extension_payments = payload["extension_payments"]
                self.extension_ledger_message = payload[
                    "extension_ledger_message"
                ]
                self.months = payload["months"]
                self.worksheet_name = payload["worksheet"]
                self.sheets_health = (
                    f"Connected · {len(self.records)} live records"
                )
                self.calendar_health = payload["calendar_health"]
                self.last_refresh = _gaborone_now()
            except Exception as e:
                logging.exception(f"Error: {e}")
                self.error_message = "Extension saved and verified, but refresh failed. Refresh Sheets; do not repeat the payment."
                self.sheets_health = "Refresh needed"
        except ValueError as e:
            self.extension_error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.extension_error = "Extension could not be confirmed. Inspect the live due date and payment in Sheets before doing anything else; Retry the same snapshot to verify the existing transaction, or refresh and use Reconcile saved extension; do not collect cash again."
        finally:
            self.operation_loading = False

    @rx.var
    def notice_message(self) -> str:
        return _notice_text(self.notice_type, self.selected_record["ticket"])

    @rx.var
    def whatsapp_url(self) -> str:
        normalized = _first_valid_mobile(
            self.selected_record["mobile"], self.selected_record["contact"]
        )
        if not normalized:
            return ""
        return (
            f"https://wa.me/267{normalized}?text={quote(self.notice_message)}"
        )

    @rx.event
    def set_search(self, value: str):
        self.ledger_search = value

    @rx.event
    def set_status_filter(self, value: str):
        self.status_filter = value

    @rx.event
    def select_ticket(self, ticket: str):
        if self.operation_loading:
            return
        self.selected_ticket = ticket
        self.payment_amount = ""
        self.extension_error = ""

    @rx.event
    def set_notice_type(self, value: str):
        self.notice_type = value

    @rx.event
    def set_payment_amount(self, value: str):
        if not self.operation_loading:
            self.payment_amount = value
            self.extension_error = ""

    @rx.event
    async def settle_ticket(self):
        if self.operation_loading:
            return
        self.error_message = ""
        self.success_message = ""
        if not self.settlement_eligible:
            self.error_message = "Select an unsold Active or Extended ticket before settling. Refresh Sheets if its status changed."
            return
        try:
            if self.selected_record["extension_pending"]:
                raise ValueError(
                    "Reconcile the saved extension payment before settling this ticket."
                )
            if not self.payment_amount.strip():
                raise ValueError("Enter a cash amount before settling.")
            _settlement_cash(self.payment_amount)
            record = self.selected_record.copy()
            preview = _settlement_display(
                record, self.payment_amount, _gaborone_date()
            )
            if preview["error"]:
                raise ValueError(preview["error"])
            self.operation_loading = True
            result = await asyncio.to_thread(
                _record_settlement,
                record["ticket"],
                record["submission_id"],
                self.payment_amount,
                record,
            )
            self.success_message = result
            self.selected_ticket = ""
            self.payment_amount = ""
            try:
                payload = await asyncio.to_thread(_read_live_records)
                self.records = payload["records"]
                self.months = payload["months"]
                self.worksheet_name = payload["worksheet"]
                self.sheets_health = (
                    f"Connected · {len(self.records)} live records"
                )
                self.calendar_health = payload["calendar_health"]
                self.last_refresh = _gaborone_now()
            except Exception:
                logging.exception("Unexpected error")
                logging.warning(
                    "Settlement committed but dashboard refresh failed"
                )
                self.error_message = "Settlement saved and verified in Sheets, but the dashboard could not sync. Refresh Sheets to update the ledger; do not settle this ticket again."
                self.sheets_health = "Refresh needed"
        except ValueError as e:
            self.error_message = str(e)
        except Exception:
            logging.exception("Unexpected error")
            logging.warning(
                "Settlement could not be confirmed; refresh before retrying"
            )
            self.error_message = "Settlement could not be confirmed. Refresh Sheets and check the live ticket before retrying; the write outcome may be uncertain. Check worksheet edit access if the problem persists."
        finally:
            self.operation_loading = False

    @rx.event
    def set_payment_date(self, value: str):
        self.payment_date = value

    @rx.event
    def toggle_delete_confirmation(self):
        self.delete_confirmed = not self.delete_confirmed

    @rx.event
    async def update_ticket_status(self, status: str):
        if status == "Settled":
            return DashboardState.settle_ticket
        if status == "Extended":
            return DashboardState.extend_ticket
        await self._mutate_ticket(
            "status", status, self.payment_amount, self.payment_date
        )

    @rx.event
    async def partial_payment(self):
        await self._mutate_ticket(
            "partial", self.payment_amount, self.payment_date, ""
        )

    @rx.event
    async def interest_extension(self):
        return DashboardState.extend_ticket

    @rx.event
    async def delete_ticket(self):
        if (
            not self.selected_ticket
            or not self.delete_confirmed
            or self.confirmation_text != self.selected_ticket
        ):
            self.error_message = "Select a ticket and type its ticket number with confirmation enabled."
            return
        await self._mutate_ticket("delete", "", "", "")

    async def _mutate_ticket(
        self, operation: str, value: str, second: str, third: str
    ):
        if self.operation_loading:
            return
        if not self.selected_ticket:
            self.error_message = (
                "Select a ticket before performing an operation."
            )
            return
        self.operation_loading = True
        self.error_message = ""
        self.success_message = ""
        try:
            result = await asyncio.to_thread(
                _mutate_live_ticket,
                self.selected_ticket,
                operation,
                value,
                second,
                third,
            )
            self.success_message = result
            self.selected_ticket = ""
            self.confirmation_text = ""
            self.delete_confirmed = False
            await self.refresh_sheets()
            self.success_message = result
            if operation == "status" and value == "Defaulted":
                self.inventory_search = ""
                self.active_tab = "inventory"
        except ValueError as e:
            self.error_message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error_message = "Operation failed safely. Verify the ticket and integration access."
        self.operation_loading = False

    @rx.var
    def visible_records(self) -> list[LoanRecord]:
        if self.selected_month == "ALL":
            return self.records
        return [
            record
            for record in self.records
            if record["month"] == self.selected_month
        ]

    @rx.var
    def deployed_capital(self) -> float:
        return _sum_cents(
            record["remaining_principal"]
            for record in self.visible_records
            if record["status"] != "Settled"
            and not _is_sold(record["liquidation_status"])
        )

    @rx.var
    def realized_interest(self) -> float:
        month = (
            self.selected_month
            if self.selected_month != "ALL"
            else _gaborone_date().strftime("%Y-%m")
        )
        return _monthly_realized_interest(
            self.records, self.extension_payments, month
        )

    @rx.var
    def visible_extension_payments(self) -> list[ExtensionPayment]:
        query = self.ledger_search.strip().casefold()
        return [
            p
            for p in self.extension_payments
            if (
                self.selected_month == "ALL"
                or p["payment_date"][:7] == self.selected_month
            )
            and (not query or query in p["ticket"].casefold())
        ]

    @rx.var
    def customer_extension_payments(self) -> list[ExtensionPayment]:
        identities = {
            (r["ticket"], r["submission_id"])
            for r in self.selected_customer_records
        }
        return [
            p
            for p in self.extension_payments
            if (p["ticket"], p["submission_id"]) in identities
        ]

    @rx.event
    async def reconcile_extension(self):
        if (
            self.operation_loading
            or not self.selected_record["extension_pending"]
        ):
            return
        self.operation_loading = True
        self.extension_error = ""
        self.success_message = ""
        try:
            result = await asyncio.to_thread(
                _record_extension, self.selected_record.copy(), "", True
            )
            payload = await asyncio.to_thread(_read_live_records)
            self.records = payload["records"]
            self.extension_payments = payload["extension_payments"]
            self.extension_ledger_message = payload["extension_ledger_message"]
            self.months = payload["months"]
            self.last_refresh = _gaborone_now()
            self.success_message = result
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.extension_error = "Reconciliation could not be verified. Keep the saved transaction intact and retry reconciliation; do not collect another payment."
        finally:
            self.operation_loading = False

    @rx.var
    def liquidation_profit(self) -> float:
        return _sum_cents(
            Decimal(str(r["final_revenue"])) - Decimal(str(r["principal"]))
            for r in self.visible_records
            if _is_sold(r["liquidation_status"])
        )

    @rx.var
    def active_capital(self) -> float:
        return _sum_cents(
            record["approved"]
            for record in self.visible_records
            if record["status"] in {"Active", "Extended"}
        )

    @rx.var
    def active_count(self) -> int:
        return sum(
            1 for record in self.visible_records if record["status"] == "Active"
        )

    @rx.var
    def settled_count(self) -> int:
        return sum(
            1
            for record in self.visible_records
            if record["status"] == "Settled"
        )

    @rx.var
    def extended_count(self) -> int:
        return sum(
            1
            for record in self.visible_records
            if record["status"] == "Extended"
        )

    @rx.var
    def defaulted_count(self) -> int:
        return sum(
            1
            for record in self.visible_records
            if record["status"] == "Defaulted"
        )

    @rx.event
    def choose_month(self, value: str):
        self.selected_month = value

    @rx.event
    def choose_tab(self, value: str):
        self.active_tab = value

    @rx.event
    async def refresh_sheets(self):
        if self.operation_loading:
            return
        self.is_loading = True
        self.error_message = ""
        self.success_message = ""
        self.extension_error = ""
        try:
            payload = await asyncio.to_thread(_read_live_records)
            self.records = payload["records"]
            self.extension_payments = payload["extension_payments"]
            self.extension_ledger_message = payload["extension_ledger_message"]
            self.months
            self.worksheet_name = payload["worksheet"]
            self.sheets_health = f"Connected · {len(self.records)} live records"
            self.calendar_health = payload["calendar_health"]
            self.last_refresh = _gaborone_now()
            self.success_message = (
                "Sheets refreshed without changing Calendar reminders."
            )
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error_message = "Live sync failed. Check Google configuration and worksheet access."
            self.sheets_health = "Error"
        self.is_loading = False

    @rx.event
    async def reconcile_calendar(self):
        self.is_reconciling = True
        self.error_message = ""
        self.success_message = ""
        try:
            result = await asyncio.to_thread(_reconcile_reminders, self.records)
            self.reminder_summary = result
            self.calendar_health = "Healthy · reminders reconciled"
            self.success_message = result["message"]
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.calendar_health = "Error"
            self.error_message = "Calendar reconciliation failed. No credentials or customer values were logged."
        self.is_reconciling = False


def _gaborone_now() -> str:
    return datetime.now(ZoneInfo("Africa/Gaborone")).isoformat(
        timespec="seconds"
    )


def _normalize_mobile(value: str) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    compact = re.sub(r"[\s()\-]", "", text)
    for prefix in ("+267", "00267", "267"):
        if compact.startswith(prefix):
            compact = compact[len(prefix) :]
            break
    if compact.startswith("0"):
        compact = compact[1:]
    return compact if re.fullmatch(r"7[0-9]{7}", compact) else ""


def _first_valid_mobile(mobile: str, contact: str) -> str:
    return _normalize_mobile(mobile) or _normalize_mobile(contact)


def _is_sold(value: str) -> bool:
    return value.strip().casefold() in {"sold", "liquidated / sold"}


def _money(value: str) -> float:
    parsed = _money_value(value)
    return parsed if parsed is not None else 0.0


def _sum_cents(values: Iterable[float | Decimal]) -> float:
    total = sum(
        (
            Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
            for value in values
        ),
        Decimal("0"),
    )
    return float(total.quantize(CENT, rounding=ROUND_HALF_UP))


def _sheet_cents(value: str) -> float:
    parsed = _money_value(value)
    return (
        float(_settlement_money(parsed))
        if parsed is not None and math.isfinite(parsed) and parsed >= 0
        else 0.0
    )


def _settlement_accounting(
    raw: dict[str, str], status: str, interest: float
) -> dict[str, float]:
    sold = _is_sold(raw.get("Liquidation Status", ""))
    explicit = raw.get("Payment Type", "").strip().casefold() == "settlement"
    settled_loan = status == "Settled" and not sold
    detail_columns = (
        "Settlement Principal",
        "Settlement Interest",
        "Settlement Late Fees",
        "Retained Overpayment",
        "Settlement Realized Profit",
        "Settlement Required Total",
    )
    has_detail = any(str(raw.get(name, "")).strip() for name in detail_columns)
    principal = (
        _sheet_cents(raw.get("Settlement Principal", ""))
        if settled_loan
        else 0.0
    )
    earned_interest = (
        _sheet_cents(raw.get("Settlement Interest", ""))
        if settled_loan
        else 0.0
    )
    fees = (
        _sheet_cents(raw.get("Settlement Late Fees", ""))
        if settled_loan
        else 0.0
    )
    retained = (
        _sheet_cents(raw.get("Retained Overpayment", ""))
        if settled_loan
        else 0.0
    )
    saved_profit = (
        _sheet_cents(raw.get("Settlement Realized Profit", ""))
        if settled_loan
        else 0.0
    )
    profit = (
        _sum_cents((earned_interest, fees, retained))
        if settled_loan and explicit and has_detail
        else (
            _sheet_cents(interest) if settled_loan and not has_detail else 0.0
        )
    )
    if (
        settled_loan
        and explicit
        and has_detail
        and raw.get("Settlement Realized Profit", "").strip()
        and saved_profit != profit
    ):
        logging.warning(
            "Settlement realized profit differs from persisted components; using component sum"
        )
    return {
        "cash_tendered": _sheet_cents(
            _first(raw, ["Payment Amount", "Final Payout (BWP)"])
        )
        if settled_loan
        else 0.0,
        "settlement_principal": principal,
        "settlement_interest": earned_interest,
        "settlement_late_fees": fees,
        "retained_overpayment": retained,
        "settlement_realized_profit": profit,
        "settlement_required_total": _sheet_cents(
            raw.get("Settlement Required Total", "")
        )
        if settled_loan
        else 0.0,
    }


def _money_value(value: str) -> float | None:
    try:
        cleaned = (
            str(value)
            .replace("BWP", "")
            .replace("P", "")
            .replace(",", "")
            .strip()
        )
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError) as e:
        logging.exception(f"Error: {e}")
        return None


def _parse_business_date(value: str) -> date | None:
    """ISO first; never guess the order of an ambiguous legacy numeric date."""
    text = str(value or "").strip()
    candidate = text.replace("T", " ").split(" ", 1)[0]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            return None
    match = re.fullmatch(r"(\d{2})[/-](\d{2})[/-](\d{4})", candidate)
    if match:
        first, second, year = map(int, match.groups())
        try:
            if first == second:
                return date(year, first, second)
            if first > 12:
                return date(year, second, first)
            if second > 12:
                return date(year, first, second)
        except ValueError:
            return None
        return None
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_jotform_source_date(value: str) -> date | None:
    """Known source uses MM-DD-YYYY / MM/DD/YYYY; ISO is always year-first."""
    candidate = str(value or "").strip().replace("T", " ").split(" ", 1)[0]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return _parse_business_date(candidate)
    match = re.fullmatch(r"(\d{2})[/-](\d{2})[/-](\d{4})", candidate)
    if not match:
        return None
    month, day, year = map(int, match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _date_value(value: str, source: str = "normalized") -> date | None:
    return (
        _parse_jotform_source_date(value)
        if source == "jotform"
        else _parse_business_date(value)
    )


def _iso_or_raw(value: str) -> str:
    """Return ISO text when parseable, otherwise keep the nonempty raw value."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = _parse_business_date(raw)
    return parsed.isoformat() if parsed else raw


def _resolved_due_date(
    explicit: str, issue_date: date | None, source: str = "jotform"
) -> date | None:
    """Source dates are month-first; normalized records never guess legacy order."""
    if str(explicit or "").strip():
        return _date_value(explicit, source)
    return issue_date + timedelta(days=30) if issue_date else None


def _record_due_date(raw: dict[str, str], issue: date | None) -> date | None:
    explicit = raw.get("Maturity / Due Date", "").strip()
    if not explicit:
        return _resolved_due_date("", issue)
    legacy_extension = "extension" in raw.get(
        "Payment Type", ""
    ).casefold() or (
        _first(raw, ["Status", "Loan Status"]).casefold() == "extended"
        and bool(raw.get("Last Updated", "").strip())
    )
    return _date_value(
        explicit, "normalized" if legacy_extension else "jotform"
    )


def _days_to_due(due_date: date | None, today: date) -> int | None:
    if due_date is None:
        return None
    return (due_date - today).days


def _gaborone_date() -> date:
    return datetime.now(ZoneInfo("Africa/Gaborone")).date()


def _first(raw: dict[str, str], names: list[str]) -> str:
    for name in names:
        value = str(raw.get(name, "") or "").strip()
        if value:
            return value
    return ""


def _authoritative_date(
    raw: dict[str, str], source: str, aliases: list[str]
) -> date | None:
    primary = str(raw.get(source, "") or "").strip()
    parsed = (
        _parse_jotform_source_date(primary)
        if source == "Date"
        else _date_value(primary)
    )
    if parsed:
        return parsed
    return _date_value(_first(raw, aliases))


def _display_text(value: str) -> str:
    return str(value or "").strip() or "—"


def _interest_rate(value: str) -> tuple[float, str]:
    text = str(value or "").replace(",", ".").strip()
    has_percent = "%" in text
    cleaned = "".join(
        ch for ch in text.replace("%", "") if ch.isdigit() or ch in ".-"
    )
    try:
        number = float(cleaned)
    except (ValueError, TypeError):
        return 0.0, ""
    if number < 0:
        return 0.0, ""
    rate = number / 100 if has_percent or number > 1 else number
    return rate, f"{rate * 100:.4g}%"


def _milestone_status(
    raw_status: str, milestone: date | None, today: date, settled: bool
) -> str:
    if raw_status:
        return raw_status
    if settled:
        return "Completed"
    if milestone is None:
        return ""
    if milestone < today:
        return "Sent"
    if milestone == today:
        return "Due"
    return "Scheduled"


def _unique_headers(headers: list[str]) -> list[str]:
    """Assign collision-free lookup keys without changing physical worksheet headers."""
    reserved = {header.strip() for header in headers if header.strip()}
    used: set[str] = set()
    result: list[str] = []
    for header in headers:
        source = header.strip()
        base = source or "Unnamed"
        if base not in used and (source or base not in reserved):
            key = base
        else:
            suffix = 2
            key = f"{base}_{suffix}"
            while key in used or key in reserved:
                suffix += 1
                key = f"{base}_{suffix}"
        used.add(key)
        result.append(key)
    return result


def _read_live_records() -> dict[str, object]:
    try:
        import gspread
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/calendar",
        ]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=scopes
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(
            os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"]
        )
        sheet = spreadsheet.worksheet(os.environ["GOOGLE_SHEETS_WORKSHEET"])
        extension_payments, ledger_message = _load_extension_payments(
            spreadsheet
        )
        verified_ids = {p["extension_id"] for p in extension_payments}
        values = sheet.get_all_values()
        headers = _unique_headers(values[0])
        rows = values[1:]
        records: list[LoanRecord] = []
        for row in rows:
            if not any(str(cell).strip() for cell in row):
                continue
            raw = {
                headers[index]: row[index] if index < len(row) else ""
                for index in range(len(headers))
            }
            issue_date = _authoritative_date(
                raw,
                "Date",
                [
                    "Submission Date",
                    "Created At",
                    "Created at",
                    "Date Created",
                    "Timestamp",
                    "Issue Date",
                    "Loan Date",
                ],
            )
            loan_date = issue_date
            due_date = _record_due_date(raw, issue_date)
            explicit = _first(raw, ["Status", "Loan Status"]).title()
            status = (
                explicit
                if explicit in {"Active", "Settled", "Extended", "Defaulted"}
                else "Active"
            )
            if not explicit and due_date and due_date < _gaborone_date():
                status = "Active"
            category = raw.get("Category", raw.get("Category_2", ""))
            category_other = raw.get("Category - Other", "")
            item = " ".join(
                filter(
                    None,
                    [
                        category,
                        category_other,
                        raw.get("Brand", ""),
                        raw.get("Model", ""),
                        raw.get("Colour", ""),
                    ],
                )
            )
            estimated = _money(raw.get("Estimated Market Value", ""))
            approved_value = _money_value(raw.get("Approved Loan Amount", ""))
            principal = (
                approved_value
                if approved_value is not None
                else _money(
                    _first(
                        raw,
                        [
                            "Principal Loan Amount",
                            "Principal",
                            "Principal (BWP)",
                            "Loan Amount",
                        ],
                    )
                )
            )
            interest_value = _money_value(raw.get("Interest Amount", ""))
            interest_amount = (
                interest_value
                if interest_value is not None
                and interest_value >= 0
                and interest_value <= principal
                else round(principal * 0.30, 2)
            )
            total_value = _money_value(raw.get("Total Amount Due", ""))
            resolved_total = round(principal + interest_amount, 2)
            total_due = (
                total_value
                if total_value is not None
                and abs(total_value - resolved_total) <= 0.01
                else resolved_total
            )
            rate = interest_amount / principal if principal > 0 else 0.0
            rate_display = f"{rate * 100:.4g}%" if principal > 0 else "0%"
            penalty = _money(
                _first(
                    raw,
                    [
                        "Daily Penalty",
                        "Daily Penalty (BWP)",
                        "Penalty Per Day",
                        "Daily Late Fee",
                        "Late Fee Per Day",
                    ],
                )
            )
            penalty = penalty if penalty > 0 else 0.0
            today = _gaborone_date()
            settled = status == "Settled"
            date_settled = _iso_or_raw(
                _first(raw, ["Date Settled", "Settlement Date", "Payment Date"])
            )
            settled_on = _date_value(date_settled) if settled else None
            days_overdue = (
                max(0, ((settled_on or due_date) - due_date).days)
                if settled and due_date and settled_on
                else max(0, (today - due_date).days)
                if due_date and not settled
                else 0
            )
            accounting = _settlement_accounting(raw, status, interest_amount)
            late_fees = (
                accounting["settlement_late_fees"]
                if settled
                else _sum_cents((Decimal(days_overdue) * Decimal(penalty),))
            )
            recorded_payout = next(
                (
                    amount
                    for name in ("Final Payout (BWP)", "Payment Amount")
                    if (amount := _money_value(raw.get(name, ""))) is not None
                    and math.isfinite(amount)
                    and amount >= 0
                ),
                None,
            )
            remaining_value = _money_value(raw.get("Remaining Principal", ""))
            remaining_principal = (
                remaining_value
                if remaining_value is not None
                and math.isfinite(remaining_value)
                and remaining_value >= 0
                else principal
            )
            final_payout = (
                float(_settlement_money(recorded_payout))
                if settled
                and recorded_payout is not None
                and math.isfinite(recorded_payout)
                and recorded_payout >= 0
                else 0.0
                if settled
                else _sum_cents(
                    (remaining_principal, interest_amount, late_fees)
                )
            )
            day_23 = due_date - timedelta(days=7) if due_date else None
            day_35 = due_date + timedelta(days=5) if due_date else None
            description = " · ".join(
                filter(
                    None,
                    [
                        raw.get("Brand", "").strip(),
                        raw.get("Model", "").strip(),
                        raw.get("Colour", "").strip(),
                        _first(raw, ["Item Description", "Description"]),
                        _first(raw, ["IMEI", "IMEI No.", "IMEI Number"]),
                        _first(
                            raw,
                            [
                                "Serial",
                                "Serial No.",
                                "Serial Number",
                                "VIN",
                            ],
                        ),
                    ],
                )
            )
            recommended = round(estimated * 0.8, 2) if estimated else principal
            records.append(
                {
                    "ticket": _first(
                        raw,
                        ["Pawn / Loan No.", "Submission ID"],
                    )
                    or "Unnumbered",
                    "issue_date": issue_date.isoformat() if issue_date else "",
                    "contact": raw.get("Mobile No.", ""),
                    "item_category": _display_text(category or category_other),
                    "description": _display_text(description or item),
                    "interest_rate": rate,
                    "interest_rate_display": rate_display or "—",
                    "day_23": day_23.isoformat() if day_23 else "",
                    "day_23_status": _milestone_status(
                        _first(raw, ["Day 23 Status"]), day_23, today, settled
                    ),
                    "day_30_action": due_date.isoformat() if due_date else "",
                    "day_30_status": _milestone_status(
                        _first(raw, ["Day 30 Status"]),
                        due_date,
                        today,
                        settled,
                    ),
                    "day_35": day_35.isoformat() if day_35 else "",
                    "day_35_status": _milestone_status(
                        _first(raw, ["Day 35 Status"]), day_35, today, settled
                    ),
                    "daily_penalty": penalty,
                    "days_overdue": days_overdue,
                    "late_fees": late_fees,
                    "final_payout": final_payout,
                    "cash_tendered": accounting["cash_tendered"],
                    "settlement_principal": accounting["settlement_principal"],
                    "settlement_interest": accounting["settlement_interest"],
                    "settlement_late_fees": accounting["settlement_late_fees"],
                    "retained_overpayment": accounting["retained_overpayment"],
                    "settlement_realized_profit": accounting[
                        "settlement_realized_profit"
                    ],
                    "settlement_required_total": accounting[
                        "settlement_required_total"
                    ],
                    "date_settled": _display_text(date_settled),
                    "remarks": _display_text(
                        _first(
                            raw,
                            [
                                "Remarks / Notes",
                                "Remarks",
                                "Notes",
                                "Comments",
                            ],
                        )
                    ),
                    "loan_date": loan_date.isoformat() if loan_date else "",
                    "due_date": due_date.isoformat()
                    if due_date
                    else raw.get("Maturity / Due Date", "").strip(),
                    "customer": _display_text(
                        " ".join(
                            filter(
                                None,
                                [
                                    raw.get("Full Name - First Name", ""),
                                    raw.get("Full Name - Middle Name", ""),
                                    raw.get("Full Name - Last Name", ""),
                                ],
                            )
                        )
                    ),
                    "omang": _display_text(raw.get("Omang / Passport No.", "")),
                    "mobile": _display_text(raw.get("Mobile No.", "")),
                    "category": _display_text(category),
                    "item": _display_text(item),
                    "payment_date": _iso_or_raw(raw.get("Payment Date", "")),
                    "liquidation_status": raw.get("Liquidation Status", ""),
                    "sale_date": _iso_or_raw(raw.get("Sale Date", "")),
                    "final_revenue": _money(raw.get("Final Cash Revenue", "")),
                    "realized_profit": _money(raw.get("Realized Profit", "")),
                    "recommended_price": recommended,
                    "month": issue_date.strftime("%Y-%m")
                    if issue_date
                    else "Unknown",
                    "estimated_value": estimated,
                    "principal": principal,
                    "approved": principal,
                    "interest": interest_amount,
                    "total_due": total_due,
                    "remaining_principal": remaining_principal,
                    "status": status,
                    "submission_id": _display_text(
                        raw.get("Submission ID", "")
                    ),
                    "extension_pending": bool(raw.get("Extension ID", ""))
                    and raw.get("Extension ID", "") not in verified_ids,
                }
            )
        calendar = build(
            "calendar", "v3", credentials=creds, cache_discovery=False
        )
        calendar.calendars().get(
            calendarId=os.environ["GOOGLE_CALENDAR_ID"]
        ).execute()
        return {
            "records": records,
            "extension_payments": extension_payments,
            "extension_ledger_message": ledger_message,
            "months": sorted(
                {
                    record["month"]
                    for record in records
                    if record["month"] != "Unknown"
                }
                | {p["payment_date"][:7] for p in extension_payments}
                | {
                    r["date_settled"][:7]
                    for r in records
                    if r["status"] == "Settled"
                    and _date_value(r["date_settled"])
                },
                reverse=True,
            ),
            "worksheet": sheet.title,
            "calendar_health": "Connected · read access verified",
        }
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise


def _validated_payment_date(value: str) -> str:
    if not value.strip():
        return _gaborone_date().isoformat()
    parsed = _date_value(value)
    if parsed is None or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        raise ValueError("Enter the payment date as YYYY-MM-DD.")
    return parsed.isoformat()


def _extension_cash(cash: str, interest: float | Decimal) -> Decimal:
    if not cash.strip():
        raise ValueError(
            "Enter cash received for the extension (up to two decimal places)."
        )
    tender = _settlement_cash(cash)
    if tender <= 0:
        raise ValueError("Extension cash must be finite and positive.")
    required = _settlement_money(interest)
    if tender < required:
        raise ValueError(
            f"Extension must cover current interest: P{required:,.2f}; short by P{required - tender:,.2f}."
        )
    return tender


def _extension_fingerprint(record: LoanRecord) -> str:
    return _extension_id(
        record["ticket"], record["submission_id"], record["due_date"]
    )


def _extension_updates(
    raw: dict[str, str], expected: LoanRecord, cash: str, today: date
) -> dict[str, str]:
    status = _first(raw, ["Status", "Loan Status"]).title() or "Active"
    if status not in {"Active", "Extended"} or _is_sold(
        raw.get("Liquidation Status", "")
    ):
        raise ValueError(
            "Only an unsold Active or Extended ticket can be extended."
        )
    if (
        raw.get("Date Settled", "").strip()
        or raw.get("Payment Type", "").casefold() == "settlement"
    ):
        raise ValueError(
            "This ticket already has settlement details; refresh and resolve its status first."
        )
    ticket = _first(raw, ["Pawn / Loan No.", "Submission ID"])
    if (
        ticket != expected["ticket"]
        or _display_text(raw.get("Submission ID", ""))
        != expected["submission_id"]
    ):
        raise ValueError(
            "Live ticket identity changed. Refresh Sheets before extending."
        )
    issue = _authoritative_date(
        raw,
        "Date",
        [
            "Issue Date",
            "Loan Date",
            "Submission Date",
            "Created At",
            "Created at",
            "Date Created",
            "Timestamp",
        ],
    )
    due = _record_due_date(raw, issue)
    if due is None:
        raise ValueError(
            "Live due date is invalid or ambiguous. Correct it to ISO and refresh before extending."
        )
    principal_text = _first(
        raw,
        [
            "Approved Loan Amount",
            "Principal Loan Amount",
            "Principal",
            "Principal (BWP)",
            "Loan Amount",
        ],
    )
    principal = _extension_sheet_money(principal_text)
    remaining = _extension_sheet_money(
        raw.get("Remaining Principal", "").strip() or principal_text
    )
    interest = _extension_sheet_money(raw.get("Interest Amount", ""))
    if (
        principal <= 0
        or remaining <= 0
        or remaining > principal
        or interest > principal
    ):
        raise ValueError(
            "Live principal or interest is inconsistent. Correct Sheets before extending."
        )
    if (
        status != expected["status"]
        or due != _date_value(expected["due_date"])
        or principal != _settlement_money(expected["principal"])
        or remaining != _settlement_money(expected["remaining_principal"])
        or interest != _settlement_money(expected["interest"])
        or _iso_or_raw(raw.get("Payment Date", "")) != expected["payment_date"]
    ):
        raise ValueError(
            "The live status, due date or amounts changed. Refresh and review before extending."
        )
    tender = _extension_cash(cash, interest)
    new_due = max(today, due) + timedelta(days=30)
    next_interest = _settlement_money(remaining * interest / principal)
    return {
        "Status": "Extended",
        "Maturity / Due Date": new_due.isoformat(),
        "Day 23 Courtesy": (new_due - timedelta(days=7)).isoformat(),
        "Day 30 Due Action": new_due.isoformat(),
        "Day 35 Final Warning": (new_due + timedelta(days=5)).isoformat(),
        "Payment Amount": f"{tender:.2f}",
        "Payment Date": today.isoformat(),
        "Payment Type": "Interest Extension",
        "Remaining Principal": f"{remaining:.2f}",
        "Interest Amount": f"{next_interest:.2f}",
        "Total Amount Due": f"{remaining + next_interest:.2f}",
        "Last Updated": _gaborone_now(),
    }


def _write_ticket_extension(
    sheet,
    expected: LoanRecord,
    cash: str,
    today: date,
    spreadsheet=None,
    repair: bool = False,
) -> str:
    """Optimistic live check, append-only headers, one RAW batch, then read-back."""
    import gspread

    if not expected["ticket"].strip() or expected["ticket"] == "Unnumbered":
        raise ValueError("Select a numbered ticket before extending.")
    values = sheet.get_all_values()
    if not values:
        raise ValueError("Worksheet has no headers.")
    physical = values[0].copy()
    headers = _unique_headers(physical)
    matches: list[tuple[int, dict[str, str], list[str]]] = []
    for index, row in enumerate(values[1:], 2):
        raw = {
            name: row[i].strip() if i < len(row) else ""
            for i, name in enumerate(headers)
        }
        if (
            _first(raw, ["Pawn / Loan No.", "Submission ID"])
            == expected["ticket"]
        ):
            matches.append((index, raw, row))
    if len(matches) != 1:
        raise ValueError(
            "Ticket must match exactly one live row. Resolve duplicate or missing identifiers and refresh."
        )
    index, raw, original = matches[0]
    if spreadsheet is None:
        spreadsheet = sheet.spreadsheet
    saved_id = raw.get("Extension ID", "")
    requested_id = _extension_fingerprint(expected)
    if saved_id:
        journal = _extension_journal(raw)
        if saved_id == requested_id or repair:
            if not repair and _settlement_cash(cash) != Decimal(
                journal["Cash Received"]
            ):
                raise ValueError(
                    "Retry cash differs from the saved transaction. Reconcile the saved extension without collecting cash again."
                )
            _verify_extension_primary(raw, journal)
            _append_extension_payment(spreadsheet, journal)
            final_row = sheet.row_values(index)
            final_raw = {
                name: final_row[i].strip() if i < len(final_row) else ""
                for i, name in enumerate(headers)
            }
            _verify_extension_primary(final_raw, journal)
            if final_raw.get("Extension ID") != saved_id:
                raise RuntimeError(
                    "Primary extension changed during reconciliation. Refresh and inspect the saved transaction."
                )
            return _extension_result(journal)
        existing, _ = _load_extension_payments(spreadsheet)
        if not any(p["extension_id"] == saved_id for p in existing):
            raise ValueError(
                "Previous extension payment needs reconciliation. Select Reconcile saved extension before another payment."
            )
    if repair:
        raise ValueError(
            "No durable extension transaction is available to reconcile."
        )
    updates = _extension_updates(raw, expected, cash, today)
    journal = {
        "Extension ID": requested_id,
        "Ticket": expected["ticket"],
        "Submission ID": expected["submission_id"],
        "Payment Date": updates["Payment Date"],
        "Old Due": expected["due_date"],
        "New Due": updates["Maturity / Due Date"],
        "Cash Received": updates["Payment Amount"],
        "Interest Realized": f"{_extension_sheet_money(raw['Interest Amount']):.2f}",
        "Unapplied Excess": f"{Decimal(updates['Payment Amount']) - _extension_sheet_money(raw['Interest Amount']):.2f}",
        "Remaining Principal": updates["Remaining Principal"],
        "Status": "Verified",
        "Verification": "Primary read-back verified",
        "Primary Updates": json.dumps(updates, sort_keys=True),
    }
    updates = {
        **updates,
        "Extension ID": requested_id,
        "Extension Transaction": json.dumps(journal, sort_keys=True),
    }
    missing = [name for name in updates if name not in headers]
    if sheet.row_values(1) != physical:
        raise ValueError("Headers changed; refresh before extending.")
    if missing:
        needed = len(physical) + len(missing)
        if sheet.col_count < needed:
            sheet.add_cols(needed - sheet.col_count)
        first = gspread.utils.rowcol_to_a1(1, len(physical) + 1)
        last = gspread.utils.rowcol_to_a1(1, needed)
        sheet.update(
            range_name=f"{first}:{last}",
            values=[missing],
            value_input_option="RAW",
        )
        headers.extend(missing)
    if sheet.row_values(1) != physical + missing:
        raise RuntimeError(
            "Extension headers could not be verified. Inspect Sheets before retrying."
        )
    current = sheet.row_values(index)
    if any(
        (current[i] if i < len(current) else "")
        != (original[i] if i < len(original) else "")
        for i in range(len(physical))
    ):
        raise ValueError(
            "Live row changed during preparation; refresh and inspect before retrying."
        )
    columns = {name: headers.index(name) for name in updates}
    sheet.batch_update(
        [
            {
                "range": gspread.utils.rowcol_to_a1(index, columns[name] + 1),
                "values": [[value]],
            }
            for name, value in updates.items()
        ],
        value_input_option="RAW",
    )
    saved = sheet.row_values(index)
    if any(
        columns[name] >= len(saved) or saved[columns[name]] != value
        for name, value in updates.items()
    ):
        raise RuntimeError(
            "Extension write was not verified. Inspect live payment and due date; do not replay this attempt."
        )
    _append_extension_payment(spreadsheet, journal)
    final_row = sheet.row_values(index)
    final_raw = {
        name: final_row[i].strip() if i < len(final_row) else ""
        for i, name in enumerate(headers)
    }
    _verify_extension_primary(final_raw, journal)
    if final_raw.get("Extension ID") != requested_id:
        raise RuntimeError(
            "Payment persisted but primary transaction changed. Refresh and reconcile before proceeding."
        )
    return _extension_result(journal)


def _record_extension(
    expected: LoanRecord, cash: str, repair: bool = False
) -> str:
    try:
        import gspread
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_info(
            json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        spreadsheet = gspread.authorize(creds).open_by_key(
            os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"]
        )
        sheet = spreadsheet.worksheet(os.environ["GOOGLE_SHEETS_WORKSHEET"])
        return _write_ticket_extension(
            sheet, expected, cash, _gaborone_date(), spreadsheet, repair
        )
    except ValueError:
        raise
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise RuntimeError(
            "Extension outcome is uncertain. Inspect Sheets before retrying."
        ) from None


EXTENSION_COLUMNS: tuple[str, ...] = (
    "Extension ID",
    "Ticket",
    "Submission ID",
    "Payment Date",
    "Old Due",
    "New Due",
    "Cash Received",
    "Interest Realized",
    "Unapplied Excess",
    "Remaining Principal",
    "Status",
    "Verification",
    "Primary Updates",
)


def _extension_id(ticket: str, submission: str, old_due: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", old_due) or not _date_value(
        old_due
    ):
        raise ValueError("Extension requires a strict ISO previous due date.")
    identity = json.dumps([ticket, submission, old_due], separators=(",", ":"))
    return f"EXT-{hashlib.sha256(identity.encode()).hexdigest()}"


def _extension_sheet_money(value: str) -> Decimal:
    text = str(value).strip().replace("BWP", "").removeprefix("P").strip()
    if not text:
        raise ValueError(
            "A required extension amount is missing. Correct Sheets and refresh."
        )
    return _settlement_cash(text)


def _extension_result(journal: dict[str, str]) -> str:
    return f"Extension saved and verified in ticket and payment ledger · cash P{Decimal(journal['Cash Received']):,.2f} · interest P{Decimal(journal['Interest Realized']):,.2f} · due {journal['New Due']}."


def _validated_extension_entry(raw: dict[str, str]) -> ExtensionPayment:
    for key in ("Payment Date", "Old Due", "New Due"):
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", raw.get(key, "")
        ) or not _date_value(raw[key]):
            raise ValueError("Extension ledger has an invalid ISO date.")
    if raw.get("Extension ID") != _extension_id(
        raw["Ticket"], raw["Submission ID"], raw["Old Due"]
    ):
        raise ValueError(
            "Extension ledger identity does not match its due transition."
        )
    amounts = {
        key: _extension_sheet_money(raw.get(key, ""))
        for key in (
            "Cash Received",
            "Interest Realized",
            "Unapplied Excess",
            "Remaining Principal",
        )
    }
    if (
        amounts["Cash Received"] <= 0
        or amounts["Cash Received"]
        != amounts["Interest Realized"] + amounts["Unapplied Excess"]
    ):
        raise ValueError("Extension ledger cash allocation is inconsistent.")
    if date.fromisoformat(raw["New Due"]) != max(
        date.fromisoformat(raw["Old Due"]),
        date.fromisoformat(raw["Payment Date"]),
    ) + timedelta(days=30):
        raise ValueError("Extension ledger due transition is inconsistent.")
    return ExtensionPayment(
        extension_id=raw["Extension ID"],
        ticket=raw["Ticket"],
        submission_id=raw["Submission ID"],
        payment_date=raw["Payment Date"],
        old_due=raw["Old Due"],
        new_due=raw["New Due"],
        cash=float(amounts["Cash Received"]),
        interest=float(amounts["Interest Realized"]),
        excess=float(amounts["Unapplied Excess"]),
        principal=float(amounts["Remaining Principal"]),
        status=raw["Status"],
    )


def _extension_journal(raw: dict[str, str]) -> dict[str, str]:
    try:
        journal = json.loads(raw.get("Extension Transaction", ""))
        if not isinstance(journal, dict) or not all(
            isinstance(v, str) for v in journal.values()
        ):
            raise ValueError("Invalid saved extension transaction.")
        _validated_extension_entry(journal)
        if (
            journal["Extension ID"] != raw.get("Extension ID")
            or journal["Ticket"]
            != _first(raw, ["Pawn / Loan No.", "Submission ID"])
            or journal["Submission ID"]
            != _display_text(raw.get("Submission ID", ""))
        ):
            raise ValueError(
                "Saved extension identity differs from the ticket."
            )
        return journal
    except (ValueError, KeyError, TypeError) as e:
        logging.exception(f"Error: {e}")
        raise ValueError(
            "Saved extension details are invalid. Preserve them and reconcile the worksheet manually; do not repeat the payment."
        ) from None


def _verify_extension_primary(
    raw: dict[str, str], journal: dict[str, str]
) -> None:
    updates = json.loads(journal["Primary Updates"])
    if (
        not isinstance(updates, dict)
        or not updates
        or any(raw.get(k, "") != v for k, v in updates.items())
    ):
        raise ValueError(
            "Saved extension primary values cannot be verified. Preserve the transaction and inspect the ticket; no payment has been appended."
        )


def _extension_ledger_rows(spreadsheet) -> tuple[object, list[dict[str, str]]]:
    import gspread

    try:
        ledger = spreadsheet.worksheet("Extension Payments")
    except gspread.WorksheetNotFound:
        logging.exception("Unexpected error")
        return None, []
    values = ledger.get_all_values()
    if not values:
        return ledger, []
    if len(set(values[0])) != len(values[0]) or not set(
        EXTENSION_COLUMNS
    ).issubset(values[0]):
        raise ValueError(
            "Extension Payments headers are incomplete or duplicated. Preserve historical rows and repair the headers."
        )
    return ledger, [
        {
            name: row[i].strip() if i < len(row) else ""
            for i, name in enumerate(values[0])
        }
        for row in values[1:]
        if any(row)
    ]


def _load_extension_payments(spreadsheet) -> tuple[list[ExtensionPayment], str]:
    ledger, rows = _extension_ledger_rows(spreadsheet)
    if ledger is None:
        return (
            [],
            "No extension payments worksheet yet. It is created only when an operator extends a ticket.",
        )
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row.get("Extension ID", ""), []).append(row)
    payments: list[ExtensionPayment] = []
    rejected = 0
    for group in grouped.values():
        if any(row != group[0] for row in group[1:]):
            rejected += len(group)
            continue
        raw = group[0]
        if (
            raw.get("Status") != "Verified"
            or raw.get("Verification") != "Primary read-back verified"
        ):
            rejected += len(group)
            continue
        try:
            payments.append(_validated_extension_entry(raw))
        except (ValueError, KeyError) as e:
            logging.exception(f"Error: {e}")
            rejected += len(group)
    duplicates = len(rows) - len(grouped)
    message = f"{len(payments)} verified extension payments loaded."
    if rejected or duplicates:
        message = f"{message} Review ledger: {rejected} invalid/unverified/conflicting rows excluded; {duplicates} duplicate IDs counted at most once. Historical rows were not changed."
    return sorted(
        payments,
        key=lambda p: (p["payment_date"], p["extension_id"]),
        reverse=True,
    ), message


def _append_extension_payment(spreadsheet, journal: dict[str, str]) -> None:
    _validated_extension_entry(journal)
    ledger, rows = _extension_ledger_rows(spreadsheet)
    matches = [
        row
        for row in rows
        if row.get("Extension ID") == journal["Extension ID"]
    ]
    if matches:
        if len(matches) != 1 or any(
            matches[0].get(k) != journal[k] for k in EXTENSION_COLUMNS
        ):
            raise ValueError(
                "Existing extension ledger ID has conflicting or duplicate entries. Preserve history and reconcile; no row was overwritten."
            )
        return
    if ledger is None:
        try:
            ledger = spreadsheet.add_worksheet(
                title="Extension Payments",
                rows=1000,
                cols=len(EXTENSION_COLUMNS),
            )
        except Exception as e:
            logging.exception(f"Error: {e}")
            ledger, rows = _extension_ledger_rows(spreadsheet)
            if ledger is None:
                raise
    if not ledger.get_all_values():
        ledger.update(
            range_name="A1",
            values=[list(EXTENSION_COLUMNS)],
            value_input_option="RAW",
        )
    ledger, rows = _extension_ledger_rows(spreadsheet)
    matches = [
        r for r in rows if r.get("Extension ID") == journal["Extension ID"]
    ]
    if matches:
        if len(matches) != 1 or any(
            matches[0].get(k) != journal[k] for k in EXTENSION_COLUMNS
        ):
            raise ValueError(
                "Extension ledger conflict; reconcile existing entries without overwriting history."
            )
        return
    headers = ledger.row_values(1)
    ledger.append_row(
        [journal.get(k, "") for k in headers], value_input_option="RAW"
    )
    _, saved = _extension_ledger_rows(spreadsheet)
    matches = [
        r for r in saved if r.get("Extension ID") == journal["Extension ID"]
    ]
    if len(matches) != 1 or any(
        matches[0].get(k) != journal[k] for k in EXTENSION_COLUMNS
    ):
        raise RuntimeError(
            "Primary extension saved, but payment ledger is not verified. Refresh and reconcile the saved extension; do not collect cash again."
        )


def _monthly_realized_interest(
    records: list[LoanRecord], payments: list[ExtensionPayment], month: str
) -> float:
    settlement = [
        Decimal(r["settlement_realized_profit"])
        for r in records
        if r["status"] == "Settled"
        and not _is_sold(r["liquidation_status"])
        and _date_value(r["date_settled"])
        and r["date_settled"][:7] == month
    ]
    unique = {
        p["extension_id"]: p for p in payments if p["status"] == "Verified"
    }
    return _sum_cents(
        settlement
        + [
            Decimal(p["interest"])
            for p in unique.values()
            if p["payment_date"][:7] == month
        ]
    )


SETTLEMENT_COLUMNS: tuple[str, ...] = (
    "Status",
    "Date Settled",
    "Payment Amount",
    "Payment Date",
    "Payment Type",
    "Remaining Principal",
    "Final Payout (BWP)",
    "Settlement Principal",
    "Settlement Interest",
    "Settlement Late Fees",
    "Retained Overpayment",
    "Settlement Realized Profit",
    "Settlement Required Total",
    "Last Updated",
)


def _live_settlement_amounts(
    raw: dict[str, str], tender: Decimal, today: date
) -> SettlementAmounts:
    approved_text = raw.get("Approved Loan Amount", "").strip()
    principal_text = approved_text or _first(
        raw,
        [
            "Principal Loan Amount",
            "Principal",
            "Principal (BWP)",
            "Loan Amount",
        ],
    )
    principal_value = _money_value(principal_text) if principal_text else None
    if (
        principal_value is None
        or not math.isfinite(principal_value)
        or principal_value < 0
    ):
        raise ValueError(
            "The live principal is missing or invalid. Correct the worksheet and refresh before settling."
        )
    principal = _settlement_money(principal_value)
    remaining_text = raw.get("Remaining Principal", "").strip()
    remaining_value = (
        _money_value(remaining_text) if remaining_text else principal_value
    )
    if (
        remaining_value is None
        or not math.isfinite(remaining_value)
        or remaining_value < 0
    ):
        raise ValueError(
            "The live remaining principal is invalid. Correct the worksheet before settling."
        )
    interest_text = raw.get("Interest Amount", "").strip()
    interest_value = _money_value(interest_text) if interest_text else None
    interest = _settlement_money(
        interest_value
        if interest_value is not None
        and math.isfinite(interest_value)
        and 0 <= interest_value <= principal_value
        else principal * Decimal("0.30")
    )
    issue = _authoritative_date(
        raw,
        "Date",
        [
            "Submission Date",
            "Created At",
            "Created at",
            "Date Created",
            "Timestamp",
            "Issue Date",
            "Loan Date",
        ],
    )
    due = _record_due_date(raw, issue)
    if due is None:
        raise ValueError(
            "The live due date and issue date are missing or invalid. Correct the worksheet before settling."
        )
    penalty_text = _first(
        raw,
        [
            "Daily Penalty",
            "Daily Penalty (BWP)",
            "Penalty Per Day",
            "Daily Late Fee",
            "Late Fee Per Day",
        ],
    )
    penalty_value = _money_value(penalty_text) if penalty_text else 0.0
    if (
        penalty_value is None
        or not math.isfinite(penalty_value)
        or penalty_value < 0
    ):
        raise ValueError(
            "The live daily penalty is invalid. Correct the worksheet before settling."
        )
    late_fees = _settlement_money(
        Decimal(penalty_value) * max(0, (today - due).days)
    )
    return _calculate_settlement(
        _settlement_money(remaining_value), interest, late_fees, tender
    )


def _record_settlement(
    ticket: str, submission_id: str, cash: str, expected: LoanRecord
) -> str:
    if not cash.strip():
        raise ValueError("Enter a cash amount before settling.")
    tender = _settlement_cash(cash)
    if not ticket.strip() or ticket == "Unnumbered":
        raise ValueError("Select a numbered ticket before settling.")
    try:
        import gspread
        from google.oauth2 import service_account

        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        sheet = (
            gspread.authorize(creds)
            .open_by_key(os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"])
            .worksheet(os.environ["GOOGLE_SHEETS_WORKSHEET"])
        )
        values = sheet.get_all_values()
        if not values:
            raise ValueError(
                "The worksheet has no header row. Refresh Sheets and check the worksheet."
            )
        physical_headers = values[0].copy()
        headers = _unique_headers(physical_headers)
        if "Pawn / Loan No." not in headers and "Submission ID" not in headers:
            raise ValueError("The worksheet has no ticket identifier column.")
        matches: list[tuple[int, dict[str, str], list[str]]] = []
        for row_index, row in enumerate(values[1:], 2):
            raw = {
                name: row[i].strip() if i < len(row) else ""
                for i, name in enumerate(headers)
            }
            if (
                _first(raw, ["Pawn / Loan No.", "Submission ID"])
                == ticket.strip()
            ):
                matches.append((row_index, raw, row))
        if len(matches) != 1:
            raise ValueError(
                "Ticket must match exactly one live worksheet row. Refresh Sheets and resolve missing or duplicate ticket numbers."
            )
        row_index, raw, original_row = matches[0]
        if raw.get("Extension ID", ""):
            journal = _extension_journal(raw)
            spreadsheet = sheet.spreadsheet
            existing, _ = _load_extension_payments(spreadsheet)
            if not any(
                p["extension_id"] == journal["Extension ID"] for p in existing
            ):
                _verify_extension_primary(raw, journal)
                _append_extension_payment(spreadsheet, journal)
        if (
            submission_id not in {"", "—"}
            and raw.get("Submission ID", "") != submission_id
        ):
            raise ValueError(
                "The live ticket identity changed. Refresh Sheets before settling."
            )
        status = _first(raw, ["Status", "Loan Status"]).title() or "Active"
        if (
            status not in {"Active", "Extended"}
            or _is_sold(raw.get("Liquidation Status", ""))
            or raw.get("Date Settled", "").strip()
            or raw.get("Payment Type", "").strip().casefold() == "settlement"
        ):
            raise ValueError(
                "This ticket is no longer an unsold Active or Extended loan. Refresh Sheets before retrying."
            )
        today = _gaborone_date()
        amounts = _live_settlement_amounts(raw, tender, today)
        preview = _settlement_display(expected, cash, today)
        if any(
            preview[key] != f"P{amounts[key]:,.2f}"
            for key in ("principal", "interest", "late_fees", "required")
        ):
            raise ValueError(
                "The live settlement amounts changed since the preview. Refresh Sheets, review the new totals and settle again."
            )
        money = lambda key: f"{amounts[key]:.2f}"
        updates: dict[str, str] = {
            "Status": "Settled",
            "Date Settled": today.isoformat(),
            "Payment Amount": money("tender"),
            "Payment Date": today.isoformat(),
            "Payment Type": "Settlement",
            "Remaining Principal": "0.00",
            "Final Payout (BWP)": money("tender"),
            "Settlement Principal": money("principal"),
            "Settlement Interest": money("interest"),
            "Settlement Late Fees": money("late_fees"),
            "Retained Overpayment": money("retained"),
            "Settlement Realized Profit": money("profit"),
            "Settlement Required Total": money("required"),
            "Last Updated": _gaborone_now(),
        }
        if "Remarks / Notes" in headers:
            existing = raw.get("Remarks / Notes", "")
            note = f"Settlement {today.isoformat()}: cash P{amounts['tender']:,.2f}; required P{amounts['required']:,.2f}; retained P{amounts['retained']:,.2f}."
            updates["Remarks / Notes"] = (
                f"{existing}\n{note}" if existing else note
            )
        missing = [name for name in SETTLEMENT_COLUMNS if name not in headers]
        before_headers = sheet.row_values(1)
        if (
            before_headers
            + [""] * max(0, len(physical_headers) - len(before_headers))
            != physical_headers
        ):
            raise ValueError(
                "The worksheet headers changed while preparing settlement. Refresh Sheets before retrying."
            )
        if missing:
            needed = len(physical_headers) + len(missing)
            if sheet.col_count < needed:
                sheet.add_cols(needed - sheet.col_count)
            first = gspread.utils.rowcol_to_a1(1, len(physical_headers) + 1)
            last = gspread.utils.rowcol_to_a1(1, needed)
            sheet.update(
                range_name=f"{first}:{last}",
                values=[missing],
                value_input_option="RAW",
            )
            headers.extend(missing)
        verified_headers = sheet.row_values(1)
        expected_headers = physical_headers + missing
        if (
            verified_headers
            + [""] * max(0, len(expected_headers) - len(verified_headers))
            != expected_headers
        ):
            raise RuntimeError(
                "Worksheet headers could not be verified; refresh Sheets before retrying."
            )
        current_row = sheet.row_values(row_index)
        if any(
            (current_row[i] if i < len(current_row) else "")
            != (original_row[i] if i < len(original_row) else "")
            for i in range(len(physical_headers))
        ):
            raise ValueError(
                "The live row changed while preparing settlement. Refresh Sheets and review it before retrying."
            )
        update_columns = {name: headers.index(name) for name in updates}
        cells = [
            {
                "range": gspread.utils.rowcol_to_a1(
                    row_index, update_columns[name] + 1
                ),
                "values": [[value]],
            }
            for name, value in updates.items()
        ]
        sheet.batch_update(cells, value_input_option="RAW")
        saved_row = sheet.row_values(row_index)
        if any(
            update_columns[name] >= len(saved_row)
            or saved_row[update_columns[name]] != value
            for name, value in updates.items()
        ):
            raise RuntimeError(
                "Settlement write could not be verified; refresh Sheets and inspect this ticket before retrying."
            )
    except ValueError:
        raise
    except Exception:
        logging.exception("Unexpected error")
        logging.warning(
            "Settlement Sheets access, update, or verification failed"
        )
        raise RuntimeError(
            "Settlement write could not be confirmed. Refresh Sheets and inspect the live ticket before retrying; check worksheet edit access if needed."
        ) from None
    try:
        _clear_calendar_events(ticket)
    except Exception:
        logging.exception("Unexpected error")
        logging.warning("Settlement saved; calendar cleanup could not complete")
    return f"Settlement saved and verified · cash P{amounts['tender']:,.2f} · realized profit P{amounts['profit']:,.2f} · retained overpayment P{amounts['retained']:,.2f}."


def _mutate_live_ticket(
    ticket: str, operation: str, value: str, second: str, third: str
) -> str:
    try:
        import gspread
        from google.oauth2 import service_account

        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/calendar",
            ],
        )
        sheet = (
            gspread.authorize(creds)
            .open_by_key(os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"])
            .worksheet(os.environ["GOOGLE_SHEETS_WORKSHEET"])
        )
        if operation == "interest_extension" or (
            operation == "status" and value == "Extended"
        ):
            raise ValueError(
                "Use the verified Extend 30 days action with cash payment."
            )
        values = sheet.get_all_values()
        headers = values[0]
        required = [
            "Status",
            "Payment Date",
            "Payment Amount",
            "Remaining Principal",
            "Payment Type",
            "Last Updated",
        ]
        for name in required:
            if name not in headers:
                sheet.update_cell(1, len(headers) + 1, name)
                headers.append(name)
        row_index = next(
            (
                i
                for i, row in enumerate(sheet.get_all_values()[1:], 2)
                if (
                    row[headers.index("Submission ID")]
                    if "Submission ID" in headers
                    and len(row) > headers.index("Submission ID")
                    else ""
                )
                == ticket
                or (
                    row[headers.index("Pawn / Loan No.")]
                    if "Pawn / Loan No." in headers
                    and len(row) > headers.index("Pawn / Loan No.")
                    else ""
                )
                == ticket
            ),
            0,
        )
        if not row_index:
            raise ValueError("Ticket was not found in the live worksheet.")
        row = sheet.row_values(row_index)
        raw = {
            headers[i]: row[i] if i < len(row) else ""
            for i in range(len(headers))
        }
        principal = _money(raw.get("Approved Loan Amount", ""))
        remaining = _money(raw.get("Remaining Principal", "")) or principal
        interest = _money(raw.get("Interest Amount", ""))
        updates: dict[str, str] = {"Last Updated": _gaborone_now()}
        if operation == "partial":
            amount = _money(value)
            if amount <= 0 or amount > remaining:
                raise ValueError(
                    "Enter a positive payment not greater than the remaining principal."
                )
            remaining -= amount
            updates.update(
                {
                    "Status": "Settled" if remaining <= 0 else "Active",
                    "Remaining Principal": f"{remaining:.2f}",
                    "Payment Amount": f"{amount:.2f}",
                    "Payment Date": _validated_payment_date(second),
                    "Payment Type": "Partial Principal",
                }
            )
        elif operation == "delete":
            sheet.delete_rows(row_index)
            _clear_calendar_events(ticket)
            return "Ticket deleted and managed reminders purged."
        else:
            status = value
            if status not in {"Settled", "Extended", "Defaulted"}:
                raise ValueError("Choose a valid operational status.")
            if status == "Settled":
                amount = _money(second)
                if amount <= 0:
                    raise ValueError(
                        "Settled records require a positive payment amount."
                    )
                updates.update(
                    {
                        "Status": "Settled",
                        "Payment Amount": f"{amount:.2f}",
                        "Payment Date": _validated_payment_date(third),
                        "Payment Type": "Settlement",
                    }
                )
            else:
                updates["Status"] = "Defaulted"
        cells = []
        for key, item in updates.items():
            if key in headers:
                cells.append(
                    {
                        "range": f"{gspread.utils.rowcol_to_a1(row_index, headers.index(key) + 1)}",
                        "values": [[item]],
                    }
                )
        sheet.batch_update(cells)
        if operation in {"partial", "interest_extension"} or value in {
            "Extended",
            "Defaulted",
            "Settled",
        }:
            _clear_calendar_events(ticket)
        return "Ticket operation committed successfully."
    except ValueError:
        raise
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise RuntimeError(
            "The live operation could not be completed safely."
        ) from e


def _record_sale(ticket: str, revenue: float, sale_date: str) -> str:
    try:
        parsed_date = _date_value(sale_date)
        if (
            not ticket.strip()
            or not math.isfinite(revenue)
            or revenue <= 0
            or parsed_date is None
        ):
            raise ValueError(
                "Enter a valid ticket, positive final sale price and valid sale date."
            )
        import gspread
        from google.oauth2 import service_account

        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/calendar",
            ],
        )
        sheet = (
            gspread.authorize(creds)
            .open_by_key(os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"])
            .worksheet(os.environ["GOOGLE_SHEETS_WORKSHEET"])
        )
        values = sheet.get_all_values()
        headers = [header.strip() for header in values[0]]
        matches = []
        for i, row in enumerate(values[1:], 2):
            raw = {
                header: row[j].strip() if j < len(row) else ""
                for j, header in enumerate(headers)
            }
            if (
                _first(raw, ["Pawn / Loan No.", "Submission ID"])
                == ticket.strip()
            ):
                matches.append((i, raw))
        if len(matches) != 1:
            raise ValueError(
                "Ticket must match exactly one live worksheet record."
            )
        row_index, raw = matches[0]
        if _first(
            raw, ["Status", "Loan Status"]
        ).casefold() != "defaulted" or _is_sold(
            raw.get("Liquidation Status", "")
        ):
            raise ValueError(
                "Only unsold Defaulted inventory can be marked Sold."
            )
        principal_value = _money_value(raw.get("Approved Loan Amount", ""))
        principal = (
            principal_value
            if principal_value is not None
            else _money(
                _first(
                    raw,
                    [
                        "Principal Loan Amount",
                        "Principal",
                        "Principal (BWP)",
                        "Loan Amount",
                    ],
                )
            )
        )
        if not math.isfinite(principal) or principal < 0:
            raise ValueError(
                "The item has an invalid principal. Correct it before recording a sale."
            )
        for name in [
            "Status",
            "Liquidation Status",
            "Sale Date",
            "Final Cash Revenue",
            "Realized Profit",
            "Recommended Selling Price",
            "Last Updated",
        ]:
            if name not in headers:
                sheet.update_cell(1, len(headers) + 1, name)
                headers.append(name)
        row = values[row_index - 1]
        market = _money(
            row[headers.index("Estimated Market Value")]
            if "Estimated Market Value" in headers
            and headers.index("Estimated Market Value") < len(row)
            else ""
        )
        updates = {
            "Liquidation Status": "Sold",
            "Sale Date": parsed_date.isoformat(),
            "Final Cash Revenue": f"{revenue:.2f}",
            "Realized Profit": f"{revenue - principal:.2f}",
            "Recommended Selling Price": f"{(market * 0.8 if market else principal):.2f}",
            "Last Updated": _gaborone_now(),
            "Status": "Settled",
        }
        sheet.batch_update(
            [
                {
                    "range": f"{gspread.utils.rowcol_to_a1(row_index, headers.index(key) + 1)}",
                    "values": [[value]],
                }
                for key, value in updates.items()
                if key in headers
            ]
        )
        _clear_calendar_events(ticket)
        return "Inventory item marked Sold; net profit recorded and reminders cleared."
    except ValueError:
        raise
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise RuntimeError("Sale operation failed safely.") from e


def _clear_calendar_events(ticket: str) -> None:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/calendar"]
        )
        service = build(
            "calendar", "v3", credentials=creds, cache_discovery=False
        )
        token = ""
        while True:
            response = (
                service.events()
                .list(
                    calendarId=os.environ["GOOGLE_CALENDAR_ID"],
                    privateExtendedProperty=[
                        "setlhoa_managed=true",
                        f"ticket={ticket}",
                    ],
                    pageToken=token,
                )
                .execute()
            )
            for event in response.get("items", []):
                service.events().delete(
                    calendarId=os.environ["GOOGLE_CALENDAR_ID"],
                    eventId=event["id"],
                ).execute()
            token = response.get("nextPageToken", "")
            if not token:
                break
    except Exception:
        logging.exception("Unexpected error")
        logging.warning("Calendar reminder cleanup failed")
        raise RuntimeError("Calendar reminder cleanup failed safely.") from None


def _reconcile_reminders(records: list[LoanRecord]) -> ReminderSummary:
    try:
        import json as json_module
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        desired_payloads: list[
            tuple[LoanRecord, ReminderStage, dict[str, object]]
        ] = []
        desired_identities: set[tuple[str, str]] = set()
        for record in records:
            for stage, payload in _reminder_payloads_for_record(record):
                identity = (record["ticket"], stage["reminder_type"])
                desired_identities.add(identity)
                desired_payloads.append((record, stage, payload))

        info = json_module.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/calendar"]
        )
        service = build(
            "calendar", "v3", credentials=creds, cache_discovery=False
        )
        calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
        summary: ReminderSummary = {
            "day_23": 0,
            "day_30": 0,
            "day_35": 0,
            "managed": 0,
            "message": "Calendar reminders reconciled.",
        }
        managed_events: list[dict[str, object]] = []
        token = ""
        while True:
            response = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    privateExtendedProperty="setlhoa_managed=true",
                    showDeleted=False,
                    maxResults=2500,
                    pageToken=token or None,
                )
                .execute()
            )
            managed_events.extend(response.get("items", []))
            token = response.get("nextPageToken", "")
            if not token:
                break

        cleanup_count = 0
        retained_events: list[dict[str, object]] = []
        for event in managed_events:
            properties = event.get("extendedProperties") or {}
            private_properties = properties.get("private") or {}
            identity = (
                str(private_properties.get("ticket", "")),
                str(private_properties.get("reminder_type", "")),
            )
            if identity not in desired_identities:
                service.events().delete(
                    calendarId=calendar_id,
                    eventId=event["id"],
                ).execute()
                cleanup_count += 1
            else:
                retained_events.append(event)
        managed_events = retained_events

        for record, stage, payload in desired_payloads:
            existing = _match_managed_event(
                managed_events, record["ticket"], stage["reminder_type"]
            )
            if existing:
                service.events().patch(
                    calendarId=calendar_id,
                    eventId=existing["id"],
                    body=payload,
                ).execute()
            else:
                created = (
                    service.events()
                    .insert(calendarId=calendar_id, body=payload)
                    .execute()
                )
                managed_events.append(created)
            summary[stage["summary_key"]] += 1
            summary["managed"] += 1
        summary["message"] = (
            f"Calendar reminders reconciled · {summary['managed']} managed events "
            f"across Day 23/30/35 · {cleanup_count} obsolete events cleaned up."
        )
        return summary
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise
