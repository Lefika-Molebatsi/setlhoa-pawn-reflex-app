import reflex as rx
from app.states.dashboard_state import (
    DashboardState,
    LoanRecord,
    ReminderRow,
)

SURFACE = rx.color_mode_cond(
    "bg-white border-[#E5E7EB]", "bg-[#202629] border-white/10"
)
INSET = rx.color_mode_cond(
    "bg-[#F8FAFC] border-[#E5E7EB]", "bg-[#171a1c] border-white/10"
)
BORDER = rx.color_mode_cond("border-[#E5E7EB]", "border-white/10")
BORDER_SOFT = rx.color_mode_cond("border-[#F1F5F9]", "border-white/5")
TEXT_STRONG = rx.color_mode_cond("text-[#111827]", "text-white")
TEXT_BODY = rx.color_mode_cond("text-[#334155]", "text-[#d6ddda]")
TEXT_SECONDARY = rx.color_mode_cond("text-[#475569]", "text-[#aeb6b2]")
TEXT_MUTED = rx.color_mode_cond("text-[#64748B]", "text-[#8f9a95]")
ACCENT_TEXT = rx.color_mode_cond("text-[#189b2b]", "text-[#2ec24a]")
POSITIVE_TEXT = rx.color_mode_cond("text-[#15803d]", "text-[#8bd4b0]")
DANGER_TEXT = rx.color_mode_cond("text-[#b91c1c]", "text-[#e9a18c]")
ROW_HOVER = rx.color_mode_cond("hover:bg-[#F1F5F9]", "hover:bg-white/5")
FOCUS = "focus:outline-hidden focus:ring-2 focus:ring-[#189b2b] focus:ring-offset-1 focus:ring-offset-transparent"
FIELD = rx.color_mode_cond(
    "bg-white border-[#E5E7EB] text-[#111827] placeholder:text-[#94A3B8]",
    "bg-[#202629] border-white/10 text-white placeholder:text-[#8f9a95]",
)
PRIMARY_BTN = "bg-[#189b2b] text-white hover:bg-[#147f23]"
GHOST_BTN = rx.color_mode_cond(
    "border-[#189b2b]/40 text-[#189b2b] hover:bg-[#189b2b]/10",
    "border-[#189b2b]/60 text-[#2ec24a] hover:bg-[#189b2b]/15",
)
TH = "px-3 py-3 text-left text-[10px] uppercase tracking-wider"


def _money(value: rx.Var) -> rx.Component:
    return rx.el.span(
        f"P{value:,.2f}",
        class_name=[
            "mt-3 block font-['IBM_Plex_Mono'] text-2xl font-bold",
            TEXT_STRONG,
        ],
    )


def _th(label: str) -> rx.Component:
    return rx.el.th(label, class_name=[TH, TEXT_MUTED])


def nav_item(item: dict[str, str]) -> rx.Component:
    return rx.el.button(
        rx.icon(item["icon"], class_name="h-4 w-4"),
        item["label"],
        on_click=lambda: DashboardState.choose_tab(item["value"]),
        class_name=rx.cond(
            DashboardState.active_tab == item["value"],
            "flex shrink-0 items-center gap-3 rounded-sm bg-[#189b2b] px-3 py-2 text-left text-sm font-semibold text-white",
            rx.color_mode_cond(
                f"flex shrink-0 items-center gap-3 rounded-sm px-3 py-2 text-left text-sm font-medium text-[#475569] hover:bg-[#189b2b]/10 hover:text-[#111827] {FOCUS}",
                f"flex shrink-0 items-center gap-3 rounded-sm px-3 py-2 text-left text-sm font-medium text-[#aeb6b2] hover:bg-[#189b2b]/15 hover:text-white {FOCUS}",
            ),
        ),
        aria_label=item["label"],
    )


def sidebar() -> rx.Component:
    items = [
        {
            "value": "dashboard",
            "label": "Executive Dashboard",
            "icon": "layout-dashboard",
        },
        {"value": "ledger", "label": "Active Pawn Ledger", "icon": "book-open"},
        {
            "value": "payments",
            "label": "Payments & Extensions",
            "icon": "arrow-left-right",
        },
        {
            "value": "reminders",
            "label": "Reminders Queue",
            "icon": "bell-ring",
        },
        {
            "value": "liquidation",
            "label": "Liquidation Queue",
            "icon": "package-open",
        },
        {
            "value": "history",
            "label": "Customer History",
            "icon": "contact-round",
        },
        {
            "value": "vehicles",
            "label": "Vehicle Valuation",
            "icon": "car-front",
        },
        {
            "value": "electronics",
            "label": "Electronics Valuation",
            "icon": "smartphone",
        },
    ]
    return rx.el.aside(
        rx.el.div(
            rx.icon("landmark", class_name="h-6 w-6 text-[#189b2b]"),
            rx.el.div(
                rx.el.p(
                    "Setlhoa Cash Solutions",
                    class_name=[
                        "text-sm font-bold tracking-tight",
                        TEXT_STRONG,
                    ],
                ),
                rx.el.p(
                    "OPERATIONS ROOM",
                    class_name=[
                        "font-['IBM_Plex_Mono'] text-[10px] tracking-[0.18em]",
                        TEXT_MUTED,
                    ],
                ),
            ),
            class_name=[
                "flex shrink-0 items-center gap-3 border-b px-5 py-5",
                BORDER,
            ],
        ),
        rx.el.div(
            rx.el.a(
                "➕ Create New Pawn Ticket",
                href="https://form.jotform.com/262402781377056",
                target="_blank",
                rel="noopener noreferrer",
                aria_label="Create New Pawn Ticket — opens the intake form in a new tab",
                class_name=f"flex w-full items-center justify-center gap-2 rounded-sm px-3 py-3 text-center text-sm font-semibold {PRIMARY_BTN} {FOCUS}",
            ),
            class_name=["shrink-0 border-b p-4", BORDER],
        ),
        rx.el.nav(
            rx.foreach(items, nav_item),
            class_name="flex min-h-0 flex-1 flex-row gap-1 overflow-x-auto p-2 sm:flex-col sm:overflow-y-auto sm:overflow-x-hidden sm:p-4",
        ),
        rx.el.div(
            rx.el.p(
                "SETLHOA CASH SOLUTIONS",
                class_name=[
                    "font-['IBM_Plex_Mono'] text-[10px] tracking-widest",
                    ACCENT_TEXT,
                ],
            ),
            rx.el.p(
                "Botswana · Africa/Gaborone",
                class_name=["mt-1 text-xs", TEXT_MUTED],
            ),
            class_name=["border-t p-4", BORDER],
        ),
        class_name=[
            "flex h-auto w-full shrink-0 flex-col border-r sm:h-full sm:w-72",
            SURFACE,
        ],
    )


