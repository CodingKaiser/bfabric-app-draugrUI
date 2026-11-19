"""
Domain-specific UI components for DraugrUI.

Only contains components unique to the Draugr workflow: lane cards, DMX and
BF registration sidebars, the draugr queue and BF registration status tables, confirmation
modals, and documentation.
The app shell — title bar, entity row, tab bar, notification stack — and the
generic auth/layout components come from bfabric_web_apps, as do the .bf-*
classes used below (the library's design system in
bfabric_web_apps/assets/bfabric.css, served automatically by the shell).

The switches are dbc.Switch, whose state prop is `value`. They were
daq.BooleanSwitch (prop `on`) until dash_daq stopped arriving as a transitive
dependency of the library, which itself moved off dash_daq for the same reason.
"""

import shlex

import dash_bootstrap_components as dbc
from dash import dcc, html

from utils import draugr_queue, registration_status

# ==================== Lane Cards ====================


def lane_card(lane_position, container_ids, highlight=False):
    """One lane of the run, listing the orders whose samples it holds."""
    body = (
        [html.P("Container IDs:", className="bf-muted")]
        + [html.H5(name) for name in container_ids]
        if container_ids
        else [html.P("[None Assigned]", className="bf-muted")]
    )

    style = {"maxWidth": "25vw", "marginBottom": "10px"}
    if highlight:
        # Lanes holding a selected order are called out in the B-Fabric accent.
        style["borderColor"] = "var(--bf-accent)"
        style["borderWidth"] = "2px"

    return html.Div(
        className="bf-panel",
        style=style,
        children=[
            html.Div(f"Lane {lane_position}", className="bf-panel-header"),
            html.Div(body, className="bf-panel-body"),
        ],
    )


# ==================== Sidebars ====================

_switch_row_style = {
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "space-between",
    "marginBottom": "8px",
}
_icon_style = {"cursor": "help", "color": "#888", "fontSize": "0.8em", "marginLeft": "4px"}


def _label(text, tip_id):
    return html.Span([text, html.Span(" ⓘ", id=tip_id, style=_icon_style)])


def _switch_row(text, tip_id, switch_id, on=False):
    return html.Div(
        [_label(text, tip_id), dbc.Switch(id=switch_id, value=on, className="mb-0")],
        style=_switch_row_style,
    )


def _instrument_section(title, note, colour, children):
    """Box a group of instrument-specific inputs so it reads as its own unit."""
    return html.Div(
        [
            html.P(
                title,
                className="bf-bold",
                style={"marginBottom": "2px", "color": colour},
            ),
            html.P(note, className="bf-muted", style={"marginBottom": "8px"}),
        ]
        + children,
        style={
            "border": f"2px solid {colour}",
            "background": "rgba(0, 0, 0, 0.03)",
            "padding": "10px",
            "marginTop": "8px",
        },
    )


# Bases mask and barcode mismatches are top-level draugr flags as of v2.8.0:
# bcl-convert 4.5.4 has no --use-bases-mask and no --barcode-mismatches option,
# they are sample sheet settings. Typing either into the custom bclconvert flags
# field makes draugr exit 2, hence the dedicated inputs.
illumina_specific_section = _instrument_section(
    "Illumina-Specific",
    "Applies to Illumina runs only; ignored for Element/Aviti.",
    "#ed8b00",
    [
        dbc.Input(value="", placeholder="Custom bclconvert flags", id="bclconvert-input"),
        html.Br(),
        dbc.Input(
            value="",
            placeholder="Bases mask (e.g. y36n*,I8n*,I8n*,y150n*)",
            id="bases-mask-input",
        ),
        html.Br(),
        html.Div(
            [
                _label("Barcode mismatches", "tip-barcode-mismatches"),
                dcc.Dropdown(
                    options=[
                        {"label": "Auto (draugr computes)", "value": ""},
                        {"label": "0", "value": "0"},
                        {"label": "1", "value": "1"},
                        {"label": "2", "value": "2"},
                    ],
                    value="",
                    id="barcode-mismatches-input",
                    clearable=False,
                    style={"width": "12vw"},
                ),
            ],
            style=_switch_row_style,
        ),
    ],
)

# Element exposes real settings flags on bases2fastq, so masks and mismatch
# thresholds go inside the custom flags string here — there is no --bases-mask
# for Element and the Illumina fields above do not apply.
element_specific_section = _instrument_section(
    "Element-Specific",
    "Applies to Element/Aviti runs only; ignored for Illumina.",
    "#35306e",
    [
        dbc.Input(value="", placeholder="Custom Bases2fastq flags", id="bases2fastq-input"),
    ],
)

# The Submit button is wrapped in its own div because a tooltip cannot attach to
# a disabled button — the wrapper is the tooltip's target instead.
default_sidebar = [
    html.P("Select Orders to DMX", id="sidebar_text"),
    dcc.Dropdown([], id="draugr-dropdown", multi=True),
    html.Br(),
    _switch_row("Disable Wizard", "tip-disable-wizard", "disable-wizard", on=False),
    _switch_row("Skip RawQC", "tip-skip-raw-qc", "skip-raw-qc", on=True),
    html.Br(),
    illumina_specific_section,
    element_specific_section,
    html.Br(),
    html.P("Advanced Options", className="bf-bold", style={"marginBottom": "4px"}),
    _switch_row("Skip GStore Copy", "tip-gstore", "gstore", on=False),
    _switch_row("Skip Postprocessing", "tip-skip-postprocessing", "skip-postprocessing", on=False),
    _switch_row("Skip Demultiplexing", "tip-skip-demux", "skip-demux", on=False),
    html.Div(_label("Run after", "tip-after"), style={"marginBottom": "4px"}),
    # Filled with the jobs queued or running on the run's server.
    dcc.Dropdown([], id="after-dropdown", multi=True, placeholder="No other job"),
    html.Br(),
    html.Div(
        id="submit-btn-wrapper",
        children=dbc.Button("Submit", id="draugr-button", className="bf-btn"),
    ),
]

registration_sidebar = [
    html.P("Select Orders to Register", id="sidebar_text2"),
    dcc.Dropdown([], id="draugr-dropdown-2", multi=True),
    html.Br(),
    html.Div(
        id="submit-btn-wrapper-2",
        children=dbc.Button("Submit", id="draugr-button-2", className="bf-btn"),
    ),
]


# ==================== Queue ====================


def _pill(text, kind):
    return html.Span(text, className=f"bf-pill bf-pill--{kind}")


def _when(timestamp):
    return (timestamp or "").replace("T", " ") or "—"


def _orders(job):
    return ", ".join(job["orders"]) if job["orders"] else "all"


def _parameters(job):
    return html.Details([
        html.Summary("show"),
        html.Pre(
            shlex.join(job.get("draugr_args") or []),
            style={"whiteSpace": "pre-wrap", "textAlign": "left", "maxWidth": "40vw"},
        ),
    ])


def _action(label, action, job, danger=False):
    """A button acting on a job by its key; the app confirms it in the queue action dialog."""
    return dbc.Button(
        label,
        id={"type": "queue-action", "action": action, "key": job["key"]},
        className="bf-btn bf-btn--danger" if danger else "bf-btn",
        size="sm",
        style={"marginRight": "4px"},
    )


def _log_button(job):
    if not job.get("log"):
        return ""
    return dbc.Button(
        "Log", id={"type": "job-log", "key": job["key"]}, className="bf-btn", size="sm",
        style={"marginRight": "4px"},
    )  # fmt: skip


def _table(header, rows):
    return html.Table(
        [html.Thead(html.Tr([html.Th(h) for h in header])), html.Tbody(rows)],
        className="bf-stats",
    )


def _row(job, run_folder, cells):
    style = {"background": "rgba(234, 107, 19, 0.08)"} if job["run"] == run_folder else {}
    return html.Tr([html.Td(cell) for cell in cells], style=style)


