import reflex as rx

from app.components.dashboard_ui import (
    dashboard_panel,
    scheduled_panel,
    liquidation_panel,
    history_panel,
    reminders_panel,
    sidebar,
    vehicle_panel,
    electronics_panel,
)
from app.states.dashboard_state import DashboardState


def content() -> rx.Component:
    return rx.match(
        DashboardState.active_tab,
        ("dashboard", dashboard_panel()),
        ("ledger", scheduled_panel()),
        ("payments", scheduled_panel()),
        ("reminders", reminders_panel()),
        ("liquidation", liquidation_panel()),
        ("history", history_panel()),
        ("vehicles", vehicle_panel()),
        ("electronics", electronics_panel()),
        scheduled_panel(),
    )


def top_header() -> rx.Component:
    return rx.el.header(
        rx.el.div(
            rx.icon("landmark", class_name="h-4 w-4 shrink-0 text-[#189b2b]"),
            rx.el.p(
                "SETLHOA CASH SOLUTIONS · OPERATIONS WORKSPACE",
                class_name=[
                    "truncate font-['IBM_Plex_Mono'] text-[10px] font-semibold tracking-[0.18em]",
                    rx.color_mode_cond("text-[#475569]", "text-[#8f9a95]"),
                ],
            ),
            class_name="flex min-w-0 items-center gap-2",
        ),
        rx.el.div(
            rx.el.span(
                "Theme",
                class_name=[
                    "hidden text-xs font-medium sm:inline",
                    rx.color_mode_cond("text-[#64748B]", "text-[#8f9a95]"),
                ],
            ),
            rx.color_mode_cond(
                rx.icon("sun", class_name="h-4 w-4 text-[#189b2b]"),
                rx.icon("moon", class_name="h-4 w-4 text-[#189b2b]"),
            ),
            class_name="flex shrink-0 items-center gap-2",
        ),
        class_name=[
            "flex h-12 shrink-0 items-center justify-between gap-3 border-b px-4 sm:px-6 lg:px-10",
            rx.color_mode_cond(
                "border-[#E5E7EB] bg-white", "border-white/10 bg-[#202629]"
            ),
        ],
    )


def index() -> rx.Component:
    return rx.el.div(
        top_header(),
        rx.el.div(
            sidebar(),
            rx.el.main(
                content(),
                class_name=[
                    "min-w-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-10",
                    rx.color_mode_cond(
                        "bg-[#F8FAFC] text-[#334155]",
                        "bg-[#171a1c] text-[#d6ddda]",
                    ),
                ],
            ),
            class_name="flex min-h-0 flex-1 flex-col overflow-hidden sm:flex-row",
        ),
        class_name="flex h-dvh w-screen flex-col overflow-hidden font-['IBM_Plex_Sans']",
    )


app = rx.App(
    theme=rx.theme(appearance="light"),
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(
            rel="preconnect",
            href="https://fonts.gstatic.com",
            cross_origin="",
        ),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap",
            rel="stylesheet",
        ),
    ],
)
app.add_page(index, route="/")