def metric_card(
    label: str, value: rx.Var, detail: str, icon: str
) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon(icon, class_name="h-4 w-4 text-[#189b2b]"),
            rx.el.span(
                label,
                class_name=[
                    "text-xs font-semibold uppercase tracking-wider",
                    TEXT_MUTED,
                ],
            ),
            class_name="flex items-center gap-2",
        ),
        _money(value),
        rx.el.p(detail, class_name=["mt-2 text-xs leading-5", TEXT_MUTED]),
        class_name=["w-full rounded-sm border p-4", SURFACE],
    )


def dashboard_panel() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.p(
                    "CAPITAL COMMAND BOARD",
                    class_name=[
                        "font-['IBM_Plex_Mono'] text-xs font-bold tracking-[0.22em]",
                        ACCENT_TEXT,
                    ],
                ),
                rx.el.h1(
                    "Executive dashboard",
                    class_name=[
                        "mt-2 text-2xl font-semibold tracking-tight",
                        TEXT_STRONG,
                    ],
                ),
                rx.el.p(
                    "Live deployment visibility for the Botswana pawn book — calculated only from normalized worksheet records.",
                    class_name=["mt-2 max-w-3xl text-sm", TEXT_SECONDARY],
                ),
            ),
            rx.el.div(
                rx.el.button(
                    rx.icon("refresh-cw", class_name="h-4 w-4"),
                    "Refresh Sheets",
                    on_click=DashboardState.refresh_sheets,
                    class_name=[
                        f"flex items-center gap-2 rounded-sm border px-3 py-2 text-xs font-semibold {FOCUS}",
                        GHOST_BTN,
                    ],
                ),
                rx.el.button(
                    rx.icon("calendar-sync", class_name="h-4 w-4"),
                    rx.cond(
                        DashboardState.is_reconciling,
                        "Reconciling…",
                        "Reconcile Calendar",
                    ),
                    on_click=DashboardState.reconcile_calendar,
                    class_name=f"mt-2 flex items-center gap-2 rounded-sm px-3 py-2 text-xs font-semibold {PRIMARY_BTN} {FOCUS}",
                ),
                class_name="w-full sm:w-auto",
            ),
            class_name=[
                "flex flex-col justify-between gap-5 border-b pb-6 lg:flex-row",
                BORDER,
            ],
        ),
        rx.cond(
            DashboardState.error_message != "",
            rx.el.div(
                rx.icon("circle-alert", class_name="h-4 w-4"),
                DashboardState.error_message,
                class_name=[
                    "mt-4 flex items-center gap-2 rounded-sm border px-3 py-2 text-sm",
                    rx.color_mode_cond(
                        "border-[#fecaca] bg-[#fef2f2] text-[#b91c1c]",
                        "border-[#b95b3e]/50 bg-[#b95b3e]/10 text-[#e9a18c]",
                    ),
                ],
            ),
            rx.cond(
                DashboardState.success_message != "",
                rx.el.div(
                    rx.icon("circle_check", class_name="h-4 w-4"),
                    DashboardState.success_message,
                    class_name=[
                        "mt-4 flex items-center gap-2 rounded-sm border px-3 py-2 text-sm",
                        rx.color_mode_cond(
                            "border-[#bbf7d0] bg-[#f0fdf4] text-[#15803d]",
                            "border-[#57b38a]/40 bg-[#57b38a]/10 text-[#8bd4b0]",
                        ),
                    ],
                ),
                rx.fragment(),
            ),
        ),
        rx.el.div(
            rx.el.div(
                "Month lens",
                class_name=["text-xs uppercase tracking-wider", TEXT_MUTED],
            ),
            rx.el.div(
                rx.el.select(
                    rx.el.option("All live months", value="ALL"),
                    rx.foreach(
                        DashboardState.months,
                        lambda month: rx.el.option(month, value=month),
                    ),
                    value=DashboardState.selected_month,
                    on_change=DashboardState.choose_month,
                    class_name=[
                        f"w-full appearance-none rounded-sm border px-3 py-2 pr-9 text-sm {FOCUS}",
                        FIELD,
                    ],
                ),
                rx.icon(
                    "chevron-down",
                    class_name=[
                        "pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2",
                        TEXT_MUTED,
                    ],
                ),
                class_name="relative mt-2 w-full max-w-xs",
            ),
            class_name="mt-5",
        ),
        rx.el.div(
            metric_card(
                "Monthly deployed capital",
                DashboardState.deployed_capital,
                "Approved loan amount for the selected live month.",
                "banknote",
            ),
            metric_card(
                "Monthly realized interest",
                DashboardState.realized_interest,
                "Interest from records explicitly marked Settled.",
                "trending-up",
            ),
            metric_card(
                "Liquidation profit",
                DashboardState.liquidation_profit,
                "No liquidation fields in source; safe zero until that workflow is live.",
                "package-check",
            ),
            metric_card(
                "Active capital",
                DashboardState.active_capital,
                "Approved capital in Active or Extended operational status.",
                "wallet-cards",
            ),
            class_name="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.el.p(
                        "STATUS DISTRIBUTION",
                        class_name=[
                            "font-['IBM_Plex_Mono'] text-xs font-bold tracking-[0.18em]",
                            ACCENT_TEXT,
                        ],
                    ),
                    rx.el.p(
                        "Conservative operational reading",
                        class_name=["mt-1 text-xs", TEXT_MUTED],
                    ),
                ),
                rx.foreach(
                    [
                        ("Active", DashboardState.active_count),
                        ("Settled", DashboardState.settled_count),
                        ("Extended", DashboardState.extended_count),
                        ("Defaulted", DashboardState.defaulted_count),
                    ],
                    lambda item: rx.el.div(
                        rx.el.div(
                            rx.el.span(
                                item[0], class_name=["text-sm", TEXT_BODY]
                            ),
                            rx.el.span(
                                item[1],
                                class_name=[
                                    "font-['IBM_Plex_Mono'] text-sm",
                                    TEXT_STRONG,
                                ],
                            ),
                            class_name="flex justify-between",
                        ),
                        rx.el.progress(
                            value=item[1],
                            max=DashboardState.visible_records.length(),
                            class_name="mt-2 h-2 w-full accent-[#189b2b]",
                        ),
                        class_name="mt-4",
                    ),
                ),
                class_name=["rounded-sm border p-5", SURFACE],
            ),
            rx.el.div(
                rx.el.p(
                    "INTEGRATION HEALTH",
                    class_name=[
                        "font-['IBM_Plex_Mono'] text-xs font-bold tracking-[0.18em]",
                        ACCENT_TEXT,
                    ],
                ),
                rx.el.div(
                    rx.el.p(
                        "Google Sheets", class_name=["text-sm", TEXT_SECONDARY]
                    ),
                    rx.el.p(
                        DashboardState.sheets_health,
                        class_name=["mt-1 text-sm", POSITIVE_TEXT],
                    ),
                    class_name="mt-4",
                ),
                rx.el.div(
                    rx.el.p(
                        "Google Calendar",
                        class_name=["text-sm", TEXT_SECONDARY],
                    ),
                    rx.el.p(
                        DashboardState.calendar_health,
                        class_name=["mt-1 text-sm", POSITIVE_TEXT],
                    ),
                    class_name="mt-4",
                ),
                rx.el.div(
                    rx.el.p(
                        "Last Sheets refresh",
                        class_name=["text-sm", TEXT_SECONDARY],
                    ),
                    rx.el.p(
                        DashboardState.last_refresh,
                        class_name=[
                            "mt-1 font-['IBM_Plex_Mono'] text-sm",
                            TEXT_STRONG,
                        ],
                    ),
                    class_name="mt-4",
                ),
                rx.el.p(
                    "Calendar is never mutated on page load. Reconciliation is explicit and idempotent.",
                    class_name=[
                        "mt-5 border-t pt-4 text-xs leading-5",
                        BORDER,
                        TEXT_MUTED,
                    ],
                ),
                class_name=["rounded-sm border p-5", SURFACE],
            ),
            class_name="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2",
        ),
        class_name="w-full",
    )