def _panel(title, body, colour=None):
    style = {"marginBottom": "12px"}
    if colour:
        style.update({"borderColor": colour, "borderWidth": "2px"})
    return html.Div(className="bf-panel", style=style, children=[
        html.Div(title, className="bf-panel-header"),
        html.Div(body, className="bf-panel-body"),
    ])  # fmt: skip


def _current_state(job):
    """The state pill, plus the job's place in the queue or when it started."""
    if job["state"] == "running":
        return [_pill("running", "info"), html.Div(f"since {_when(job.get('started_at'))}", className="bf-muted")]
    return [_pill("queued", "none"), html.Div(f"#{job['position']} in queue", className="bf-muted")]


def _current_row(job, run_folder):
    after = ", ".join(str(a["tsp_id"]) for a in job.get("after") or []) or "—"
    actions = [_log_button(job)]
    if job["state"] == "queued":
        actions.append(_action("Remove", "remove", job, danger=True))
    else:
        actions.append(_action("Stop", "stop", job, danger=True))
    return _row(job, run_folder, [
        job["tsp_id"], _current_state(job), job["run"], _orders(job), job.get("source") or "—",
        job.get("submitter") or "—", _when(job.get("submitted_at")), after, _parameters(job), actions,
    ])  # fmt: skip


def _lost_row(job, run_folder):
    if job.get("interrupted"):
        was = [_pill("interrupted", "fail"), html.Div("may have left partial output", className="bf-muted")]
    else:
        was = [_pill("never started", "warn"), html.Div("safe to queue again", className="bf-muted")]
    return _row(job, run_folder, [
        job["tsp_id"], was, job["run"], _orders(job), job.get("submitter") or "—",
        _when(job.get("submitted_at")), _parameters(job),
        [_action("Queue again", "requeue", job), _action("Clear", "clear", job, danger=True)],
    ])  # fmt: skip


def _outcome(job):
    if job["event"] == "removed":
        return [_pill("removed", "none"), html.Div(_when(job.get("removed_at")), className="bf-muted")]
    if draugr_queue.was_stopped(job):
        return [_pill("stopped", "warn"),
                html.Div(f"by {job['stopped_by']} at {_when(job.get('stopped_at'))}", className="bf-muted")]  # fmt: skip
    code = job.get("exit_code")
    text = draugr_queue.EXIT_CODES.get(code, f"exit {code}")
    return [_pill("succeeded" if code == 0 else "failed", "pass" if code == 0 else "fail"),
            html.Div(text if code == 0 else f"{text} ({code})", className="bf-muted")]  # fmt: skip


def _past_row(job):
    return html.Tr([html.Td(cell) for cell in [
        job.get("tsp_id", "—"), _outcome(job), _orders(job), job.get("source") or "—",
        job.get("submitter") or "—", _when(job.get("submitted_at")), _when(job.get("started_at")),
        _when(job.get("finished_at")), _parameters(job), _log_button(job),
    ]])  # fmt: skip


def _held_up_by(active, run_folder):
    """A warning when another run's job holds the server, so this run's jobs cannot start yet."""
    running = next((job for job in active if job["state"] == "running"), None)
    if running is None or running["run"] == run_folder:
        return ""
    waiting = sum(job["run"] == run_folder for job in active)
    if waiting:
        effect = f"{waiting} job{'s' if waiting > 1 else ''} for this run {'are' if waiting > 1 else 'is'} waiting behind it."
    else:
        effect = "Anything queued for this run now waits until it ends."
    return html.Div(
        [_pill("busy", "warn"), " ", html.B(running["run"]),
         f" is running on this server (job {running['tsp_id']}, since {_when(running.get('started_at'))}). {effect}"],
        style={"marginBottom": "8px"},
    )  # fmt: skip


