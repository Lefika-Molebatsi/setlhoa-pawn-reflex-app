import reflex as rx
import reflex_xy
from app.states.dashboard_state import DashboardState, FinancialMonthRow
from app.components.dashboard_ui import (
    SURFACE,
    INSET,
    BORDER,
    TEXT_STRONG,
    TEXT_SECONDARY,
    TEXT_MUTED,
    TEXT_BODY,
    ACCENT_TEXT,
    FIELD,
    metric_card,
    calculator_metric,
)


def financial_header(label: str, icon: str) -> rx.Component:
    return rx.el.th(
        rx.el.div(
            rx.icon(icon, class_name="h-3 w-3"),
            label,
            class_name="flex items-center gap-2",
        ),
        class_name=[
            "whitespace-nowrap px-4 py-3 text-left text-[10px] uppercase tracking-wider",
            TEXT_MUTED,
        ],
    )


def financial_row(row: FinancialMonthRow) -> rx.Component:
    return rx.el.tr(
        rx.el.td(
            row["month"], class_name=["px-4 py-4 font-semibold", TEXT_STRONG]
        ),
        rx.el.td(f"P{row['settlement']:,.2f}", class_name="px-4 py-4"),
        rx.el.td(f"P{row['extension']:,.2f}", class_name="px-4 py-4"),
        rx.el.td(f"P{row['liquidation']:,.2f}", class_name="px-4 py-4"),
        rx.el.td(
            f"P{row['total']:,.2f}",
            class_name=rx.cond(
                row["total"] < 0,
                "px-4 py-4 font-semibold text-red-500",
                "px-4 py-4 font-semibold text-[#189b2b]",
            ),
        ),
        key=row["month"],
        class_name=[
            "border-b font-['IBM_Plex_Mono'] text-xs even:bg-slate-500/5 hover:bg-[#189b2b]/5",
            BORDER,
            TEXT_BODY,
        ],
    )


def financial_trend_chart() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.icon(
                "chart-no-axes-combined", class_name="h-5 w-5 text-[#189b2b]"
            ),
            rx.el.h2(
                "Deployment vs realized profit",
                class_name=["text-lg font-semibold", TEXT_STRONG],
            ),
            class_name="flex items-center gap-2",
        ),
        rx.el.p(
            "All source months, oldest first · Original approved capital on issue date; realized profit on settlement, verified receipt or sale date. Hover to inspect BWP values. This chart never follows the table filter.",
            class_name=["mt-2 text-xs leading-5", TEXT_SECONDARY],
        ),
        rx.cond(
            DashboardState.financial_rows.length() > 0,
            rx.el.div(
                reflex_xy.chart(
                    reflex_xy.line(
                        "month",
                        "deployed",
                        name="Original approved capital (BWP)",
                        color="#64748b",
                        width=2.5,
                    ),
                    reflex_xy.scatter(
                        "month",
                        "deployed",
                        name="Capital points (BWP)",
                        color="#64748b",
                        size=6,
                    ),
                    reflex_xy.line(
                        "month",
                        "profit",
                        name="Realized profit (BWP)",
                        color="#189b2b",
                        width=2.5,
                    ),
                    reflex_xy.scatter(
                        "month",
                        "profit",
                        name="Profit points (BWP)",
                        color="#189b2b",
                        size=6,
                    ),
                    reflex_xy.x_axis(label="Source month · YYYY-MM"),
                    reflex_xy.y_axis(label="Botswana pula (BWP)"),
                    reflex_xy.tooltip(
                        title="Month {month}",
                        fields=["deployed", "profit"],
                        labels={
                            "deployed": "Original capital (BWP)",
                            "profit": "Realized profit (BWP)",
                        },
                        format={"deployed": ",.2f", "profit": ",.2f"},
                    ),
                    reflex_xy.legend(),
                    reflex_xy.modebar(False),
                    reflex_xy.interaction_config(navigation=False),
                    data=DashboardState.financial_trends,
                    height="360px",
                    class_name="w-full min-w-[300px] bg-white text-slate-700",
                ),
                class_name="mt-4 h-[360px] w-full shrink-0 overflow-x-auto",
            ),
            rx.el.div(
                rx.icon(
                    "chart-no-axes-column", class_name="h-6 w-6 text-[#189b2b]"
                ),
                rx.el.p(
                    "No dated financial activity yet",
                    class_name=["mt-3 text-sm font-semibold", TEXT_STRONG],
                ),
                rx.el.p(
                    "Dated issued loans, receipts, settlements or sales will populate the trend after the workspace refreshes.",
                    class_name=["mt-2 text-xs", TEXT_MUTED],
                ),
                class_name=[
                    "mt-4 flex min-h-48 flex-col items-center justify-center border p-6 text-center",
                    INSET,
                ],
            ),
        ),
        class_name=["mt-5 w-full min-w-0 border p-4 sm:p-5", SURFACE],
    )


def financial_breakdown() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.el.h2(
                    "Monthly profit breakdown",
                    class_name=["text-lg font-semibold", TEXT_STRONG],
                ),
                rx.el.p(
                    "Realized categories only · Recent months first · Zero-profit source months retained",
                    class_name=["mt-1 text-xs", TEXT_MUTED],
                ),
            ),
            rx.el.div(
                rx.el.label(
                    "Financial reporting month",
                    html_for="financial-month",
                    class_name=["mb-2 block text-xs", TEXT_MUTED],
                ),
                rx.el.div(
                    rx.el.select(
                        rx.el.option("ALL · All source months", value="ALL"),
                        rx.foreach(
                            DashboardState.financial_months,
                            lambda month: rx.el.option(month, value=month),
                        ),
                        id="financial-month",
                        value=DashboardState.financial_month,
                        on_change=DashboardState.choose_financial_month,
                        class_name=[
                            "w-full appearance-none border px-3 py-2 pr-9 text-sm outline-hidden focus:ring-2 focus:ring-[#189b2b]",
                            FIELD,
                        ],
                    ),
                    rx.icon(
                        "chevron-down",
                        class_name=[
                            "pointer-events-none absolute right-3 top-3 h-4 w-4",
                            TEXT_MUTED,
                        ],
                    ),
                    class_name="relative",
                ),
                class_name="w-full sm:w-64",
            ),
            class_name="flex flex-col justify-between gap-4 sm:flex-row sm:items-end",
        ),
        rx.el.p(
            "Independent filter: the executive dashboard month lens, cumulative profit and trend chart remain unchanged.",
            class_name=["mt-3 text-xs", TEXT_SECONDARY],
        ),
        rx.el.div(
            calculator_metric(
                "Settlement subtotal",
                DashboardState.financial_subtotals["settlement"],
            ),
            calculator_metric(
                "Verified extension subtotal",
                DashboardState.financial_subtotals["extension"],
            ),
            calculator_metric(
                "Liquidation net subtotal",
                DashboardState.financial_subtotals["liquidation"],
            ),
            calculator_metric(
                "Selected period total",
                DashboardState.financial_subtotals["total"],
            ),
            class_name="mt-4 grid w-full grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            financial_header("Month", "calendar-days"),
                            financial_header(
                                "Settled-loan profit (BWP)", "receipt"
                            ),
                            financial_header(
                                "Verified extensions (BWP)", "badge-check"
                            ),
                            financial_header(
                                "Liquidation net (BWP)", "package-check"
                            ),
                            financial_header("Total profit (BWP)", "sigma"),
                            class_name=["border-b", BORDER, INSET],
                        )
                    ),
                    rx.el.tbody(
                        rx.foreach(
                            DashboardState.financial_filtered_rows,
                            financial_row,
                        )
                    ),
                    class_name="table-auto w-full min-w-[850px]",
                ),
                class_name="overflow-x-auto",
            ),
            class_name=["mt-4 overflow-hidden border", BORDER],
        ),
        rx.cond(
            DashboardState.financial_filtered_rows.length() == 0,
            rx.el.p(
                "No source-dated activity for this reporting view. Select ALL to review available months.",
                class_name=["mt-4 text-sm", TEXT_MUTED],
            ),
            rx.fragment(),
        ),
        rx.el.p(
            "Settlement profit uses the saved settlement accounting, including retained overpayment and late fees. Extensions count only nonconflicting verified payment IDs once, on actual receipt date; unapplied excess is excluded. Sold tickets contribute sale revenue minus original principal on sale date, never settlement profit as well. Invalid dates are excluded from dated earnings; losses reduce totals.",
            class_name=["mt-4 text-xs leading-5", TEXT_SECONDARY],
        ),
        class_name=["mt-5 w-full border p-4 sm:p-5", SURFACE],
    )


def financial_panel() -> rx.Component:
    return rx.el.div(
        rx.el.header(
            rx.el.div(
                rx.el.p(
                    "FINANCIAL PERFORMANCE REPORT",
                    class_name=[
                        "font-['IBM_Plex_Mono'] text-xs font-semibold tracking-[0.2em]",
                        ACCENT_TEXT,
                    ],
                ),
                rx.el.h1(
                    "Financials",
                    class_name=[
                        "mt-2 text-2xl font-semibold tracking-tight",
                        TEXT_STRONG,
                    ],
                ),
                rx.el.p(
                    "Capital deployed, cash earned and near-term collections — distinct measures from the live operations book.",
                    class_name=["mt-2 text-sm", TEXT_SECONDARY],
                ),
            ),
            rx.el.span(
                rx.icon("lock-keyhole", class_name="h-3 w-3"),
                "Read-only report",
                class_name=[
                    "flex w-fit items-center gap-2 border px-3 py-2 text-xs",
                    BORDER,
                    ACCENT_TEXT,
                ],
            ),
            class_name=[
                "flex flex-col justify-between gap-4 border-b pb-5 sm:flex-row sm:items-end",
                BORDER,
            ],
        ),
        rx.el.p(
            f"Workspace snapshot: {DashboardState.last_refresh} · Uses existing refreshed data; no cash collection or worksheet writes.",
            class_name=["mt-3 text-xs", TEXT_MUTED],
        ),
        rx.el.div(
            metric_card(
                "Total Deployed Capital",
                DashboardState.financial_total_deployed,
                "Original approved principal of all source-dated issued loans across all months, once per loan. Includes settled and sold loans; extensions are not new deployment. Not an outstanding-balance measure.",
                "banknote",
            ),
            metric_card(
                "All-Months Cumulative Profit",
                DashboardState.financial_cumulative_profit,
                "All monthly settlement profit + verified extension interest + liquidation net profit, including losses. Always all months; excludes recovered principal and forecast inflows.",
                "trending-up",
            ),
            metric_card(
                "Expected Inflows · Next 30 Days",
                DashboardState.financial_expected_inflows,
                "FORECAST, not realized profit: current total due once per unsettled, unsold Active/Extended loan due today through day 30 inclusive, Botswana time. Includes principal; excludes overdue and invalid due dates.",
                "calendar-clock",
            ),
            class_name="mt-5 grid w-full grid-cols-1 gap-3 lg:grid-cols-3",
        ),
        rx.el.p(
            f"Forecast window · {DashboardState.financial_forecast_window}",
            class_name=["mt-2 font-['IBM_Plex_Mono'] text-xs", TEXT_MUTED],
        ),
        financial_trend_chart(),
        financial_breakdown(),
        class_name="w-full min-w-0",
    )
