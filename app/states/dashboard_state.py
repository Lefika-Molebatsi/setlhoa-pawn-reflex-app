import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import TypedDict
from urllib.parse import quote

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
    day_27: str
    day_27_status: str
    day_30_action: str
    day_30_status: str
    day_32: str
    day_32_status: str
    day_35: str
    day_35_status: str
    daily_penalty: float
    days_overdue: int
    late_fees: float
    final_payout: float
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


NOTICE_TEMPLATES: dict[str, str] = {
    "Pre-Due": "Hello. A friendly reminder that your loan {ticket} is due in 3 days. To settle or extend your loan, please contact us at 74927495/72796888.",
    "Due Today": "Hello. Your loan {ticket} is due Today. Please arrange payment today to maintain your loan in good standing. Call/WhatsApp 74927495/72796888 for bank/e-wallet details.",
    "Final Warning": "Hello. Your loan ticket {ticket} is now 5 days overdue. Please settle by the end of the day to safeguard your item from liquidation. Contact us immediately at 74927495/72796888.",
    "Courtesy": "Hello. A courtesy reminder that your loan {ticket} matures in 7 days. To plan your settlement or an extension, please contact us at 74927495/72796888.",
    "Overdue": "Hello. Your loan ticket {ticket} is now 2 days overdue and daily penalties are accruing. Please settle as soon as possible to protect your item. Contact us at 74927495/72796888.",
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
    "day_27": "",
    "day_27_status": "",
    "day_30_action": "",
    "day_30_status": "",
    "day_32": "",
    "day_32_status": "",
    "day_35": "",
    "day_35_status": "",
    "daily_penalty": 0.0,
    "days_overdue": 0,
    "late_fees": 0.0,
    "final_payout": 0.0,
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
}


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


def _queue_stage(countdown_days: int) -> tuple[str, str, str]:
    """Return (stage, badge color key, display label) for a countdown value."""
    if countdown_days < 0:
        overdue = abs(countdown_days)
        unit = "day" if overdue == 1 else "days"
        return (
            "Overdue Stage",
            "dark-red",
            f"{overdue} {unit} overdue · Overdue Stage",
        )
    if countdown_days == 0:
        return ("Due Today", "red", "Due today · 0 days remaining")
    if countdown_days <= 3:
        unit = "day" if countdown_days == 1 else "days"
        return (
            "Pre-Due Stage",
            "orange",
            f"{countdown_days} {unit} remaining · Pre-Due Stage",
        )
    if countdown_days <= 7:
        return (
            "Courtesy Stage",
            "blue",
            f"{countdown_days} days remaining · Courtesy Stage",
        )
    return (
        "On Track",
        "green",
        f"{countdown_days} days remaining · On Track",
    )


def _queue_notice_type(countdown_days: int) -> str:
    """Map a countdown value to the exact NOTICE_TEMPLATES key."""
    if countdown_days < 0:
        return "Final Warning"
    if countdown_days == 0:
        return "Due Today"
    return "Pre-Due"


