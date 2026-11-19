"""
DraugrUI main application.

Defines the Dash app, layout, and all callbacks. Entry point when run directly.

The layout is the library's app shell (`get_static_layout`): dark app-name bar,
notification banner stack, entity row, and a horizontal tab bar with Main,
Documentation and Report a Bug. The app only supplies the Main tab's content —
three sub-tabs: Draugr/DMX and Registration, each pairing an options sidebar with the
run's lanes or orders, and Queue, the draugr queue of the run's server. The shell's tab
bar has no slot for a further app tab, so the workflows are sub-tabs of Main
rather than tabs of the shell.

Authentication is the library's too: `register_url_token_callback` exchanges the
launch token and fills the stores and header links, and `register_auth_callback`
gates the content on an elevated user — reading the run's lanes and launching a
demultiplexing both need B-Fabric web service access.

draugr runs are queued with draugr-queue on the run's instrument server rather
than started directly, one at a time per server; see utils/draugr_queue.py.

Callback responsibilities:
  - register_url_token_callback : exchange the launch token, populate stores (library)
  - register_auth_callback      : show/hide content based on auth state (library)
  - handle_bug_report           : submit a bug report (library)
  - load_run_data               : traverse the run's lanes/orders once per session
  - update_dmx_dropdown         : populate the DMX order dropdown
  - update_lane_display         : render lane cards from run data
  - update_registration_status  : per-order BF registration status, Registration dropdown
  - update_after_dropdown       : the server's queued/running jobs, for Run after
  - toggle_modal / toggle_modal2 : open/close confirmation dialogs
  - execute_draugr_command      : queue a Draugr run, or fire the BF registration SSH commands
  - toggle_queue_refresh / refresh_queue : the Queue tab's live job list
  - toggle_queue_action_modal / run_queue_action : remove a queued job, stop the running one, clear or re-queue a lost one
  - show_log                    : tail of a job's console output
  - toggle_submit_button / _2   : disable submit when no orders selected
  - reset_form_state            : reset switches/inputs on every page load
"""

import os
import time
import tomllib

import dash_bootstrap_components as dbc
from bfabric_web_apps import (
    DEBUG,
    HOST,
    PORT,
    create_app,
    get_static_layout,
    make_banner,
    register_auth_callback,
    register_url_token_callback,
    submit_bug_report,
)
from dash import ALL, Input, Output, State, dcc, html, no_update
from dash import callback_context as ctx

from utils import draugr_queue, registration_status
from utils import draugr_utils as du
from utils.bfabric_utils import as_token_data, get_logger
from utils.components import (
    default_sidebar,
    documentation_content,
    lane_card,
    log_modal,
    modal,
    modal2,
    queue_action_modal,
    queue_pane,
    queue_view,
    registration_sidebar,
    registration_status_table,
)
from utils.run_data import fetch_run_entity_data

# Load version from pyproject.toml
with open("pyproject.toml", "rb") as f:
    app_version = tomllib.load(f).get("project", {}).get("version", "unknown")

# How many history events the Queue tab reads to list the jobs that have ended.
QUEUE_HISTORY_EVENTS = 500

# ==================== (1) App ====================

app = create_app(title="DraugrUI")
# Module-level attribute so gunicorn can be pointed at "index:server" — it takes
# module:attribute and cannot resolve a dotted path like "index:app.server".
server = app.server

# ==================== (2) Layout ====================


def _lanes_loading(text="Querying B-Fabric for the run's lanes…"):
    """Shown in place of a pane's content until the run comes back from B-Fabric."""
    return html.Div(
        [
            dbc.Spinner(size="sm", spinner_style={"marginRight": "8px"}),
            html.Span(text, className="bf-muted"),
        ],
        style={"display": "flex", "alignItems": "center", "padding": "12px 0"},
    )


def _work_pane(sidebar, display_id, loading_text):
    """An options sidebar beside the run's lanes or orders — the shape both work sub-tabs share."""
    return html.Div(
        className="bf-row bf-gap-16",
        style={"paddingTop": "12px"},
        children=[
            html.Div(children=sidebar, style={"width": "320px", "flexShrink": 0}),
            # Starts on the spinner: Dash holds update_lane_display back until
            # load_run_data has answered, so nothing else would fill the pane
            # while B-Fabric is being queried.
            html.Div(id=display_id, className="bf-fill", children=_lanes_loading(loading_text)),
        ],
    )