LEDGER_COLUMNS: list[str] = [
    "Ticket #",
    "Issue Date",
    "Customer Name",
    "Contact #",
    "Item Category",
    "Description / IMEI / Serial",
    "Principal (BWP)",
    "Interest Rate",
    "Interest (BWP)",
    "Total Due (BWP)",
    "Due Date (Day 30)",
    "Status",
    "Day 23 Courtesy",
    "Day 23 Status",
    "Day 27 Pre-Due",
    "Day 27 Status",
    "Day 30 Due Action",
    "Day 30 Status",
    "Day 32 Overdue",
    "Day 32 Status",
    "Day 35 Final Warning",
    "Day 35 Status",
    "Daily Penalty (BWP)",
    "Days Overdue",
    "Late Fees (BWP)",
    "Final Payout (BWP)",
    "Date Settled",
    "Remarks / Notes",
]

CELL = "whitespace-nowrap px-3 py-3"
CELL_MONO = "whitespace-nowrap px-3 py-3 font-['IBM_Plex_Mono']"


def _sticky_th(label: str) -> rx.Component:
    return rx.el.th(
        label,
        class_name=[
            "sticky top-0 z-10 whitespace-nowrap px-3 py-3 text-left text-[10px] uppercase tracking-wider",
            TEXT_MUTED,
            rx.color_mode_cond("bg-[#F8FAFC]", "bg-[#171a1c]"),
        ],
    )


def _ledger_row(record: LoanRecord) -> rx.Component:
    return rx.el.tr(
        rx.el.td(
            record["ticket"],
            class_name=[CELL_MONO, ACCENT_TEXT],
        ),
        rx.el.td(record["issue_date"], class_name=[CELL_MONO, TEXT_BODY]),
        rx.el.td(
            record["customer"],
            class_name=[CELL, "font-medium", TEXT_STRONG],
        ),
        rx.el.td(record["contact"], class_name=[CELL, TEXT_BODY]),
        rx.el.td(record["item_category"], class_name=[CELL, TEXT_BODY]),
        rx.el.td(
            record["description"],
            class_name=["max-w-xs truncate px-3 py-3", TEXT_BODY],
        ),
        rx.el.td(
            f"P{record['principal']:,.2f}",
            class_name=[CELL_MONO, TEXT_BODY],
        ),
        rx.el.td(
            record["interest_rate_display"],
            class_name=[CELL_MONO, TEXT_BODY],
        ),
        rx.el.td(
            f"P{record['interest']:,.2f}",
            class_name=[CELL_MONO, TEXT_BODY],
        ),
        rx.el.td(
            f"P{record['total_due']:,.2f}",
            class_name=[CELL_MONO, TEXT_STRONG],
        ),
        rx.el.td(record["due_date"], class_name=[CELL_MONO, TEXT_BODY]),
        rx.el.td(record["status"], class_name=[CELL, POSITIVE_TEXT]),
        rx.el.td(record["day_23"], class_name=[CELL_MONO, TEXT_BODY]),
        rx.el.td(record["day_23_status"], class_name=[CELL, TEXT_MUTED]),
        rx.el.td(record["day_27"], class_name=[CELL_MONO, TEXT_BODY]),
        rx.el.td(record["day_27_status"], class_name=[CELL, TEXT_MUTED]),
        rx.el.td(record["day_30_action"], class_name=[CELL_MONO, TEXT_BODY]),
        rx.el.td(record["day_30_status"], class_name=[CELL, TEXT_MUTED]),
        rx.el.td(record["day_32"], class_name=[CELL_MONO, TEXT_BODY]),
        rx.el.td(record["day_32_status"], class_name=[CELL, TEXT_MUTED]),
        rx.el.td(record["day_35"], class_name=[CELL_MONO, TEXT_BODY]),
        rx.el.td(record["day_35_status"], class_name=[CELL, TEXT_MUTED]),
        rx.el.td(
            f"P{record['daily_penalty']:,.2f}",
            class_name=[CELL_MONO, TEXT_BODY],
        ),
        rx.el.td(
            record["days_overdue"],
            class_name=[
                CELL_MONO,
                rx.cond(record["days_overdue"] > 0, DANGER_TEXT, TEXT_BODY),
            ],
        ),
        rx.el.td(
            f"P{record['late_fees']:,.2f}",
            class_name=[CELL_MONO, TEXT_BODY],
        ),
        rx.el.td(
            f"P{record['final_payout']:,.2f}",
            class_name=[CELL_MONO, ACCENT_TEXT],
        ),
        rx.el.td(record["date_settled"], class_name=[CELL_MONO, TEXT_BODY]),
        rx.el.td(
            record["remarks"],
            class_name=["max-w-xs truncate px-3 py-3", TEXT_MUTED],
        ),
        on_click=lambda: DashboardState.select_ticket(record["ticket"]),
        class_name=rx.cond(
            DashboardState.selected_ticket == record["ticket"],
            rx.color_mode_cond(
                "cursor-pointer bg-[#189b2b]/10",
                "cursor-pointer bg-[#189b2b]/25",
            ),
            rx.color_mode_cond(
                "cursor-pointer border-b border-[#F1F5F9] hover:bg-[#F1F5F9]",
                "cursor-pointer border-b border-white/5 hover:bg-white/5",
            ),
        ),
    )