def _whatsapp_link(mobile: str, ticket: str, countdown_days: int) -> str:
    """Build a wa.me link with normalized Botswana mobile and exact notice text."""
    normalized = _normalize_mobile(mobile)
    if not normalized:
        return ""
    message = _notice_text(_queue_notice_type(countdown_days), ticket)
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
        "offset": 23,
        "summary_key": "day_23",
        "notice_key": "Courtesy",
        "milestone_field": "day_23",
    },
    {
        "reminder_type": "Day 27 Pre-Due",
        "title_prefix": "PRE-DUE WARNING",
        "day_label": "Day 27",
        "offset": 27,
        "summary_key": "day_27",
        "notice_key": "Pre-Due",
        "milestone_field": "day_27",
    },
    {
        "reminder_type": "Day 30 Due Today",
        "title_prefix": "DUE TODAY",
        "day_label": "Day 30",
        "offset": 30,
        "summary_key": "day_30",
        "notice_key": "Due Today",
        "milestone_field": "day_30_action",
    },
    {
        "reminder_type": "Day 32 Overdue",
        "title_prefix": "OVERDUE NOTICE",
        "day_label": "Day 32",
        "offset": 32,
        "summary_key": "day_32",
        "notice_key": "Overdue",
        "milestone_field": "day_32",
    },
    {
        "reminder_type": "Day 35 Final Warning",
        "title_prefix": "FINAL WARNING",
        "day_label": "Day 35",
        "offset": 35,
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
    """Day 30 always uses the resolved due date; others use derived dates."""
    if stage["summary_key"] == "day_30":
        return due
    derived = _date_value(record.get(stage["milestone_field"], ""))
    if derived:
        return derived
    return issue + timedelta(days=stage["offset"]) if issue else None


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
    """All five stage payloads for one Active, resolvable loan record."""
    if record["status"] != "Active" or not record["ticket"]:
        return []
    issue = _date_value(record["issue_date"]) or _date_value(
        record["loan_date"]
    )
    due = _resolved_due_date(record["due_date"], issue)
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
    day_27: int
    day_30: int
    day_32: int
    day_35: int
    managed: int
    message: str


class DashboardState(rx.State):
    records: list[LoanRecord] = []
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
        "day_27": 0,
        "day_30": 0,
        "day_32": 0,
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
    liquidation_search: str = ""
    liquidation_sort: str = "margin"
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
            due = _resolved_due_date(record["due_date"], issue)
            if due is None:
                continue
            countdown = (due - today).days
            stage, color, label = _queue_stage(countdown)
            url = _whatsapp_link(
                record["mobile"] or record["contact"],
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
    def liquidation_records(self) -> list[LoanRecord]:
        query = self.liquidation_search.lower().strip()
        records = [
            record
            for record in self.records
            if record["status"] == "Defaulted"
            and (
                not query
                or query in f"{record['ticket']} {record['item']}".lower()
            )
        ]
        return sorted(
            records,
            key=lambda record: (
                record["recommended_price"] - record["principal"]
            ),
            reverse=self.liquidation_sort == "margin",
        )

    @rx.var
    def history_records(self) -> list[LoanRecord]:
        query = self.history_search.lower().strip()
        if not query:
            return []
        return [
            record
            for record in self.records
            if query in record["omang"].lower()
            or query in _normalize_mobile(record["mobile"])
        ]

    @rx.var
    def selected_customer_records(self) -> list[LoanRecord]:
        if not self.selected_customer_key:
            return []
        return [
            record
            for record in self.records
            if record["omang"] == self.selected_customer_key
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
        self.selected_customer_key = key

    @rx.event
    def set_sale_revenue(self, value: str):
        self.sale_revenue = value

    @rx.event
    def set_sale_date(self, value: str):
        self.sale_date = value

    @rx.event
    def toggle_sale_confirmation(self):
        self.sale_confirmed = not self.sale_confirmed

    @rx.event
    async def submit_sale(self):
        if not self.selected_ticket or not self.sale_confirmed:
            self.error_message = (
                "Select a defaulted ticket and confirm the sale write."
            )
            return
        try:
            revenue = _money(self.sale_revenue)
            if revenue <= 0 or not _date_value(self.sale_date):
                raise ValueError(
                    "Enter a positive final revenue and valid sale date."
                )
            result = await asyncio.to_thread(
                _record_sale, self.selected_ticket, revenue, self.sale_date
            )
            self.success_message = result
            self.sale_confirmed = False
            await self.refresh_sheets()
        except ValueError as e:
            self.error_message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error_message = (
                "Sale write failed safely; no partial confirmation was shown."
            )

    @rx.var
    def selected_record(self) -> LoanRecord:
        for record in self.records:
            if record["ticket"] == self.selected_ticket:
                return record
        return dict(EMPTY_RECORD)

    @rx.var
    def notice_message(self) -> str:
        return _notice_text(self.notice_type, self.selected_record["ticket"])

    @rx.var
    def whatsapp_url(self) -> str:
        digits = "".join(
            ch for ch in self.selected_record["mobile"] if ch.isdigit()
        )
        normalized = (
            digits[3:] if digits.startswith("267") else digits.lstrip("0")
        )
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
        self.selected_ticket = ticket

    @rx.event
    def set_notice_type(self, value: str):
        self.notice_type = value

    @rx.event
    def set_payment_amount(self, value: str):
        self.payment_amount = value

    @rx.event
    def set_payment_date(self, value: str):
        self.payment_date = value

    @rx.event
    def toggle_delete_confirmation(self):
        self.delete_confirmed = not self.delete_confirmed

    @rx.event
    async def update_ticket_status(self, status: str):
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
        await self._mutate_ticket(
            "interest_extension", self.payment_amount, self.payment_date, ""
        )

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
        return sum(record["approved"] for record in self.visible_records)

    @rx.var
    def realized_interest(self) -> float:
        return sum(
            record["interest"]
            for record in self.visible_records
            if record["status"] == "Settled"
        )

    @rx.var
    def liquidation_profit(self) -> float:
        return 0.0

    @rx.var
    def active_capital(self) -> float:
        return sum(
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
        self.is_loading = True
        self.error_message = ""
        self.success_message = ""
        try:
            payload = await asyncio.to_thread(_read_live_records)
            self.records = payload["records"]
            self.months = payload["months"]
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
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Africa/Gaborone")).strftime(
            "%d %b %Y · %H:%M"
        )
    except Exception as e:
        logging.exception(f"Error: {e}")
        return datetime.now().strftime("%d %b %Y · %H:%M")


def _normalize_mobile(value: str) -> str:
    digits = "".join(
        character for character in str(value) if character.isdigit()
    )
    return digits[3:] if digits.startswith("267") else digits.lstrip("0")


def _money(value: str) -> float:
    parsed = _money_value(value)
    return parsed if parsed is not None else 0.0


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


DAY_FIRST_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d %m %Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
)


def _parse_business_date(value: str) -> date | None:
    """Parse any incoming business date using strict day-first semantics.

    Ambiguous numeric dates such as 03/09/2026 resolve to 3 September 2026.
    Unambiguous ISO dates (YYYY-MM-DD) and common timestamp suffixes
    ("03/09/2026 10:45:00", "2026-09-03T10:45:00Z") are accepted safely.
    """
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text.replace("T", " ").split(" ")[0].strip()
    if candidate.count(":"):
        candidate = candidate.split(":")[0]
    for source in (candidate, text):
        for fmt in DAY_FIRST_FORMATS:
            try:
                return datetime.strptime(source, fmt).date()
            except ValueError:
                continue
    parts = [
        piece
        for piece in candidate.replace("-", "/").replace(".", "/").split("/")
        if piece
    ]
    if len(parts) == 3 and all(piece.isdigit() for piece in parts):
        try:
            if len(parts[0]) == 4:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            year = int(parts[2])
            year = year + 2000 if year < 100 else year
            return date(year, int(parts[1]), int(parts[0]))
        except ValueError:
            return None
    return None


def _parse_jotform_source_date(value: str) -> date | None:
    """Parse Jotform source dates with strict MM-DD-YYYY semantics."""
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text.replace("T", " ").split(" ", 1)[0].strip()
    if len(candidate) == 10 and candidate[2] == "-" and candidate[5] == "-":
        try:
            month, day, year = (int(part) for part in candidate.split("-"))
            return date(year, month, day)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error: {e}")
            return None
    if len(candidate) == 10 and candidate[4] == "-" and candidate[7] == "-":
        try:
            return date.fromisoformat(candidate)
        except ValueError as e:
            logging.exception(f"Error: {e}")
            return None
    return None


def _date_value(value: str) -> date | None:
    """Centralized day-first date parsing used across this module."""
    return _parse_business_date(value)


def _iso_or_raw(value: str) -> str:
    """Return ISO text when parseable, otherwise keep the nonempty raw value."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = _parse_business_date(raw)
    return parsed.isoformat() if parsed else raw


def _resolved_due_date(explicit: str, issue_date: date | None) -> date | None:
    """Use a valid Jotform due date, else issue date plus 30 days."""
    parsed = _parse_jotform_source_date(explicit) or _parse_business_date(
        explicit
    )
    if parsed:
        return parsed
    return issue_date + timedelta(days=30) if issue_date else None


def _days_to_due(due_date: date | None, today: date) -> int | None:
    if due_date is None:
        return None
    return (due_date - today).days


def _countdown_stage(due_date: date | None, today: date, status: str) -> str:
    """Pure helper deriving a countdown stage label for reminder queues."""
    if status == "Settled":
        return "Settled"
    remaining = _days_to_due(due_date, today)
    if remaining is None:
        return "Unscheduled"
    if remaining > 3:
        return "Upcoming"
    if remaining > 0:
        return "Pre-Due"
    if remaining == 0:
        return "Due Today"
    if remaining >= -4:
        return "Overdue"
    return "Final Warning"


def _stage_notice_type(stage: str) -> str:
    """Map a countdown stage to the exact notice template key."""
    if stage == "Due Today":
        return "Due Today"
    if stage == "Final Warning":
        return "Final Warning"
    return "Pre-Due"


def _gaborone_date() -> date:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Africa/Gaborone")).date()
    except Exception as e:
        logging.exception(f"Error: {e}")
        return date.today()


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
    counts: dict[str, int] = {}
    result: list[str] = []
    for header in headers:
        key = header.strip() or "Unnamed"
        counts[key] = counts.get(key, 0) + 1
        result.append(f"{key} [{counts[key]}]" if counts[key] > 1 else key)
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
        sheet = client.open_by_key(
            os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"]
        ).worksheet(os.environ["GOOGLE_SHEETS_WORKSHEET"])
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
            due_date = _resolved_due_date(
                raw.get("Maturity / Due Date", ""),
                issue_date,
            )
            explicit = _first(raw, ["Status", "Loan Status"]).title()
            status = (
                explicit
                if explicit in {"Active", "Settled", "Extended", "Defaulted"}
                else "Active"
            )
            if not explicit and due_date and due_date < date.today():
                status = "Active"
            category = raw.get("Category", raw.get("Category [2]", ""))
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
            days_overdue = (
                max(0, (today - due_date).days)
                if due_date and not settled
                else 0
            )
            late_fees = round(days_overdue * penalty, 2)
            final_payout = round(total_due + late_fees, 2)
            day_23 = issue_date + timedelta(days=23) if issue_date else None
            day_27 = issue_date + timedelta(days=27) if issue_date else None
            day_32 = issue_date + timedelta(days=32) if issue_date else None
            day_35 = issue_date + timedelta(days=35) if issue_date else None
            date_settled = _iso_or_raw(
                _first(
                    raw,
                    [
                        "Date Settled",
                        "Settlement Date",
                        "Payment Date",
                    ],
                )
            )
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
                    "day_27": day_27.isoformat() if day_27 else "",
                    "day_27_status": _milestone_status(
                        _first(raw, ["Day 27 Status"]), day_27, today, settled
                    ),
                    "day_30_action": due_date.isoformat() if due_date else "",
                    "day_30_status": _milestone_status(
                        _first(raw, ["Day 30 Status"]),
                        due_date,
                        today,
                        settled,
                    ),
                    "day_32": day_32.isoformat() if day_32 else "",
                    "day_32_status": _milestone_status(
                        _first(raw, ["Day 32 Status"]), day_32, today, settled
                    ),
                    "day_35": day_35.isoformat() if day_35 else "",
                    "day_35_status": _milestone_status(
                        _first(raw, ["Day 35 Status"]), day_35, today, settled
                    ),
                    "daily_penalty": penalty,
                    "days_overdue": days_overdue,
                    "late_fees": late_fees,
                    "final_payout": final_payout,
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
                    "due_date": due_date.isoformat() if due_date else "",
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
                    "remaining_principal": (
                        remaining_value
                        if (
                            remaining_value := _money_value(
                                raw.get("Remaining Principal", "")
                            )
                        )
                        is not None
                        else principal
                    ),
                    "status": status,
                    "submission_id": _display_text(
                        raw.get("Submission ID", "")
                    ),
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
            "months": sorted(
                {
                    record["month"]
                    for record in records
                    if record["month"] != "Unknown"
                },
                reverse=True,
            ),
            "worksheet": sheet.title,
            "calendar_health": "Connected · read access verified",
        }
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise


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
        due = _date_value(raw.get("Maturity / Due Date", "")) or date.today()
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
                    "Payment Date": second or date.today().isoformat(),
                    "Payment Type": "Partial Principal",
                }
            )
        elif operation == "interest_extension":
            amount = _money(value)
            if amount < interest:
                raise ValueError(
                    "Interest-only extension must cover at least the current interest."
                )
            due += timedelta(days=30)
            updates.update(
                {
                    "Status": "Extended",
                    "Maturity / Due Date": due.strftime("%d/%m/%Y"),
                    "Payment Amount": f"{amount:.2f}",
                    "Payment Date": second or date.today().isoformat(),
                    "Payment Type": "Interest-only Extension",
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
                        "Payment Date": third or date.today().isoformat(),
                        "Payment Type": "Settlement",
                    }
                )
            elif status == "Extended":
                rate = interest / principal if principal else 0.0
                due += timedelta(days=30)
                next_interest = remaining * rate
                updates.update(
                    {
                        "Status": "Extended",
                        "Maturity / Due Date": due.strftime("%d/%m/%Y"),
                        "Interest Amount": f"{next_interest:.2f}",
                        "Total Amount Due": f"{remaining + next_interest:.2f}",
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
        headers = values[0]
        for name in [
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
        row_index = next(
            (i for i, row in enumerate(values[1:], 2) if ticket in row), 0
        )
        if not row_index:
            raise ValueError("Ticket was not found in the live worksheet.")
        row = values[row_index - 1]
        principal = _money(
            row[headers.index("Approved Loan Amount")]
            if "Approved Loan Amount" in headers
            and headers.index("Approved Loan Amount") < len(row)
            else ""
        )
        market = _money(
            row[headers.index("Estimated Market Value")]
            if "Estimated Market Value" in headers
            and headers.index("Estimated Market Value") < len(row)
            else ""
        )
        updates = {
            "Liquidation Status": "Liquidated / Sold",
            "Sale Date": sale_date,
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
        return "Sale committed; ticket marked Liquidated / Sold and reminders cleared."
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
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise RuntimeError("Calendar reminder cleanup failed safely.") from e


def _reconcile_reminders(records: list[LoanRecord]) -> ReminderSummary:
    try:
        import json as json_module
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

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
            "day_27": 0,
            "day_30": 0,
            "day_32": 0,
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
        for record in records:
            for stage, payload in _reminder_payloads_for_record(record):
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
            f"across Day 23/27/30/32/35."
        )
        return summary
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise
