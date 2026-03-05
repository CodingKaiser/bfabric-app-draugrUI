"""
DraugrUI main application.

Defines the Dash app, layout, and all callbacks. Entry point when run directly.

Layout structure:
  - Banner (black bar with app title)
  - Header row (run name, B-Fabric Entity link, View Logs link)
  - Persistent DMX sidebar (always in DOM; hidden/shown per tab via callback)
  - Flat tab row: Draugr/DMX | Sushify | Documentation | Report a Bug

Callback responsibilities:
  - display_page       : validate token, fetch run data, populate stores
  - register_auth_callback : show/hide content based on auth state (framework)
  - update_dmx_dropdown / update_sushi_dropdown : populate order dropdowns
  - update_lane_display    : render lane cards from run data
  - toggle_modal / toggle_modal2 : open/close confirmation dialogs
  - execute_draugr_command : build and fire Draugr or Sushi SSH commands
  - toggle_submit_button / _2 : disable submit when no orders selected
  - toggle_sidebar_visibility : show sidebar on DMX+Docs tabs, hide elsewhere
  - goto_submission_tab       : "Go to Submission" button returns to DMX tab
"""

import base64
import os
import time

import dash_bootstrap_components as dbc
from bfabric_web_apps import (
    HOST,
    PORT,
    create_app,
    process_url_and_token,
    register_auth_callback,
)
from bfabric_web_apps.layouts.layouts import get_report_bug_tab
from dash import Input, Output, State, dcc, html
from dash import callback_context as ctx

from utils import draugr_utils as du
from utils.bfabric_utils import get_logger
from utils.components import (
    default_sidebar,
    documentation_content,
    lane_card,
    modal,
    modal2,
    sushi_sidebar,
)
from utils.run_data import fetch_run_entity_data

# ==================== (1) App ====================

app = create_app(title="DraugrUI")

# Load logo as base64
_logo_path = os.path.join(
    os.path.dirname(__file__), "assets", "K_draugr_2_HQ-04_inverted.png"
)
with open(_logo_path, "rb") as f:
    logo_base64 = base64.b64encode(f.read()).decode("utf-8")

# ==================== (2) Layout ====================

# The main content shown to authenticated users (alerts, tooltips, modals, store)
main_content = html.Div(
    [
        # Alerts
        dbc.Alert(
            "Demultiplexing has begun! Please close this window now, and see B-Fabric for further status updates and logs.",
            id="alert-fade",
            dismissable=True,
            is_open=False,
            color="success",
            style={"max-width": "50vw", "margin": "10px"},
        ),
        dbc.Alert(
            "Sushification has begun! Please close this window now, and see Sushi for further status updates and logs.",
            id="alert-fade-2",
            dismissable=True,
            is_open=False,
            color="success",
            style={"max-width": "50vw", "margin": "10px"},
        ),
        dbc.Alert(
            "Sushification has FAILED! Please try DMX again, and then try Sushi again.",
            id="alert-fade-2-fail",
            dismissable=True,
            is_open=False,
            color="danger",
            style={"max-width": "50vw", "margin": "10px"},
        ),
        dbc.Alert(
            "Your submission didn't go through, because you haven't selected any orders from the dropdown! Please select which orders you'd like to process and try again.",
            id="alert-fade-4",
            dismissable=True,
            is_open=False,
            color="danger",
            style={"max-width": "50vw", "margin": "10px"},
        ),
        # Tooltips (switch labels — target the ⓘ icon IDs)
        dbc.Tooltip(
            "Disable the demultiplexing Wizard. None of the samples are tested for "
            "barcode issues and the information from B-Fabric is taken as-is.",
            target="tip-wizard",
        ),
        dbc.Tooltip(
            "For single-index 10X samples, determines if we should run in multiome-mode "
            "(with CellRangerARC) or with the default program (CellRanger). "
            "Overrides B-Fabric-derived information.",
            target="tip-multiome",
        ),
        dbc.Tooltip("Will skip copying files to gstore.", target="tip-gstore"),
        dbc.Tooltip(
            "Skip post-demultiplexing processing steps.",
            target="tip-skip-postprocessing",
        ),
        dbc.Tooltip("Skip the demultiplexing step entirely.", target="tip-skip-demux"),
        # Tooltips (inputs — tooltip on the field itself)
        dbc.Tooltip(
            "Custom bcl2fastq flags wrapped in a string, arguments separated by '|'. "
            'E.g. "--barcode-mismatches 2|--minimum-trimmed-read-length"',
            target="bcl-input",
        ),
        dbc.Tooltip(
            "Custom cellranger mkfastq flags wrapped in a string, arguments separated by '|'. "
            'E.g. "--barcode-mismatches 2|--delete-undetermined"',
            target="cellranger-input",
        ),
        dbc.Tooltip(
            "Custom bases2fastq flags wrapped in a string, arguments separated by ';'. "
            'E.g. "--i1-cycles 8;--r2-cycles 40"',
            target="bases2fastq-input",
        ),
        # Tooltips on Submit button wrappers
        dbc.Tooltip(
            "Select at least one order from the dropdown above to enable submission.",
            target="submit-btn-wrapper",
            id="submit-tooltip-1",
        ),
        dbc.Tooltip(
            "Select at least one order from the dropdown above to enable submission.",
            target="submit-btn-wrapper-2",
            id="submit-tooltip-2",
        ),
        # Hidden div for command execution output
        html.Div(id="empty-div-1"),
        # Confirmation modals
        modal,
        modal2,
    ]
)