def operations_panel() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.p(
                "LIVE OPERATIONS",
                class_name=[
                    "font-['IBM_Plex_Mono'] text-xs tracking-[0.2em]",
                    ACCENT_TEXT,
                ],
            ),
            rx.el.h1(
                rx.cond(
                    DashboardState.active_tab == "ledger",
                    "Active Pawn Ledger",
                    "Payments & Extensions",
                ),
                class_name=["mt-2 text-2xl font-semibold", TEXT_STRONG],
            ),
            class_name=["border-b pb-5", BORDER],
        ),
        rx.el.div(
            rx.el.label(
                "Search tickets, customers, mobile or items",
                class_name=["text-xs font-medium", TEXT_SECONDARY],
            ),
            rx.el.input(
                default_value=DashboardState.ledger_search,
                on_change=DashboardState.set_search.debounce(400),
                placeholder="Search…",
                class_name=[
                    f"mt-2 w-full rounded-sm border px-3 py-2 text-sm {FOCUS}",
                    FIELD,
                ],
            ),
            rx.el.label(
                "Status",
                class_name=["mt-3 block text-xs font-medium", TEXT_SECONDARY],
            ),
            rx.el.div(
                rx.el.select(
                    rx.el.option("All statuses", value="ALL"),
                    rx.el.option("Active", value="Active"),
                    rx.el.option("Settled", value="Settled"),
                    rx.el.option("Extended", value="Extended"),
                    rx.el.option("Defaulted", value="Defaulted"),
                    value=DashboardState.status_filter,
                    on_change=DashboardState.set_status_filter,
                    class_name=[
                        f"w-full appearance-none rounded-sm border px-3 py-2 pr-9 text-sm {FOCUS}",
                        FIELD,
                    ],
                ),
                rx.icon(
                    "chevron-down",
                    class_name=[
                        "pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2",
                        TEXT_MUTED,
                    ],
                ),
                class_name="relative mt-2 w-full max-w-xs",
            ),
            class_name="mt-5 max-w-xl",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.foreach(LEDGER_COLUMNS, _sticky_th),
                            class_name=["border-b", BORDER],
                        )
                    ),
                    rx.el.tbody(
                        rx.foreach(DashboardState.filtered_records, _ledger_row)
                    ),
                    class_name="table-auto w-max min-w-full text-sm",
                ),
                class_name=[
                    "mt-5 max-h-[70vh] overflow-auto rounded-sm border",
                    SURFACE,
                ],
            ),
            rx.cond(
                DashboardState.selected_ticket != "",
                ticket_control_surface(),
                rx.fragment(),
            ),
            class_name="w-full",
        ),
        class_name="w-full",
    )


def _detail_cell(label: str, value: rx.Var) -> rx.Component:
    return rx.el.div(
        rx.el.p(
            label,
            class_name=[
                "text-[10px] uppercase tracking-wider",
                TEXT_MUTED,
            ],
        ),
        rx.el.p(
            value,
            class_name=[
                "mt-1 break-words font-['IBM_Plex_Mono'] text-sm",
                TEXT_STRONG,
            ],
        ),
        class_name=["rounded-sm border p-3", INSET],
    )


def ticket_detail_grid() -> rx.Component:
    record = DashboardState.selected_record
    return rx.el.div(
        rx.el.p(
            "TICKET DETAIL · ALL LEDGER FIELDS",
            class_name=[
                "font-['IBM_Plex_Mono'] text-[10px] tracking-[0.2em]",
                ACCENT_TEXT,
            ],
        ),
        rx.el.div(
            _detail_cell("Ticket #", record["ticket"]),
            _detail_cell("Issue Date", record["issue_date"]),
            _detail_cell("Customer Name", record["customer"]),
            _detail_cell("Contact #", record["contact"]),
            _detail_cell("Item Category", record["item_category"]),
            _detail_cell("Description / IMEI / Serial", record["description"]),
            _detail_cell("Principal (BWP)", f"P{record['principal']:,.2f}"),
            _detail_cell("Interest Rate", record["interest_rate_display"]),
            _detail_cell("Interest (BWP)", f"P{record['interest']:,.2f}"),
            _detail_cell("Total Due (BWP)", f"P{record['total_due']:,.2f}"),
            _detail_cell("Due Date (Day 30)", record["due_date"]),
            _detail_cell("Status", record["status"]),
            _detail_cell("Day 23 Courtesy", record["day_23"]),
            _detail_cell("Day 23 Status", record["day_23_status"]),
            _detail_cell("Day 27 Pre-Due", record["day_27"]),
            _detail_cell("Day 27 Status", record["day_27_status"]),
            _detail_cell("Day 30 Due Action", record["day_30_action"]),
            _detail_cell("Day 30 Status", record["day_30_status"]),
            _detail_cell("Day 32 Overdue", record["day_32"]),
            _detail_cell("Day 32 Status", record["day_32_status"]),
            _detail_cell("Day 35 Final Warning", record["day_35"]),
            _detail_cell("Day 35 Status", record["day_35_status"]),
            _detail_cell(
                "Daily Penalty (BWP)", f"P{record['daily_penalty']:,.2f}"
            ),
            _detail_cell("Days Overdue", record["days_overdue"].to_string()),
            _detail_cell("Late Fees (BWP)", f"P{record['late_fees']:,.2f}"),
            _detail_cell(
                "Final Payout (BWP)", f"P{record['final_payout']:,.2f}"
            ),
            _detail_cell("Date Settled", record["date_settled"]),
            _detail_cell("Remarks / Notes", record["remarks"]),
            class_name="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4",
        ),
        class_name=["mt-5 rounded-sm border p-4", SURFACE],
    )


def ticket_control_surface() -> rx.Component:
    return rx.el.div(
        rx.el.h2(
            "Selected ticket control surface",
            class_name=["text-lg font-semibold", TEXT_STRONG],
        ),
        rx.el.p(
            DashboardState.notice_message,
            class_name=["mt-2 text-sm leading-6", TEXT_BODY],
        ),
        rx.el.a(
            "Open WhatsApp notice",
            href=DashboardState.whatsapp_url,
            target="_blank",
            class_name=f"mt-3 inline-flex rounded-sm px-3 py-2 text-xs font-semibold {PRIMARY_BTN} {FOCUS}",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.select(
                    rx.el.option("Pre-Due"),
                    rx.el.option("Due Today"),
                    rx.el.option("Final Warning"),
                    value=DashboardState.notice_type,
                    on_change=DashboardState.set_notice_type,
                    class_name=[
                        f"w-full appearance-none rounded-sm border px-3 py-2 pr-9 text-sm {FOCUS}",
                        FIELD,
                    ],
                ),
                rx.icon(
                    "chevron-down",
                    class_name=[
                        "pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2",
                        TEXT_MUTED,
                    ],
                ),
                class_name="relative mt-4 w-48",
            ),
            rx.el.input(
                placeholder="Payment amount",
                default_value=DashboardState.payment_amount,
                on_change=DashboardState.set_payment_amount,
                class_name=[
                    f"mt-4 rounded-sm border px-3 py-2 text-sm {FOCUS}",
                    FIELD,
                ],
            ),
            rx.el.button(
                "Settle",
                on_click=DashboardState.update_ticket_status("Settled"),
                class_name=f"mt-4 rounded-sm px-3 py-2 text-xs font-semibold {PRIMARY_BTN} {FOCUS}",
            ),
            rx.el.button(
                "Extend 30 days",
                on_click=DashboardState.update_ticket_status("Extended"),
                class_name=[
                    f"mt-4 rounded-sm border px-3 py-2 text-xs font-semibold {FOCUS}",
                    GHOST_BTN,
                ],
            ),
            class_name="flex flex-wrap items-start gap-2",
        ),
        rx.el.button(
            "Mark Defaulted",
            on_click=DashboardState.update_ticket_status("Defaulted"),
            class_name=f"mt-3 rounded-sm bg-[#b95b3e] px-3 py-2 text-xs font-semibold text-white hover:bg-[#a24c31] {FOCUS}",
        ),
        ticket_detail_grid(),
        class_name=[
            "mt-5 rounded-sm border p-5",
            rx.color_mode_cond(
                "border-[#189b2b]/30 bg-white",
                "border-[#189b2b]/50 bg-[#202629]",
            ),
        ],
    )


def _liquidation_row(record: LoanRecord) -> rx.Component:
    return rx.el.tr(
        rx.el.td(
            record["ticket"],
            class_name=["px-3 py-3 font-['IBM_Plex_Mono']", ACCENT_TEXT],
        ),
        rx.el.td(
            record["item"], class_name=["px-3 py-3 font-medium", TEXT_STRONG]
        ),
        rx.el.td(
            f"P{record['principal']:,.2f}",
            class_name=["px-3 py-3 font-['IBM_Plex_Mono']", TEXT_BODY],
        ),
        rx.el.td(
            f"P{record['estimated_value']:,.2f}",
            class_name=["px-3 py-3 font-['IBM_Plex_Mono']", TEXT_BODY],
        ),
        rx.el.td(
            f"P{record['recommended_price']:,.2f}",
            class_name=["px-3 py-3 font-['IBM_Plex_Mono']", ACCENT_TEXT],
        ),
        rx.el.td(
            f"P{record['recommended_price'] - record['principal']:,.2f}",
            class_name=["px-3 py-3 font-['IBM_Plex_Mono']", POSITIVE_TEXT],
        ),
        rx.el.td(record["due_date"], class_name=["px-3 py-3", TEXT_BODY]),
        on_click=lambda: DashboardState.select_ticket(record["ticket"]),
        class_name=[
            "cursor-pointer border-b",
            BORDER_SOFT,
            ROW_HOVER,
        ],
    )


def liquidation_panel() -> rx.Component:
    return rx.el.div(
        rx.el.h1(
            "LIQUIDATION QUEUE",
            class_name=[
                "font-['IBM_Plex_Mono'] text-xs tracking-[0.2em]",
                ACCENT_TEXT,
            ],
        ),
        rx.el.p(
            "Explicit Defaulted records only. Recommended price = 80% of estimated market value when available.",
            class_name=["mt-2 text-sm", TEXT_SECONDARY],
        ),
        rx.el.input(
            placeholder="Search ticket or item",
            default_value=DashboardState.liquidation_search,
            on_change=DashboardState.set_liquidation_search.debounce(400),
            aria_label="Search liquidation queue",
            class_name=[
                f"mt-5 w-full max-w-xl rounded-sm border px-3 py-2 text-sm {FOCUS}",
                FIELD,
            ],
        ),
        rx.el.div(
            rx.el.table(
                rx.el.thead(
                    rx.el.tr(
                        _th("Ticket"),
                        _th("Item description"),
                        _th("Original loan"),
                        _th("Market value"),
                        _th("Recommended (80%)"),
                        _th("Margin"),
                        _th("Due date"),
                        class_name=["border-b", BORDER],
                    )
                ),
                rx.el.tbody(
                    rx.foreach(
                        DashboardState.liquidation_records, _liquidation_row
                    )
                ),
                class_name="table-auto min-w-[900px] w-full text-sm",
            ),
            class_name=["mt-5 overflow-x-auto rounded-sm border", SURFACE],
        ),
        rx.cond(
            DashboardState.selected_ticket != "", sale_form(), rx.fragment()
        ),
        class_name="w-full",
    )


def sale_form() -> rx.Component:
    return rx.el.div(
        rx.el.h2(
            "Sale confirmation",
            class_name=["text-lg font-semibold", TEXT_STRONG],
        ),
        rx.el.p(
            "Final revenue becomes realized profit after the original loan is recovered.",
            class_name=["mt-2 text-sm", TEXT_SECONDARY],
        ),
        rx.el.input(
            placeholder="Positive final cash revenue",
            default_value=DashboardState.sale_revenue,
            on_change=DashboardState.set_sale_revenue,
            aria_label="Final cash revenue",
            class_name=[
                f"mt-4 block rounded-sm border px-3 py-2 text-sm {FOCUS}",
                FIELD,
            ],
        ),
        rx.el.input(
            type="date",
            default_value=DashboardState.sale_date,
            on_change=DashboardState.set_sale_date,
            aria_label="Sale date",
            class_name=[
                f"mt-3 block rounded-sm border px-3 py-2 text-sm {FOCUS}",
                FIELD,
            ],
        ),
        rx.el.p(
            f"Calculated realized profit: P{DashboardState.selected_record['principal']:,.2f} principal is deducted from final revenue.",
            class_name=["mt-3 text-sm", ACCENT_TEXT],
        ),
        rx.el.label(
            rx.el.input(
                type="checkbox",
                checked=DashboardState.sale_confirmed,
                on_change=lambda _: DashboardState.toggle_sale_confirmation(),
                class_name="h-4 w-4 accent-[#189b2b]",
            ),
            " I confirm this sale write.",
            class_name=["mt-3 flex items-center gap-2 text-sm", TEXT_BODY],
        ),
        rx.el.button(
            "Commit sale",
            on_click=DashboardState.submit_sale,
            class_name=f"mt-4 rounded-sm px-3 py-2 text-xs font-semibold {PRIMARY_BTN} {FOCUS}",
        ),
        class_name=[
            "mt-5 rounded-sm border p-5",
            rx.color_mode_cond(
                "border-[#189b2b]/30 bg-white",
                "border-[#189b2b]/50 bg-[#202629]",
            ),
        ],
    )


def history_panel() -> rx.Component:
    return rx.el.div(
        rx.el.h1(
            "CUSTOMER HISTORY",
            class_name=[
                "font-['IBM_Plex_Mono'] text-xs tracking-[0.2em]",
                ACCENT_TEXT,
            ],
        ),
        rx.el.p(
            "Search by Omang / Passport No. or normalized mobile. Identity details remain hidden until a match is selected.",
            class_name=["mt-2 text-sm", TEXT_SECONDARY],
        ),
        rx.el.input(
            placeholder="Search stable identity or mobile",
            default_value=DashboardState.history_search,
            on_change=DashboardState.set_history_search.debounce(400),
            aria_label="Search customer history",
            class_name=[
                f"mt-5 w-full max-w-xl rounded-sm border px-3 py-2 text-sm {FOCUS}",
                FIELD,
            ],
        ),
        rx.el.div(
            rx.foreach(
                DashboardState.history_records,
                lambda record: rx.el.button(
                    record["customer"],
                    on_click=DashboardState.select_customer(record["omang"]),
                    class_name=[
                        f"mt-3 block w-full max-w-xl rounded-sm border px-3 py-2 text-left text-sm font-medium {FOCUS}",
                        SURFACE,
                        TEXT_STRONG,
                        ROW_HOVER,
                    ],
                ),
            ),
            class_name="mt-3",
        ),
        rx.cond(
            DashboardState.selected_customer_key != "",
            customer_dossier(),
            rx.el.p(
                "Select a matched customer to open the risk dossier.",
                class_name=["mt-6 text-sm", TEXT_MUTED],
            ),
        ),
        class_name="w-full",
    )


def customer_dossier() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            DashboardState.customer_risk,
            class_name=["text-xl font-semibold", ACCENT_TEXT],
        ),
        rx.el.p(
            DashboardState.customer_risk_reason,
            class_name=["mt-2 text-sm", TEXT_SECONDARY],
        ),
        rx.el.div(
            rx.foreach(
                DashboardState.selected_customer_records,
                lambda record: rx.el.div(
                    record["ticket"],
                    " · ",
                    record["status"],
                    " · ",
                    record["due_date"],
                    class_name=[
                        "border-b px-3 py-3 text-sm",
                        BORDER,
                        TEXT_BODY,
                    ],
                ),
            ),
            class_name=["mt-5 rounded-sm border", SURFACE],
        ),
        class_name=[
            "mt-5 rounded-sm border p-5",
            rx.color_mode_cond(
                "border-[#189b2b]/30 bg-white",
                "border-[#189b2b]/50 bg-[#202629]",
            ),
        ],
    )


def integration_strip() -> rx.Component:
    return rx.el.div(
        rx.el.span(
            "INTEGRATIONS",
            class_name=[
                "font-['IBM_Plex_Mono'] text-[10px] tracking-widest",
                ACCENT_TEXT,
            ],
        ),
        rx.el.span(
            DashboardState.sheets_health,
            class_name=["text-xs", POSITIVE_TEXT],
        ),
        rx.el.span(
            DashboardState.calendar_health,
            class_name=["text-xs", POSITIVE_TEXT],
        ),
        class_name=[
            "mb-4 flex flex-wrap items-center gap-3 rounded-sm border px-3 py-2",
            SURFACE,
        ],
        role="status",
        aria_live="polite",
    )


def calculator_metric(label: str, value: rx.Var) -> rx.Component:
    return rx.el.div(
        rx.el.p(
            label,
            class_name=[
                "text-[10px] uppercase tracking-wider",
                TEXT_MUTED,
            ],
        ),
        rx.el.p(
            f"P{value:,.2f}",
            class_name=[
                "mt-2 font-['IBM_Plex_Mono'] text-xl font-bold",
                TEXT_STRONG,
            ],
        ),
        class_name=["w-full border p-4", SURFACE],
    )


def repayment_equation(
    safe_loan: rx.Var, interest_amount: rx.Var, total: rx.Var
) -> rx.Component:
    return rx.el.div(
        rx.el.p(
            "30-DAY REPAYMENT EQUATION",
            class_name=[
                "font-['IBM_Plex_Mono'] text-[10px] tracking-[0.2em]",
                ACCENT_TEXT,
            ],
        ),
        rx.el.div(
            rx.el.div(
                rx.el.p(
                    "Max Loan Amount",
                    class_name=[
                        "text-[10px] uppercase tracking-wider",
                        TEXT_MUTED,
                    ],
                ),
                rx.el.p(
                    f"P{safe_loan:,.2f}",
                    class_name=[
                        "font-['IBM_Plex_Mono'] text-lg font-bold",
                        TEXT_STRONG,
                    ],
                ),
                class_name=["border px-4 py-3", INSET],
            ),
            rx.el.span(
                "+",
                class_name=[
                    "font-['IBM_Plex_Mono'] text-xl font-bold",
                    ACCENT_TEXT,
                ],
            ),
            rx.el.div(
                rx.el.p(
                    "30-Day Interest Amount",
                    class_name=[
                        "text-[10px] uppercase tracking-wider",
                        TEXT_MUTED,
                    ],
                ),
                rx.el.p(
                    f"P{interest_amount:,.2f}",
                    class_name=[
                        "font-['IBM_Plex_Mono'] text-lg font-bold",
                        TEXT_STRONG,
                    ],
                ),
                class_name=["border px-4 py-3", INSET],
            ),
            rx.el.span(
                "=",
                class_name=[
                    "font-['IBM_Plex_Mono'] text-xl font-bold",
                    ACCENT_TEXT,
                ],
            ),
            rx.el.div(
                rx.el.p(
                    "Total Due at 30 Days",
                    class_name="text-[10px] uppercase tracking-wider text-white/80",
                ),
                rx.el.p(
                    f"P{total:,.2f}",
                    class_name="font-['IBM_Plex_Mono'] text-lg font-bold text-white",
                ),
                class_name="bg-[#189b2b] px-4 py-3",
            ),
            class_name="mt-3 flex flex-wrap items-center gap-3",
        ),
        class_name=[
            "mt-5 border p-5",
            rx.color_mode_cond(
                "border-[#189b2b]/30 bg-white",
                "border-[#189b2b]/50 bg-[#202629]",
            ),
        ],
    )