def queue_view(state, run_folder):
    """The server's lost jobs (if any), its current queue, then the jobs that ended."""
    panels = []
    if state["lost"]:
        panels.append(_panel(
            "Lost jobs: the server dropped these without finishing them (e.g. on a reboot)",
            _table(
                ["Job", "Was", "Run", "Orders", "Submitted by", "Submitted", "Parameters", ""],
                [_lost_row(job, run_folder) for job in state["lost"]],
            ),
            colour="var(--bf-danger, #c0392b)",
        ))  # fmt: skip

    active = draugr_queue.active_jobs(state)
    panels.append(_panel(
        f"Queue on {state['server']}",
        [
            _held_up_by(active, run_folder),
            _table(
                ["Job", "State", "Run", "Orders", "Source", "Submitted by", "Submitted", "After", "Parameters", ""],
                [_current_row(job, run_folder) for job in active],
            ) if active else html.P("No draugr jobs are queued or running.", className="bf-muted"),
        ],
    ))  # fmt: skip

    past = [job for job in state["past"] if job["run"] == run_folder]
    panels.append(_panel(
        "Ended for this run",
        _table(
            ["Job", "Outcome", "Orders", "Source", "Submitted by", "Submitted", "Started",
             "Ended", "Parameters", ""],
            [_past_row(job) for job in past],
        ) if past else html.P("None recently.", className="bf-muted"),
    ))  # fmt: skip
    return panels


queue_pane = html.Div(
    style={"paddingTop": "12px"},
    children=[
        html.P(
            "The draugr queue on this run's server, which runs one draugr job at a time; the "
            "others wait their turn. Rows for this run are highlighted. Refreshes every 15 seconds.",
            className="bf-muted",
        ),
        dcc.Interval(id="queue-interval", interval=15_000, disabled=True),
        dcc.Store(id="queue-action-target"),
        html.Div(id="queue-display"),
    ],
)


# ==================== BF registration status ====================

_REGISTRATION_STATUS_PILL = {
    registration_status.REGISTERED: "pass",
    registration_status.READY: "info",
    registration_status.SUBMITTED: "warn",
    registration_status.DEMUXING: "info",
    registration_status.NOT_DEMUXED: "none",
}


_LEFT = {"textAlign": "left"}  # .bf-stats centres cells


def registration_status_table(rows, order_names, dataset_url):
    """One row per order: its status and, once registered, a link to the dataset."""

    def dataset_cell(row):
        if row["dataset_id"]:
            return html.A(row["dataset_name"], href=dataset_url(row["dataset_id"]), target="_blank")
        if row["submitted_at"]:
            return html.Span(f"submitted at {row['submitted_at'].replace('T', ' ')}", className="bf-muted")
        return "—"

    return html.Div(className="bf-panel", children=[
        html.Div("BF registration status", className="bf-panel-header"),
        html.Div(className="bf-panel-body", children=html.Table(
            [
                html.Thead(html.Tr([html.Th(h, style=_LEFT) for h in ["Order", "Name", "Status", "Dataset"]])),
                html.Tbody([
                    html.Tr([
                        html.Td(row["order"], style=_LEFT),
                        html.Td(order_names.get(row["order"], ""), style=_LEFT),
                        html.Td(_pill(row["status"], _REGISTRATION_STATUS_PILL[row["status"]]), style=_LEFT),
                        html.Td(dataset_cell(row), style=_LEFT),
                    ])
                    for row in rows
                ]),
            ],
            className="bf-stats",
        )),
    ])  # fmt: skip


# ==================== Modals ====================

modal = html.Div([
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Ready to DMX?")),
        # Filled when the modal opens, with any jobs already queued for this run.
        dbc.ModalBody("Are you sure you're ready to demux?", id="modal-body"),
        dbc.ModalFooter(
            dbc.Button("Yes!", id="close", className="ms-auto", n_clicks=0)
        ),
    ], id="modal", is_open=False),
])

modal2 = html.Div([
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Ready to register?")),
        dbc.ModalBody("Are you sure you're ready to register in B-Fabric?"),
        dbc.ModalFooter(
            dbc.Button("Yes!", id="close2", className="ms-auto", n_clicks=0)
        ),
    ], id="modal2", is_open=False),
])