# Sidebar and Tab content definitions
_sidebar_style = {
    "border-right": "2px solid #d4d7d9",
    "height": "100%",
    "padding": "20px",
    "font-size": "20px",
}

# DMX sidebar content
dmx_sidebar = default_sidebar[:-1] + [
    html.Div(
        id="submit-btn-wrapper", children=dbc.Button("Submit", id="draugr-button")
    ),
]

# Tab content — sidebar is now inside DMX and Sushi tabs
tab_list = [
    dbc.Tab(
        dbc.Row(
            [
                dbc.Col(
                    html.Div(children=dmx_sidebar, style=_sidebar_style),
                    width=3,
                ),
                dbc.Col(
                    html.Div(
                        id="lane-display",
                        style={
                            "margin-top": "2vh",
                            "margin-left": "2vw",
                            "font-size": "20px",
                        },
                    ),
                    width=9,
                ),
            ],
            style={"margin-top": "0px", "min-height": "40vh"},
        ),
        label="Draugr / DMX",
        tab_id="dmx",
    ),
    dbc.Tab(
        dbc.Row(
            [
                dbc.Col(
                    html.Div(children=sushi_sidebar, style=_sidebar_style),
                    width=3,
                ),
                dbc.Col(
                    html.Div(
                        id="sushi-lane-display",
                        style={
                            "margin-top": "2vh",
                            "margin-left": "2vw",
                            "font-size": "20px",
                        },
                    ),
                    width=9,
                ),
            ],
            style={"margin-top": "0px", "min-height": "40vh"},
        ),
        label="Sushify",
        tab_id="sushify",
    ),
    dbc.Tab(
        dbc.Row(
            dbc.Col(
                html.Div(
                    children=documentation_content,
                    style={
                        "margin-top": "10px",
                        "font-size": "20px",
                        "padding-right": "40px",
                        "overflow-y": "scroll",
                        "max-height": "60vh",
                    },
                ),
                width=8,
            ),
            justify="center",
            style={"margin-top": "20px"},
        ),
        label="Documentation",
        tab_id="documentation",
    ),
    dbc.Tab(
        dbc.Row(
            dbc.Col(
                get_report_bug_tab(),
                width=8,
            ),
            justify="center",
            style={"margin-top": "20px"},
        ),
        label="Report a Bug",
        tab_id="report-bug",
    ),
]