def valuation_panel(
    category: str,
    set_value: rx.event.EventType,
    reset_value: rx.event.EventType,
) -> rx.Component:
    is_vehicle = category == "Vehicle"
    value = rx.cond(
        is_vehicle,
        DashboardState.vehicle_market_value,
        DashboardState.electronics_market_value,
    )
    error = rx.cond(
        is_vehicle,
        DashboardState.vehicle_value_error,
        DashboardState.electronics_value_error,
    )
    estimated = rx.cond(
        is_vehicle,
        DashboardState.vehicle_market_amount,
        DashboardState.electronics_market_amount,
    )
    safe_loan = rx.cond(
        is_vehicle,
        DashboardState.vehicle_safe_loan,
        DashboardState.electronics_safe_loan,
    )
    interest_amount = rx.cond(
        is_vehicle,
        DashboardState.vehicle_interest_amount,
        DashboardState.electronics_interest_amount,
    )
    repayment = rx.cond(
        is_vehicle,
        DashboardState.vehicle_repayment,
        DashboardState.electronics_repayment,
    )
    profit = rx.cond(
        is_vehicle,
        DashboardState.vehicle_default_profit,
        DashboardState.electronics_default_profit,
    )
    interest = rx.cond(is_vehicle, "15%", "30%")
    return rx.el.div(
        rx.el.p(
            "APPRAISAL WORKBENCH",
            class_name=[
                "font-['IBM_Plex_Mono'] text-xs tracking-[0.2em]",
                ACCENT_TEXT,
            ],
        ),
        rx.el.h1(
            f"{category} Valuation",
            class_name=["mt-2 text-2xl font-semibold", TEXT_STRONG],
        ),
        rx.el.p(
            "Second-hand market value in Botswana pula. Values remain local and are never written to Google.",
            class_name=["mt-2 mb-4 text-sm", TEXT_SECONDARY],
        ),
        integration_strip(),
        rx.el.div(
            rx.el.div(
                "40%",
                class_name="font-['IBM_Plex_Mono'] text-4xl font-bold text-white",
            ),
            rx.el.p(
                "MAXIMUM LTV BAND · SAFE LOAN POLICY",
                class_name="text-xs font-semibold tracking-wider text-white",
            ),
            class_name="mt-5 flex items-center gap-4 rounded-sm bg-[#189b2b] px-5 py-4",
        ),
        rx.el.label(
            "Second-hand market value (BWP)",
            class_name=["mt-5 block text-xs font-medium", TEXT_SECONDARY],
        ),
        rx.el.input(
            default_value=value,
            placeholder="0.00",
            input_mode="decimal",
            on_change=set_value,
            aria_label=f"{category} second-hand market value",
            class_name=[
                f"mt-2 w-full rounded-sm border px-3 py-3 font-['IBM_Plex_Mono'] {FOCUS}",
                FIELD,
            ],
        ),
        rx.cond(
            error != "",
            rx.el.p(
                error,
                class_name=["mt-2 text-sm", DANGER_TEXT],
                role="alert",
            ),
            rx.el.p(
                "Zero is a valid appraisal state.",
                class_name=["mt-2 text-xs", TEXT_MUTED],
            ),
        ),
        rx.el.div(
            calculator_metric("Estimated item value", estimated),
            calculator_metric(
                "Recommended loan amount · max loan (40% LTV)", safe_loan
            ),
            calculator_metric(
                f"Loan interest (amount in BWP) · {interest} monthly",
                interest_amount,
            ),
            calculator_metric("Total due at 30 days", repayment),
            calculator_metric("Projected default profit", profit),
            class_name="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3",
        ),
        repayment_equation(safe_loan, interest_amount, repayment),
        rx.el.div(
            rx.el.p(
                "FORMULA REFERENCE",
                class_name=[
                    "font-['IBM_Plex_Mono'] text-xs tracking-wider",
                    ACCENT_TEXT,
                ],
            ),
            rx.el.p(
                f"Max loan = estimated value × 0.40 · Loan interest = max loan × {interest} · Total due at 30 days = max loan + loan interest · Default profit = estimated value − max loan",
                class_name=["mt-2 text-xs leading-5", TEXT_SECONDARY],
            ),
            class_name=["mt-5 border p-4", SURFACE],
        ),
        rx.el.button(
            "Reset calculator",
            type="button",
            on_click=reset_value,
            class_name=[
                f"mt-4 rounded-sm border px-3 py-2 text-xs font-semibold {FOCUS}",
                rx.color_mode_cond(
                    "border-[#E5E7EB] bg-white text-[#334155] hover:bg-[#F1F5F9]",
                    "border-white/20 bg-transparent text-[#d6ddda] hover:bg-white/10",
                ),
            ],
        ),
        class_name="w-full",
    )


def scheduled_panel() -> rx.Component:
    return rx.el.div(
        integration_strip(), operations_panel(), class_name="w-full"
    )


REMINDER_COLUMNS: list[str] = [
    "Countdown Badge",
    "Ticket #",
    "Customer Name",
    "Contact #",
    "Issue Date",
    "Maturity Date",
    "Item Description",
    "Total Due (BWP)",
    "WhatsApp Action",
]

BADGE_BASE = "inline-flex w-fit items-center gap-1.5 whitespace-nowrap rounded-sm border px-2 py-1 text-[11px] font-semibold"

BADGE_GREEN = rx.color_mode_cond(
    "border-[#bbf7d0] bg-[#f0fdf4] text-[#15803d]",
    "border-[#57b38a]/40 bg-[#57b38a]/15 text-[#8bd4b0]",
)
BADGE_BLUE = rx.color_mode_cond(
    "border-[#bfdbfe] bg-[#eff6ff] text-[#1d4ed8]",
    "border-[#60a5fa]/40 bg-[#60a5fa]/15 text-[#bfdbfe]",
)
BADGE_ORANGE = rx.color_mode_cond(
    "border-[#fed7aa] bg-[#fff7ed] text-[#c2410c]",
    "border-[#fb923c]/40 bg-[#fb923c]/15 text-[#fed7aa]",
)
BADGE_RED = rx.color_mode_cond(
    "border-[#fecaca] bg-[#fef2f2] text-[#b91c1c]",
    "border-[#f87171]/40 bg-[#f87171]/15 text-[#fecaca]",
)
BADGE_DARK_RED = rx.color_mode_cond(
    "border-[#7f1d1d]/40 bg-[#7f1d1d] text-white",
    "border-[#7f1d1d] bg-[#7f1d1d] text-[#fee2e2]",
)


def _badge_classes(color: rx.Var) -> rx.Var:
    return rx.match(
        color,
        ("green", BADGE_GREEN),
        ("blue", BADGE_BLUE),
        ("orange", BADGE_ORANGE),
        ("red", BADGE_RED),
        ("dark-red", BADGE_DARK_RED),
        BADGE_GREEN,
    )


def _legend_chip(label: str, classes: rx.Var) -> rx.Component:
    return rx.el.span(label, class_name=[BADGE_BASE, classes])


def reminders_legend() -> rx.Component:
    return rx.el.div(
        rx.el.span(
            "URGENCY LEGEND",
            class_name=[
                "font-['IBM_Plex_Mono'] text-[10px] tracking-[0.18em]",
                TEXT_MUTED,
            ],
        ),
        _legend_chip("On Track · 8+ days", BADGE_GREEN),
        _legend_chip("Courtesy Stage · 7–4 days", BADGE_BLUE),
        _legend_chip("Pre-Due Stage · 3–1 days", BADGE_ORANGE),
        _legend_chip("Due Today · 0 days", BADGE_RED),
        _legend_chip("Overdue Stage", BADGE_DARK_RED),
        class_name=[
            "mt-5 flex flex-wrap items-center gap-2 rounded-sm border px-3 py-3",
            SURFACE,
        ],
    )