# The Main tab's content, injected by register_auth_callback once the user is
# authenticated.
main_content = html.Div(
    [
        dcc.Store(id="run_data", storage_type="session"),
        # Bumped after a submission or a queue action, so the queue and the
        # BF registration status refresh straight away instead of on their timers.
        dcc.Store(id="queue-version", data=0),
        dcc.Store(id="registration-version", data=0),
        # Tooltips (switch labels — target the ⓘ icon IDs)
        dbc.Tooltip(
            "Disable the demultiplexing Wizard. None of the samples are tested for "
            "barcode issues and the information from B-Fabric is taken as-is.",
            target="tip-disable-wizard",
        ),
        dbc.Tooltip(
            "Disable generation of the RawQC report.",
            target="tip-skip-raw-qc",
        ),
        dbc.Tooltip("Will skip copying files to gstore.", target="tip-gstore"),
        dbc.Tooltip(
            "Skip post-demultiplexing processing steps.",
            target="tip-skip-postprocessing",
        ),
        dbc.Tooltip("Skip the demultiplexing step entirely.", target="tip-skip-demux"),
        dbc.Tooltip(
            "Optional. Jobs on this run's server that must succeed first: the new job runs "
            "draugr only if each of them succeeded.",
            target="tip-after",
        ),
        # Tooltips (inputs — tooltip on the field itself)
        dbc.Tooltip(
            "Element/Aviti only. Custom bases2fastq flags, arguments separated by ';'. "
            'E.g. "--i1-cycles 8;--r2-cycles 40". Do not include the '
            'quotation marks when specifying this option.',
            target="bases2fastq-input",
        ),
        dbc.Tooltip(
            "Illumina only. Custom bclconvert flags, arguments separated by ';'. "
            'E.g. "--tiles s_1_2201+s_1_2202;--num-unknown-barcodes-reported 20". '
            "Do not put --use-bases-mask or --barcode-mismatches here — bcl-convert has no such "
            "options and Draugr will reject the run; use the two fields below instead.",
            target="bclconvert-input",
        ),
        dbc.Tooltip(
            "Illumina only. Overrides the computed bases mask. Give exactly one token per read "
            'position, in run order, e.g. "y36n*,I8n*,I8n*,y150n*" or "Y36N*;I8N*;I8N*;Y150N*". '
            "If the token count doesn't match the run, Draugr logs a warning and silently falls "
            "back to the computed mask — check the log.",
            target="bases-mask-input",
        ),
        dbc.Tooltip(
            "Illumina only. Overrides Draugr's Hamming-distance-derived barcode mismatch count. "
            'Leave on "Auto" unless you need to force a specific value.',
            target="tip-barcode-mismatches",
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
        # Confirmation modals
        modal,
        modal2,
        queue_action_modal,
        log_modal,
        dbc.Tabs(
            [
                dbc.Tab(
                    _work_pane(default_sidebar, "lane-display", "Querying B-Fabric for the run's lanes…"),
                    label="Draugr / DMX",
                    tab_id="dmx",
                ),
                dbc.Tab(
                    _work_pane(
                        registration_sidebar,
                        "registration-status-display",
                        "Querying B-Fabric for the orders' BF registration status…",
                    ),
                    label="Registration",
                    tab_id="registration",
                ),
                dbc.Tab(queue_pane, label="Queue", tab_id="queue"),
            ],
            id="work-tabs",
            active_tab="dmx",
        ),
    ]
)

# The shell takes a placeholder for the main content; the real content is handed
# to register_auth_callback, which injects it once the user is authenticated.
app.layout = get_static_layout(
    f"DraugrUI v{app_version}",
    html.Div(),
    documentation_content,
    layout_config={"bug": True},
)


# ==================== (3) Callbacks ====================

# --- Auth: URL → token/entity stores, and content gating ---

register_url_token_callback(app)

# Both reading the run's lanes and launching a demultiplexing go through the
# B-Fabric web service, so a non-elevated user cannot do anything useful here.
register_auth_callback(app, main_content=main_content, require_elevated=True)


# --- Bug reports ---


@app.callback(
    [
        Output("alert-fade-bug-success", "is_open"),
        Output("alert-fade-bug-fail", "is_open"),
    ],
    [Input("submit-bug-report", "n_clicks")],
    [
        State("bug-description", "value"),
        State("token_data", "data"),
        State("entity", "data"),
    ],
    prevent_initial_call=True,
)
def handle_bug_report(n_clicks, bug_description, token_data, entity_data):
    return submit_bug_report(n_clicks, bug_description, token_data, entity_data)


# --- Run data: lanes, orders, server and data folder of the launching run ---


@app.callback(
    Output("run_data", "data"),
    [Input("token_data", "data")],
)
def load_run_data(token_data):
    """Traverse run → rununit → lane → sample → container for the launching run."""
    # The error path is a plain dict rather than a token context, and a
    # non-elevated user has no web service access to traverse with.
    if not token_data or (isinstance(token_data, dict) and token_data.get("access_denied")):
        return None

    if not as_token_data(token_data).is_employee:
        return None

    # A failed fetch stores {} rather than None: None is what update_lane_display
    # reads as "still loading", and would leave the spinner up for good.
    try:
        return fetch_run_entity_data(token_data) or {}
    except Exception as e:  # noqa: BLE001 — any B-Fabric/OAuth failure, see below
        # An expired OAuth session raises here. Leaving the dropdowns empty is
        # better than failing the callback and leaving the page half-rendered.
        print(f"Error fetching run data: {e}")
        return {}


def _order_names(run_data):
    """Order id -> name, from the lanes' "<id> <name>" entries."""
    names = {}
    for entries in run_data.get("lanes", {}).values():
        for entry in entries:
            order_id, _, name = str(entry).partition(" ")
            names[order_id] = name
    return names


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


# --- Lane card display ---


@app.callback(
    Output("lane-display", "children"),
    [Input("run_data", "data"), Input("draugr-dropdown", "value")],
)
def update_lane_display(run_data, selected_orders):
    if run_data is None:
        return _lanes_loading()
    if "lanes" not in run_data:
        return []

    lanes = run_data["lanes"]
    selected_set = {str(s) for s in (selected_orders or [])}

    def make_lane_card(pos, ids):
        # ids is a list of strings like "12345 OrderName"
        highlight = any(str(order_str).split(" ")[0] in selected_set for order_str in ids)
        return lane_card(lane_position=pos, container_ids=ids, highlight=highlight)

    if len(lanes) != 8:
        return html.Div(
            [make_lane_card(pos, ids) for pos, ids in lanes.items()],
        )
    return html.Div(
        className="bf-row bf-gap-16",
        children=[
            html.Div([make_lane_card(i, lanes[str(i)]) for i in range(1, 5)]),
            html.Div([make_lane_card(i, lanes[str(i)]) for i in range(5, 9)]),
        ],
    )


# --- BF registration status ---


@app.callback(
    [
        Output("registration-status-display", "children"),
        Output("draugr-dropdown-2", "options"),
        Output("draugr-dropdown-2", "value"),
    ],
    [
        Input("run_data", "data"),
        Input("registration-version", "data"),
        Input("work-tabs", "active_tab"),
    ],
    State("token_data", "data"),
)
def update_registration_status(run_data, _version, active_tab, token_data):
    """
    Each order's BF registration status, and the Registration dropdown labelled with it.

    Statuses change as draugr runs finish, so they are re-read whenever the tab
    is opened. The outstanding (Ready) orders are only pre-selected on page load
    and after a submission, so opening the tab keeps the user's own selection.
    """
    if not run_data or not token_data:
        return [], [], None
    switched_tab = ctx.triggered_id == "work-tabs"
    if switched_tab and active_tab != "registration":
        return no_update, no_update, no_update

    orders = run_data.get("containers", [])
    try:
        queue_state = draugr_queue.status(run_data["server"], history=0)
    except draugr_queue.QueueError:
        # Without the queue only the Demultiplexing status is missing.
        queue_state = None
    try:
        rows = registration_status.order_statuses(
            token_data, run_data["name"], run_data["datafolder"], orders, queue_state
        )
    except Exception as e:  # noqa: BLE001 — any B-Fabric/OAuth failure, see below
        # An expired OAuth session raises here; the orders can still be registered.
        return (
            make_banner(f"Could not load the BF registration status: {e}", "error"),
            [{"label": o, "value": str(o)} for o in orders],
            no_update,
        )

    names = _order_names(run_data)
    base_url = str(as_token_data(token_data).base_url).rstrip("/")
    options = [
        {"label": f"{r['order']} {names.get(r['order'], '')} — {r['status']}", "value": r["order"]}
        for r in rows
    ]
    ready = [r["order"] for r in rows if r["status"] == registration_status.READY]
    return (
        registration_status_table(rows, names, lambda i: f"{base_url}/dataset/show.html?id={i}"),
        options,
        no_update if switched_tab else ready,
    )


# --- Modal toggles ---


@app.callback(
    [Output("modal", "is_open"), Output("modal-body", "children")],
    [Input("draugr-button", "n_clicks"), Input("close", "n_clicks")],
    [State("modal", "is_open"), State("run_data", "data")],
)
def toggle_modal(n1, n2, is_open, run_data):
    if not (n1 or n2):
        return is_open, no_update
    if is_open:
        return False, no_update

    # Warn about anything already queued for this run, so it can be removed first.
    # Not a block: the new job would only start after them anyway.
    if not run_data or not run_data.get("server"):
        # Submitting will report the missing run data itself.
        return True, "Are you sure you're ready to demux?"
    try:
        state = draugr_queue.status(run_data["server"], history=0)
        active = draugr_queue.active_for_run(state, run_data["datafolder"])
    except draugr_queue.QueueError:
        # Submitting will report the problem itself.
        active = []
    if not active:
        return True, "Are you sure you're ready to demux?"
    return True, [
        html.P("This run already has draugr jobs in the queue:"),
        html.Ul([
            html.Li(
                f"Job {job['tsp_id']}, {job['state']}, orders "
                f"{', '.join(job['orders'] or ['all'])} (submitted by {job.get('submitter') or 'unknown'})"
            )
            for job in active
        ]),
        html.P(
            "A new submission will wait until they have finished. Remove queued ones on the "
            "Queue tab first if they are no longer wanted."
        ),
    ]


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


def _banner(message, severity):
    """A notification banner that stays up until the user dismisses it.

    Uses make_banner's addressable form: its "×" is the dbc.Alert's own. The
    one-off form's "×" drives the library's _dismiss_banner callback, which also
    fires when the banner is inserted and so clears it the moment it appears.
    """
    return make_banner(message, severity, id="draugr-banner")


@app.callback(
    [
        Output("bf-notification", "children"),
        Output("work-tabs", "active_tab"),
        Output("queue-version", "data"),
        Output("registration-version", "data"),
        Output("after-dropdown", "value"),
    ],
    [
        Input("close", "n_clicks"),
        Input("close2", "n_clicks"),
    ],
    [
        State("draugr-dropdown", "value"),
        State("after-dropdown", "value"),
        State("gstore", "value"),
        State("skip-postprocessing", "value"),
        State("skip-demux", "value"),
        State("disable-wizard", "value"),
        State("skip-raw-qc", "value"),
        State("bases2fastq-input", "value"),
        State("bclconvert-input", "value"),
        State("bases-mask-input", "value"),
        State("barcode-mismatches-input", "value"),
        State("token_data", "data"),
        State("run_data", "data"),
        State("draugr-dropdown-2", "value"),
        State("queue-version", "data"),
        State("registration-version", "data"),
    ],
    prevent_initial_call=True,
    # draugr-queue queues the same run as often as it is asked to, so a double
    # click on Yes! must not get through as a second submission.
    running=[(Output("close", "disabled"), True, False), (Output("close2", "disabled"), True, False)],
)
def execute_draugr_command(
    n_clicks,
    n_clicks2,
    orders,
    after,
    gstore,
    skip_postprocessing,
    skip_demux,
    disable_wizard,
    skip_raw_qc,
    bases2fastq_flags,
    bclconvert_flags,
    bases_mask,
    barcode_mismatches,
    token_data,
    run_data,
    orders2,
    queue_version,
    registration_version,
):

    button_clicked = ctx.triggered_id

    # prevent_initial_call does not cover the Yes! buttons being inserted by the
    # auth router, which fires this with n_clicks=0 on every page load. Only a
    # real click may launch anything or post a banner.
    if not {"close": n_clicks, "close2": n_clicks2}.get(button_clicked):
        return no_update

    if not token_data:
        return [], no_update, no_update, no_update, no_update

    L = get_logger(token_data)
    submitter = as_token_data(token_data).subject

    no_orders = _banner(
        "Your submission didn't go through, because you haven't selected any orders "
        "from the dropdown! Please select which orders you'd like to process and try again.",
        "error",
    )

    if button_clicked == "close":
        if not orders:
            return no_orders, no_update, no_update, no_update, no_update

        server_name = run_data["server"]
        draugr_args = du.build_draugr_args(
            order_list=orders,
            skip_gstore=gstore,
            skip_postprocessing=skip_postprocessing,
            skip_demux=skip_demux,
            disable_wizard=disable_wizard,
            skip_raw_qc=skip_raw_qc,
            bases2fastq_flags=bases2fastq_flags,
            bclconvert_flags=bclconvert_flags,
            bases_mask=bases_mask,
            barcode_mismatches=barcode_mismatches,
        )

        try:
            tsp_id = draugr_queue.submit(
                server=server_name,
                run_folder=f"{draugr_queue.DATA_DIR}/{run_data['datafolder']}",
                draugr_args=draugr_args,
                submitter=submitter,
                after=after or [],
            )
        except draugr_queue.QueueError as e:
            return (
                _banner(f"Demultiplexing could not be queued: {e}", "error"),
                no_update,
                no_update,
                no_update,
                no_update,
            )

        # The key identifies the job for good; the tsp id restarts with the server.
        # A job can already have finished (e.g. draugr rejected its arguments),
        # so look it up among all the server's jobs, not only the active ones.
        key, ahead, ours = None, None, None
        try:
            state = draugr_queue.status(server_name, history=0)
            ours = next((job for job in state["jobs"] if job["tsp_id"] == tsp_id), None)
            key = ours["key"] if ours else None
            ahead = len([job for job in draugr_queue.active_jobs(state) if job["tsp_id"] < tsp_id])
        except draugr_queue.QueueError:
            pass

        L.log_operation(
            operation="execute",
            message="DMX queued",
            params={
                "tsp_id": tsp_id,
                "key": key,
                "server": server_name,
                "after": after or [],
                "draugr_args": draugr_args,
            },
            flush_logs=True,
        )

        if ours and ours["state"] == "finished":
            outcome = draugr_queue.EXIT_CODES.get(ours.get("exit_code"), f"exit {ours.get('exit_code')}")
            when = f"It has already ended: {outcome}."
        elif ahead is None:
            when = "See the Queue tab for its place in the queue."
        elif ahead:
            when = f"There are {ahead} job(s) ahead of it on that server."
        else:
            when = "Nothing is ahead of it on that server, so it starts right away."
        return (
            _banner(
                f"Demultiplexing queued as job {tsp_id} on {server_name}. {when} "
                "Follow it on the Queue tab, and see B-Fabric for status updates and logs.",
                "info",
            ),
            "queue",
            (queue_version or 0) + 1,
            no_update,
            None,
        )

    elif button_clicked == "close2":
        if not orders2:
            return no_orders, no_update, no_update, no_update, no_update

        # The dropdown's value comes from the browser and ends up in a shell
        # command, so accept only this run's own orders.
        run_orders = {str(o) for o in (run_data or {}).get("containers", [])}
        if not {str(o) for o in orders2} <= run_orders:
            return (
                _banner("BF registration refused: some selected orders are not in this run.", "error"),
                no_update,
                no_update,
                no_update,
                no_update,
            )

        try:
            draugr_command1, draugr_command2 = du.generate_registration_command(
                order_list=orders2, run_name=run_data["name"]
            )
        except (KeyError, OSError, ValueError):
            # No run name in run_data, a non-numeric order id, or the ssh existence check could not run.
            draugr_command1, draugr_command2 = None, None

        if not draugr_command1 or not draugr_command2:
            L.log_operation(
                "EXECUTE",
                "BF registration has FAILED! Please try DMX again, and then try registering again.",
                params=None,
                flush_logs=True,
            )
            return (
                _banner(
                    "BF registration has FAILED! Please try DMX again, and then try registering again.",
                    "error",
                ),
                no_update,
                no_update,
                no_update,
                no_update,
            )

        if os.system(draugr_command1) != 0:
            L.log_operation(
                "EXECUTE",
                "BF registration has FAILED: could not collect the orders' registration commands.",
                params={"generate_bash_script": draugr_command1},
                flush_logs=True,
            )
            return (
                _banner(
                    "BF registration has FAILED: could not collect the orders' registration commands.",
                    "error",
                ),
                no_update,
                no_update,
                no_update,
                no_update,
            )
        time.sleep(1)
        os.system(draugr_command2)

        L.log_operation(
            operation="execute",
            message="BF registration submitted",
            params={
                "generate_bash_script": draugr_command1,
                "execute_bash_script": draugr_command2,
            },
            flush_logs=True,
        )

        try:
            registration_status.record_submission(run_data["name"], orders2, submitter)
        except OSError as e:
            # The BF registration itself is underway, but these orders will not show as
            # Submitted, so warn instead of letting them look Ready for a second submission.
            print(f"Could not record the BF registration submission: {e}")
            return (
                _banner(
                    "BF registration has begun, but it could not be recorded here, so these orders "
                    "may still show as Ready. Do not submit them again; see B-Fabric for progress.",
                    "warning",
                ),
                no_update,
                no_update,
                no_update,
                no_update,
            )

        return (
            _banner(
                "BF registration has begun! Please close this window now, and see B-Fabric for "
                "further status updates and logs.",
                "info",
            ),
            no_update,
            no_update,
            (registration_version or 0) + 1,
            no_update,
        )

    return [], no_update, no_update, no_update, no_update


# --- Queue ---


def _job_label(job):
    orders = ", ".join(job["orders"] or ["all"])
    return f"job {job['tsp_id']} ({job['run']}, orders {orders})"


@app.callback(
    Output("after-dropdown", "options"),
    [
        Input("run_data", "data"),
        Input("queue-version", "data"),
        Input("work-tabs", "active_tab"),
    ],
)
def update_after_dropdown(run_data, _version, active_tab):
    """The jobs queued or running on the run's server, which a new job can be chained after."""
    if not run_data or not run_data.get("server"):
        return []
    if ctx.triggered_id == "work-tabs" and active_tab != "dmx":
        return no_update
    try:
        state = draugr_queue.status(run_data["server"], history=0)
    except draugr_queue.QueueError:
        return []
    return [
        {"label": f"{_job_label(job)}, {job['state']}", "value": job["tsp_id"]}
        for job in draugr_queue.active_jobs(state)
    ]


@app.callback(Output("queue-interval", "disabled"), Input("work-tabs", "active_tab"))
def toggle_queue_refresh(active_tab):
    """Only poll the server while the Queue tab is open."""
    return active_tab != "queue"


@app.callback(
    Output("queue-display", "children"),
    [
        Input("queue-interval", "n_intervals"),
        Input("work-tabs", "active_tab"),
        Input("queue-version", "data"),
    ],
    State("run_data", "data"),
)
def refresh_queue(_n_intervals, active_tab, _version, run_data):
    if active_tab != "queue":
        return no_update
    if not run_data or not run_data.get("server"):
        return make_banner("This run has no server location in B-Fabric, so there is no queue to show.", "error")
    try:
        state = draugr_queue.status(run_data["server"], history=QUEUE_HISTORY_EVENTS)
    except draugr_queue.QueueError as e:
        return make_banner(f"Could not read the draugr queue on {run_data['server']}: {e}", "error")
    return queue_view(state, run_data.get("datafolder"))


def _queue_action_dialog(action, job):
    """Title, body and confirm button (label, class) of the dialog confirming an action on a job."""
    label = _job_label(job)
    danger = "bf-btn bf-btn--danger"
    if action == "remove":
        return (
            f"Remove job {job['tsp_id']}?",
            f"The {label} is waiting in the queue and has not started. Removing it takes it off the queue.",
            "Remove job",
            danger,
        )
    if action == "stop":
        return (
            f"Stop job {job['tsp_id']}?",
            [
                html.P(
                    f"The {label} is running draugr now. Stopping it kills draugr and "
                    "bcl-convert wherever they are."
                ),
                html.Ul([
                    html.Li("The run folder may be left with partial output."),
                    html.Li("The run's status in B-Fabric stays at demultiplexing, and no failure email is sent."),
                    html.Li("Jobs set to run after it are not run; the next job in the queue starts."),
                ]),
            ],
            "Stop job",
            danger,
        )
    if action == "clear":
        return (
            f"Clear lost job {job['tsp_id']}?",
            f"This only clears the lost {label} from the list. Nothing is queued.",
            "Clear",
            danger,
        )
    # requeue
    body = [html.P(f"This queues the lost {label} again with the same draugr arguments, then clears it.")]
    if job.get("interrupted"):
        body.append(html.P(
            "draugr was running when this job was lost and may have left partial output in the run "
            "folder. Check it before queueing the job again.",
            className="bf-bold",
        ))  # fmt: skip
    if job.get("after"):
        waited = ", ".join(str(a["tsp_id"]) for a in job["after"])
        body.append(html.P(
            f"It waited for job(s) {waited}. Queued again, it will not wait for them: queue those "
            "first, or use Run after on the Draugr / DMX tab instead."
        ))  # fmt: skip
    return f"Queue job {job['tsp_id']} again?", body, "Queue again", "bf-btn"


@app.callback(
    [
        Output("queue-action-modal", "is_open"),
        Output("queue-action-title", "children"),
        Output("queue-action-body", "children"),
        Output("queue-action-confirm", "children"),
        Output("queue-action-confirm", "className"),
        Output("queue-action-target", "data"),
    ],
    [
        Input({"type": "queue-action", "action": ALL, "key": ALL}, "n_clicks"),
        Input("queue-action-dismiss", "n_clicks"),
        Input("queue-action-confirm", "n_clicks"),
    ],
    State("run_data", "data"),
    prevent_initial_call=True,
)
def toggle_queue_action_modal(_clicks, _dismiss, _confirm, run_data):
    trigger = ctx.triggered_id
    if trigger in ("queue-action-dismiss", "queue-action-confirm"):
        return False, no_update, no_update, no_update, no_update, no_update
    # Every refresh re-creates the buttons, which fires this without a click.
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return (no_update,) * 6

    # Describe the job as the server has it now, not as the page last showed it.
    try:
        job = draugr_queue.find(draugr_queue.status(run_data["server"], history=0), trigger["key"])
    except draugr_queue.QueueError as e:
        return True, "Could not read the queue", str(e), "Close", "bf-btn", None
    if job is None:
        return True, "Job gone", "This job is no longer in the queue.", "Close", "bf-btn", None
    title, body, confirm, confirm_class = _queue_action_dialog(trigger["action"], job)
    return True, title, body, confirm, confirm_class, {"action": trigger["action"], "key": trigger["key"]}


@app.callback(
    [
        Output("bf-notification", "children", allow_duplicate=True),
        Output("queue-version", "data", allow_duplicate=True),
    ],
    Input("queue-action-confirm", "n_clicks"),
    [
        State("queue-action-target", "data"),
        State("token_data", "data"),
        State("run_data", "data"),
        State("queue-version", "data"),
    ],
    prevent_initial_call=True,
    running=[(Output("queue-action-confirm", "disabled"), True, False)],
)
def run_queue_action(n_clicks, target, token_data, run_data, queue_version):
    if not n_clicks or not target or not token_data:
        return no_update, no_update
    server, key, action = run_data["server"], target["key"], target["action"]
    login = as_token_data(token_data).subject
    refreshed = (queue_version or 0) + 1
    severity = "info"
    try:
        state = draugr_queue.status(server, history=0)
        job = draugr_queue.find(state, key)
        if job is None:
            return _banner("That job is no longer in the queue.", "warning"), refreshed
        label = _job_label(job)
        if action == "stop":
            try:
                draugr_queue.stop(server, key, by=login)
            except draugr_queue.QueueError as e:
                # It finished between the last refresh and the click: not an error.
                if draugr_queue.not_running(e):
                    return _banner(f"The {label} had already ended.", "info"), refreshed
                raise
            message, params = f"Stopped the {label}.", {}
        elif action == "requeue":
            if job not in state["lost"]:
                return _banner(f"The {label} is no longer lost.", "warning"), refreshed
            tsp_id = draugr_queue.submit(
                server,
                job.get("run_folder") or f"{draugr_queue.DATA_DIR}/{job['run']}",
                job["draugr_args"],
                login,
            )
            params = {"new_tsp_id": tsp_id}
            try:
                draugr_queue.remove(server, key)
                message = f"Queued the lost {label} again as job {tsp_id}."
            except draugr_queue.QueueError as e:
                # The new job is queued; only clearing the old entry failed.
                # Saying "could not requeue" here would invite a second, duplicate run.
                severity = "warning"
                message = (
                    f"Queued the lost {label} again as job {tsp_id}, but could not clear the "
                    f"lost entry ({e}). Use Clear on it; do not queue it again."
                )
        else:  # remove, clear
            draugr_queue.remove(server, key)
            message, params = f"{'Removed' if action == 'remove' else 'Cleared'} the {label}.", {}
    except draugr_queue.QueueError as e:
        return _banner(f"Could not {action} the job: {e}", "error"), refreshed

    get_logger(token_data).log_operation(
        operation="execute",
        message=f"DMX job {action}",
        params={
            "server": server,
            "key": key,
            "tsp_id": job["tsp_id"],
            "draugr_args": job.get("draugr_args"),
            **params,
        },
        flush_logs=True,
    )
    return _banner(message, severity), refreshed


@app.callback(
    [
        Output("log-modal", "is_open"),
        Output("log-modal-title", "children"),
        Output("log-modal-body", "children"),
    ],
    Input({"type": "job-log", "key": ALL}, "n_clicks"),
    State("run_data", "data"),
    prevent_initial_call=True,
)
def show_log(_clicks, run_data):
    """The tail of a job's console output, looked up by key so only queue logs can be read."""
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update, no_update, no_update
    server = run_data["server"]
    try:
        job = draugr_queue.find(draugr_queue.status(server, history=QUEUE_HISTORY_EVENTS), ctx.triggered_id["key"])
        if not job or not job.get("log"):
            return True, "No log", "This job has no log (yet)."
        lines = draugr_queue.LOG_TAIL_LINES
        return True, f"Log of {_job_label(job)} (last {lines} lines)", draugr_queue.log_tail(server, job["log"], lines)
    except draugr_queue.QueueError as e:
        return True, "Could not read the log", str(e)


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


# --- Reset all switch/input state on each new page load ---


@app.callback(
    [
        Output("disable-wizard", "value"),
        Output("skip-raw-qc", "value"),
        Output("gstore", "value"),
        Output("skip-postprocessing", "value"),
        Output("skip-demux", "value"),
        Output("bases2fastq-input", "value"),
        Output("bclconvert-input", "value"),
        Output("bases-mask-input", "value"),
        Output("barcode-mismatches-input", "value"),
        Output("draugr-dropdown", "value"),
    ],
    Input("token_data", "data"),
    prevent_initial_call=False,
)
def reset_form_state(_token_data):
    """Force switch/input props to defaults on every page load.

    Overrides browser form-state restoration, which can cause the visual state
    of the switches to differ from Dash's internal state. The Registration dropdown
    is not reset here: update_registration_status pre-selects its outstanding orders.
    """
    return False, True, False, False, False, "", "", "", "", None


if __name__ == "__main__":
    app.run(debug=DEBUG, port=PORT, host=HOST)