# Build layout manually (replicates framework structure but with flat tabs)
app.layout = html.Div(
    children=[
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="token", storage_type="session"),
        dcc.Store(id="entity", storage_type="session"),
        dcc.Store(id="app_data", storage_type="session"),
        dcc.Store(id="token_data", storage_type="session"),
        dcc.Store(id="dynamic-link-store", storage_type="session"),
        dcc.Store(id="run_data", storage_type="session"),
        dbc.Container(
            children=[
                # Banner
                dbc.Row(
                    dbc.Col(
                        html.Div(
                            className="banner",
                            children=[
                                html.Div(
                                    children=[
                                        html.Img(
                                            src=f"data:image/png;base64,{logo_base64}",
                                            style={
                                                "height": "60px",
                                                "margin-left": "20px",
                                                "margin-right": "10px",
                                            },
                                        ),
                                        html.Span(
                                            "DraugrUI",
                                            style={
                                                "color": "#ffffff",
                                                "font-size": "40px",
                                                "vertical-align": "middle",
                                            },
                                        ),
                                    ],
                                    style={
                                        "background-color": "#000000",
                                        "border-radius": "10px",
                                        "display": "flex",
                                        "align-items": "center",
                                        "height": "80px",
                                    },
                                ),
                            ],
                            style={"position": "relative", "padding": "10px"},
                        ),
                    ),
                ),
                # Header row (page title + buttons)
                dbc.Row(
                    dbc.Col(
                        html.Div(
                            children=[
                                html.Div(
                                    id="page-title",
                                    children=[],
                                    style={
                                        "margin-left": "20px",
                                        "margin-top": "10px",
                                        "max-width": "calc(100% - 350px)",
                                    },
                                ),
                                html.Div(
                                    children=[
                                        html.Div(
                                            children=[
                                                html.A(
                                                    dbc.Button(
                                                        "B-Fabric Entity",
                                                        id="bfabric-entity-button",
                                                        color="secondary",
                                                        style={
                                                            "font-size": "18px",
                                                            "padding": "10px 20px",
                                                            "border-radius": "8px",
                                                            "margin-right": "10px",
                                                        },
                                                    ),
                                                    id="bfabric-entity-link",
                                                    href="#",
                                                    target="_blank",
                                                ),
                                                html.A(
                                                    dbc.Button(
                                                        "View Logs",
                                                        id="dynamic-link-button",
                                                        color="secondary",
                                                        style={
                                                            "font-size": "18px",
                                                            "padding": "10px 20px",
                                                            "border-radius": "8px",
                                                        },
                                                    ),
                                                    id="dynamic-link",
                                                    href="#",
                                                    target="_blank",
                                                ),
                                            ],
                                            style={
                                                "display": "flex",
                                                "align-items": "center",
                                                "margin-bottom": "8px",
                                            },
                                        ),
                                        html.Div(
                                            id="auth-display",
                                            children=[],
                                            style={
                                                "font-size": "14px",
                                                "text-align": "right",
                                                "color": "#333",
                                            },
                                        ),
                                    ],
                                    style={
                                        "position": "absolute",
                                        "right": "20px",
                                        "top": "10px",
                                        "display": "flex",
                                        "flex-direction": "column",
                                        "align-items": "flex-end",
                                    },
                                ),
                            ],
                            style={
                                "position": "relative",
                                "margin-top": "0px",
                                "min-height": "80px",
                                "border-bottom": "2px solid #d4d7d9",
                                "display": "flex",
                                "align-items": "center",
                                "justify-content": "space-between",
                                "padding-right": "20px",
                                "padding-top": "10px",
                                "padding-bottom": "10px",
                            },
                        ),
                    ),
                ),
                # Bug report alerts
                dbc.Row(
                    dbc.Col(
                        [
                            dbc.Alert(
                                "Your bug report has been submitted. Thanks for helping us improve!",
                                id="alert-fade-bug-success",
                                dismissable=True,
                                is_open=False,
                                color="info",
                                style={
                                    "max-width": "50vw",
                                    "margin-left": "10px",
                                    "margin-top": "10px",
                                },
                            ),
                            dbc.Alert(
                                "Failed to submit bug report! Please email the developers directly at the email below!",
                                id="alert-fade-bug-fail",
                                dismissable=True,
                                is_open=False,
                                color="danger",
                                style={
                                    "max-width": "50vw",
                                    "margin-left": "10px",
                                    "margin-top": "10px",
                                },
                            ),
                        ]
                    )
                ),
                # Main app area
                # Auth message container (shown when not authenticated)
                html.Div(
                    id="auth-message-container",
                    children=[],
                    style={"display": "none", "padding": "40px", "margin-top": "20px"},
                ),
                # Main content container (alerts, tooltips, modals, store - always in DOM)
                html.Div(
                    id="main-content-container",
                    children=main_content,
                ),
                # Tabs (shown/hidden together by auth callback) wrapped in loading
                dcc.Loading(
                    id="global-loading",
                    type="circle",
                    overlay_style={"filter": "blur(2px)"},
                    parent_style={"position": "relative"},
                    children=html.Div(
                        id="tabs-container",
                        children=[
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Tabs(tab_list, id="tabs", active_tab="dmx"),
                                        width=12,
                                    ),
                                ],
                                style={"margin-top": "0px", "min-height": "40vh"},
                            ),
                        ],
                    ),
                ),
            ],
            fluid=True,
            style={"width": "100vw"},
        ),
    ],
    style={"width": "100vw", "overflow-x": "hidden", "overflow-y": "scroll"},
)