def _reminder_row(row: ReminderRow) -> rx.Component:
    return rx.el.tr(
        rx.el.td(
            rx.el.span(
                rx.icon("clock", class_name="h-3 w-3"),
                row["countdown_label"],
                class_name=[BADGE_BASE, _badge_classes(row["badge_color"])],
                aria_label=row["countdown_label"],
            ),
            class_name="whitespace-nowrap px-3 py-3",
        ),
        rx.el.td(row["ticket"], class_name=[CELL_MONO, ACCENT_TEXT]),
        rx.el.td(
            row["customer"],
            class_name=[CELL, "font-medium", TEXT_STRONG],
        ),
        rx.el.td(row["contact"], class_name=[CELL_MONO, TEXT_BODY]),
        rx.el.td(row["issue_date"], class_name=[CELL_MONO, TEXT_BODY]),
        rx.el.td(row["maturity_date"], class_name=[CELL_MONO, TEXT_STRONG]),
        rx.el.td(
            row["description"],
            class_name=["max-w-xs truncate px-3 py-3", TEXT_BODY],
        ),
        rx.el.td(
            f"P{row['total_due']:,.2f}",
            class_name=[CELL_MONO, TEXT_STRONG],
        ),
        rx.el.td(
            rx.cond(
                row["whatsapp_available"],
                rx.el.a(
                    rx.icon("message-circle", class_name="h-4 w-4"),
                    "Send WhatsApp Notice",
                    href=row["whatsapp_url"],
                    target="_blank",
                    rel="noopener noreferrer",
                    aria_label=f"Send WhatsApp notice for ticket {row['ticket']} — opens WhatsApp in a new tab",
                    class_name=f"inline-flex w-fit items-center gap-2 whitespace-nowrap rounded-sm px-3 py-2 text-xs font-semibold {PRIMARY_BTN} {FOCUS}",
                ),
                rx.el.span(
                    rx.icon("ban", class_name="h-4 w-4"),
                    "No valid contact",
                    aria_disabled="true",
                    title="This loan has no valid Botswana mobile number on record.",
                    class_name=[
                        "inline-flex w-fit cursor-not-allowed items-center gap-2 whitespace-nowrap rounded-sm border px-3 py-2 text-xs font-semibold",
                        INSET,
                        TEXT_MUTED,
                    ],
                ),
            ),
            class_name="whitespace-nowrap px-3 py-3",
        ),
        class_name=["border-b", BORDER_SOFT, ROW_HOVER],
    )


def reminders_panel() -> rx.Component:
    return rx.el.div(
        integration_strip(),
        rx.el.div(
            rx.el.div(
                rx.el.p(
                    "DEADLINE CONTROL",
                    class_name=[
                        "font-['IBM_Plex_Mono'] text-xs font-bold tracking-[0.22em]",
                        ACCENT_TEXT,
                    ],
                ),
                rx.el.h1(
                    "Reminders Queue",
                    class_name=[
                        "mt-2 text-2xl font-semibold tracking-tight",
                        TEXT_STRONG,
                    ],
                ),
                rx.el.p(
                    "Active and Extended loans with a valid maturity date, ordered by urgency — the most overdue first. Countdown is measured against today in Africa/Gaborone.",
                    class_name=["mt-2 max-w-3xl text-sm", TEXT_SECONDARY],
                ),
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.p(
                        "LIVE QUEUE",
                        class_name=[
                            "font-['IBM_Plex_Mono'] text-[10px] tracking-[0.18em]",
                            TEXT_MUTED,
                        ],
                    ),
                    rx.el.p(
                        DashboardState.reminder_queue_count.to_string(),
                        class_name=[
                            "font-['IBM_Plex_Mono'] text-2xl font-bold",
                            TEXT_STRONG,
                        ],
                    ),
                    class_name=["rounded-sm border px-4 py-3", INSET],
                    role="status",
                    aria_live="polite",
                ),
                rx.el.button(
                    rx.icon("refresh-cw", class_name="h-4 w-4"),
                    rx.cond(
                        DashboardState.is_loading,
                        "Refreshing…",
                        "Refresh Queue",
                    ),
                    on_click=DashboardState.refresh_sheets,
                    disabled=DashboardState.is_loading,
                    aria_label="Refresh reminders queue from Google Sheets",
                    class_name=f"flex items-center gap-2 rounded-sm px-3 py-2 text-xs font-semibold {PRIMARY_BTN} {FOCUS}",
                ),
                class_name="flex flex-wrap items-center gap-3",
            ),
            class_name=[
                "flex flex-col justify-between gap-5 border-b pb-6 lg:flex-row lg:items-end",
                BORDER,
            ],
        ),
        reminders_legend(),
        rx.cond(
            DashboardState.is_loading,
            rx.el.div(
                rx.foreach(
                    [1, 2, 3, 4, 5],
                    lambda _: rx.el.div(
                        class_name=[
                            "h-10 animate-pulse rounded-sm border",
                            INSET,
                        ],
                    ),
                ),
                class_name=[
                    "mt-5 flex flex-col gap-3 rounded-sm border p-4",
                    SURFACE,
                ],
            ),
            rx.cond(
                DashboardState.reminder_queue.length() > 0,
                rx.el.div(
                    rx.el.table(
                        rx.el.thead(
                            rx.el.tr(
                                rx.foreach(REMINDER_COLUMNS, _sticky_th),
                                class_name=["border-b", BORDER],
                            )
                        ),
                        rx.el.tbody(
                            rx.foreach(
                                DashboardState.reminder_queue, _reminder_row
                            )
                        ),
                        class_name="table-auto w-max min-w-full text-sm",
                    ),
                    class_name=[
                        "mt-5 max-h-[70vh] overflow-auto rounded-sm border",
                        SURFACE,
                    ],
                ),
                rx.el.div(
                    rx.icon(
                        "bell-off",
                        class_name=["h-6 w-6", TEXT_MUTED],
                    ),
                    rx.el.p(
                        "No active loans with a valid maturity date.",
                        class_name=[
                            "mt-3 text-sm font-semibold",
                            TEXT_STRONG,
                        ],
                    ),
                    rx.el.p(
                        "Refresh Sheets once Active or Extended tickets carry a resolvable maturity date to populate this queue.",
                        class_name=["mt-1 text-xs", TEXT_MUTED],
                    ),
                    class_name=[
                        "mt-5 flex flex-col items-center rounded-sm border px-6 py-12 text-center",
                        SURFACE,
                    ],
                ),
            ),
        ),
        class_name="w-full",
    )


def vehicle_panel() -> rx.Component:
    return valuation_panel(
        "Vehicle",
        DashboardState.set_vehicle_market_value,
        DashboardState.reset_vehicle_calculator,
    )


def electronics_panel() -> rx.Component:
    return valuation_panel(
        "Electronics",
        DashboardState.set_electronics_market_value,
        DashboardState.reset_electronics_calculator,
    )