# Confirms a Remove, Stop, Clear or Queue again on the Queue tab; title, body and
# confirm label are filled for the action when it opens.
queue_action_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle(id="queue-action-title")),
    dbc.ModalBody(id="queue-action-body"),
    dbc.ModalFooter([
        dbc.Button("Back", id="queue-action-dismiss", className="bf-btn", n_clicks=0),
        dbc.Button(id="queue-action-confirm", className="bf-btn bf-btn--danger", n_clicks=0),
    ]),
], id="queue-action-modal", is_open=False)

log_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle(id="log-modal-title")),
    dbc.ModalBody(html.Pre(id="log-modal-body", style={"whiteSpace": "pre-wrap", "fontSize": "0.8em"})),
], id="log-modal", is_open=False, size="xl", scrollable=True)


# ==================== Documentation ====================

documentation_content = [
    html.H2("Welcome to Draugr UI"),
    html.P([
        "This app is the user interface for ",
        html.A("Draugr", href="https://gitlab.bfabric.org/Genomics/draugr", target="_blank"),
        " (Demultiplexing wRapper And Updated GRiffin)."
    ]),
    html.Br(),
    html.H4("Developer Info"),
    html.P([
        "This app was written for the FGCZ. To report a bug, use the \"Report a Bug\" tab. For anything else, email the developer at",
        html.A(" falko.noe@fgcz.uzh.ch", href="mailto:falko.noe@fgcz.uzh.ch"),
    ]),
    html.Br(),
    html.H4("Draugr / DMX Tab"),
    html.P([
        html.B("Select Orders to DMX:"),
        " the orders you want to demultiplex again.",
        html.Br(), html.Br(),
        html.B("Skip GStore Copy:"),
        " don't copy the results to gstore. Useful when you're not yet sure the settings will work.",
        html.Br(), html.Br(),
        html.B("Skip Postprocessing:"),
        " skip the post-demultiplexing processing steps.",
        html.Br(), html.Br(),
        html.B("Skip Demultiplexing:"),
        " skip the demultiplexing step entirely.",
        html.Br(), html.Br(),
        html.B("Run after:"),
        """ optional. Pick jobs on this run's server that must succeed first. The new job runs draugr
        only if all of them succeeded; otherwise it is not run and counts as failed itself. For example,
        demultiplex lanes separately with Skip Postprocessing and Skip GStore Copy, then queue the
        delivery of all orders with Skip Demultiplexing to run after them.""",
        html.Br(), html.Br(),
        html.B("Disable Wizard:"),
        " the wizard is Draugr's automatic barcode detection and correction. Turn it off if you're confident the assigned barcodes are correct, or if it creates barcode conflicts while you test new settings.",
        html.Br(), html.Br(),
        html.B("Skip RawQC:"),
        " don't generate the RawQC report.",
        html.Br(), html.Br(),
        html.B("Custom bclconvert flags (Illumina-Specific):"),
        """ custom bcl-convert flags for the standard samples, separated by ';', e.g.
        "--tiles s_1_2201+s_1_2202;--num-unknown-barcodes-reported 20". bcl-convert has no command-line
        option for the bases mask or barcode mismatches, and Draugr rejects them here; use the
        Illumina-Specific fields below instead. For all possible flags, see the """,
        html.A("bcl-convert documentation", href="https://help.dragen.illumina.com/dragen-v4.5/product-guides/dragen-v4.5/bcl-conversion", target="_blank"),
        html.Br(), html.Br(),
        html.B("Bases mask (Illumina-Specific):"),
        """ overrides the computed bases mask. Accepts the comma form "y36n*,I8n*,I8n*,y150n*" or the
        semicolon form "Y36N*;I8N*;I8N*;Y150N*". Give exactly one token per read position, in run order.
        If the token count doesn't match the run, Draugr logs an "Ignoring --bases-mask" warning and falls
        back to the computed mask, so check the log if your mask doesn't seem to apply. Leave it empty to
        use the computed mask.""",
        html.Br(), html.Br(),
        html.B("Barcode mismatches (Illumina-Specific):"),
        """ overrides the number of barcode mismatches allowed, which Draugr otherwise derives from the
        barcodes' Hamming distances. Allowed values are 0, 1 and 2; leave it on "Auto" to let Draugr decide.""",
        html.Br(), html.Br(),
        html.B("Custom Bases2fastq flags (Element-Specific):"),
        """ custom bases2fastq flags, separated by ';', e.g. "--i1-cycles 8;--r2-cycles 40". Unlike
        bcl-convert, bases2fastq has real settings flags, so masks and mismatch thresholds go here rather
        than in the Illumina-Specific fields, e.g.
        "--settings R1FastqMask,R1:y36n*;--settings I1MismatchThreshold,0". For all possible flags, see the """,
        html.A("bases2fastq documentation", href="https://docs.elembio.io/docs/bases2fastq/", target="_blank"),
        html.Br(), html.Br(),
    ], style={"marginLeft": "2vw"}),
        html.H4("Registered Tab"),
    html.P([
        html.B("Select Orders to Register:"),
        " the orders you want to register in B-Fabric again. After you click Submit and confirm, DraugrUI registers their datasets in B-Fabric, creates the FastQC and FastQScreen reports and updates the order statuses.",
        html.Br(), html.Br(),
        html.B("BF registration status:"),
        " each order on the run has one of these statuses. Ready orders are pre-selected.",
        html.Br(),
        html.B("Not demultiplexed:"), " draugr has not produced a dataset for the order on this run yet.",
        html.Br(),
        html.B("Ready:"), " demultiplexed, but no dataset is registered in B-Fabric yet.",
        html.Br(),
        html.B("Submitted:"), """ submitted from DraugrUI within the last hour, and B-Fabric has no dataset
        yet. Registration takes a few minutes, and submitting again before it lands registers a duplicate dataset.""",
        html.Br(),
        html.B("Registered:"), " B-Fabric holds a dataset for the order and this run, linked in the table.",
        html.Br(),
        html.B("Demultiplexing:"), " a draugr job for the order, or for every order on the run, is queued or running.",
        html.Br(), html.Br(),
    ], style={"marginLeft": "2vw"}),
    html.H4("Queue Tab"),
    html.P([
        """Submitting on the Draugr / DMX tab queues the run on the instrument server that holds the data;
        it does not start draugr straight away. Each server runs one draugr job at a time, because
        demultiplexing needs the whole server, and the next job starts when the previous one finishes.
        The automatic run queued when a sequencing run finishes, and runs queued on the command line,
        wait in the same queue.""",
        html.Br(), html.Br(),
        """The Queue tab shows that server's running job, its queued jobs in order, and the jobs that have
        ended for the run you opened. If another run's job is running, a note above the queue says so,
        since this run's jobs cannot start until it ends. "Parameters" shows the exact draugr arguments
        a job was given, and "Log" its console output, also while it runs. Rows for the run you opened
        are highlighted.""",
        html.Br(), html.Br(),
        html.B("Remove:"),
        " takes a queued job off the queue.",
        html.Br(), html.Br(),
        html.B("Stop:"),
        """ kills the running job, bcl-convert included, wherever it is. The run folder may be left with
        partial output, the run's B-Fabric status stays at demultiplexing, and no failure email is sent.
        Jobs set to run after it are not run, and the next job in the queue starts.""",
        html.Br(), html.Br(),
        html.B("Lost jobs:"),
        """ jobs the server dropped without finishing, usually because it rebooted. One that "never
        started" is safe to queue again. One that was "interrupted" was running and may have left partial
        output, so check the run folder before queueing it again. "Queue again" submits the same
        arguments and clears the entry; "Clear" only clears it.""",
        html.Br(), html.Br(),
    ], style={"marginLeft": "2vw"}),
]