# ==================== (3) Callbacks ====================

# --- Auth: URL → token/entity stores ---


@app.callback(
    [
        Output("token", "data"),
        Output("token_data", "data"),
        Output("entity", "data"),
        Output("app_data", "data"),
        Output("page-title", "children"),
        Output("session-details", "children"),
        Output("dynamic-link", "href"),
        Output("bfabric-entity-link", "href"),
        Output("run_data", "data"),
    ],
    [Input("url", "search")],
)
def display_page(url_params):
    """Validate token, fetch entity data, and populate stores."""
    (
        token,
        token_data,
        entity_data,
        app_data,
        page_title,
        session_details,
        job_link,
        entity_link,
    ) = process_url_and_token(url_params)

    # Fetch run-specific data (lanes, containers, server, datafolder) if authenticated
    run_data = None
    if (
        token_data
        and not token_data.get("access_denied")
        and token_data.get("is_elevated")
    ):
        run_data = fetch_run_entity_data(token_data)

    return (
        token,
        token_data,
        entity_data,
        app_data,
        page_title or " ",
        session_details or [],
        job_link or "#",
        entity_link or "#",
        run_data,
    )


# --- Auth routing: show/hide main content based on token state ---

register_auth_callback(app, main_content=main_content)


# --- Dropdown population from run data ---


@app.callback(
    Output("draugr-dropdown", "options"),
    [Input("run_data", "data")],
)
def update_dmx_dropdown(run_data):
    if not run_data:
        return []
    orders = run_data.get("containers", [])
    return [{"label": elt, "value": elt} for elt in orders]


@app.callback(
    Output("draugr-dropdown-2", "options"),
    [Input("run_data", "data")],
)
def update_sushi_dropdown(run_data):
    if not run_data:
        return []
    orders = run_data.get("containers", [])
    return [{"label": elt, "value": elt} for elt in orders]


# --- Lane card display ---


@app.callback(
    [Output("lane-display", "children"), Output("sushi-lane-display", "children")],
    [Input("run_data", "data")],
)
def update_lane_display(run_data):
    if not run_data or "lanes" not in run_data:
        return [], []

    lanes = run_data["lanes"]

    if len(lanes) != 8:
        container = dbc.Container(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                lane_card(lane_position=pos, container_ids=ids)
                                for pos, ids in lanes.items()
                            ]
                        )
                    ]
                )
            ]
        )
    else:
        container = dbc.Container(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                lane_card(lane_position=i, container_ids=lanes[str(i)])
                                for i in range(1, 5)
                            ]
                        ),
                        dbc.Col(
                            [
                                lane_card(lane_position=i, container_ids=lanes[str(i)])
                                for i in range(5, 9)
                            ]
                        ),
                    ]
                )
            ]
        )

    return container, container


# --- Modal toggles ---


@app.callback(
    Output("modal", "is_open"),
    [Input("draugr-button", "n_clicks"), Input("close", "n_clicks")],
    [State("modal", "is_open")],
)
def toggle_modal(n1, n2, is_open):
    if n1 or n2:
        return not is_open
    return is_open


@app.callback(
    Output("modal2", "is_open"),
    [Input("draugr-button-2", "n_clicks"), Input("close2", "n_clicks")],
    [State("modal2", "is_open")],
)
def toggle_modal2(n1, n2, is_open):
    if n1 or n2:
        return not is_open
    return is_open


# --- Command execution ---


@app.callback(
    [
        Output("empty-div-1", "children"),
        Output("alert-fade", "is_open"),
        Output("alert-fade-2", "is_open"),
        Output("alert-fade-2-fail", "is_open"),
        Output("alert-fade-4", "is_open"),
    ],
    [
        Input("close", "n_clicks"),
        Input("close2", "n_clicks"),
    ],
    [
        State("draugr-dropdown", "value"),
        State("gstore", "on"),
        State("skip-postprocessing", "on"),
        State("skip-demux", "on"),
        State("wizard", "on"),
        State("multiome", "on"),
        State("bcl-input", "value"),
        State("cellranger-input", "value"),
        State("bases2fastq-input", "value"),
        State("token_data", "data"),
        State("run_data", "data"),
        State("draugr-dropdown-2", "value"),
    ],
    prevent_initial_call=True,
)
def execute_draugr_command(
    n_clicks,
    n_clicks2,
    orders,
    gstore,
    skip_postprocessing,
    skip_demux,
    wizard,
    multiome,
    bcl_flags,
    cellranger_flags,
    bases2fastq_flags,
    token_data,
    run_data,
    orders2,
):

    if not token_data:
        return None, False, False, False, False

    L = get_logger(token_data)

    button_clicked = ctx.triggered_id

    if button_clicked == "close":
        if not orders:
            return None, False, False, False, True

        draugr_command = du.generate_draugr_command(
            server=run_data["server"],
            run_folder=run_data["datafolder"],
            order_list=orders,
            skip_gstore=gstore,
            skip_postprocessing=skip_postprocessing,
            skip_demux=skip_demux,
            disable_wizard=wizard,
            is_multiome=multiome,
            bcl_flags=bcl_flags,
            cellranger_flags=cellranger_flags,
            bases2fastq_flags=bases2fastq_flags,
        )

        os.system(draugr_command)

        L.log_operation(
            operation="execute",
            message="DMX execution",
            params={"system_call": draugr_command},
            flush_logs=True,
        )

        return None, True, False, False, False

    elif button_clicked == "close2":
        if not orders2:
            return None, False, False, False, True

        try:
            draugr_command1, draugr_command2 = du.generate_sushi_command(
                order_list=orders2, run_name=run_data["name"]
            )
        except Exception:
            draugr_command1, draugr_command2 = None, None

        if not draugr_command1:
            L.log_operation(
                "EXECUTE",
                "Sushification has FAILED! Please try DMX again, and then try Sushi again.",
                params=None,
                flush_logs=True,
            )
            return None, False, False, True, False

        os.system(draugr_command1)
        time.sleep(1)
        os.system(draugr_command2)

        L.log_operation(
            operation="execute",
            message="FASTQ execution",
            params={
                "generate_bash_script": draugr_command1,
                "execute_bash_script": draugr_command2,
            },
            flush_logs=True,
        )

        return None, False, True, False, False

    return None, False, False, False, False


# --- Disable Submit buttons and Tooltips when no orders selected ---


@app.callback(
    [Output("draugr-button", "disabled"), Output("submit-tooltip-1", "className")],
    Input("draugr-dropdown", "value"),
)
def toggle_submit_button(orders):
    is_disabled = not orders
    # Tooltip is hidden (d-none) when button is enabled (not disabled)
    return is_disabled, "" if is_disabled else "d-none"


@app.callback(
    [Output("draugr-button-2", "disabled"), Output("submit-tooltip-2", "className")],
    Input("draugr-dropdown-2", "value"),
)
def toggle_submit_button_2(orders):
    is_disabled = not orders
    # Tooltip is hidden (d-none) when button is enabled (not disabled)
    return is_disabled, "" if is_disabled else "d-none"


if __name__ == "__main__":
    app.run(debug=False, port=PORT, host=HOST)
