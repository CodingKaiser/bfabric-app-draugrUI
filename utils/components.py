"""
Domain-specific UI components for DraugrUI.

Only contains components unique to the Draugr workflow: lane cards, DMX/Sushi
sidebars, the draugr queue and sushification status tables, confirmation
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

from utils import sushi_status

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
    html.Br(),
    html.Div(
        id="submit-btn-wrapper",
        children=dbc.Button("Submit", id="draugr-button", className="bf-btn"),
    ),
]

sushi_sidebar = [
    html.P("Select Orders to Sushify", id="sidebar_text2"),
    dcc.Dropdown([], id="draugr-dropdown-2", multi=True),
    html.Br(),
    html.Div(
        id="submit-btn-wrapper-2",
        children=dbc.Button("Submit", id="draugr-button-2", className="bf-btn"),
    ),
]


# ==================== Queue ====================

_JOB_STATE_PILL = {
    "RUNNING": "info",
    "COMPLETING": "info",
    "CONFIGURING": "info",
    "PENDING": "none",
    "COMPLETED": "pass",
    "CANCELLED": "warn",
}


def _pill(text, kind):
    return html.Span(text, className=f"bf-pill bf-pill--{kind}")


def _job_state(job):
    """The state pill, plus where the job is: its node, or its place in the queue."""
    state = _pill(job["state"], _JOB_STATE_PILL.get(job["state"], "fail"))
    if job["state"] == "PENDING" and job["position"]:
        # "Dependency" means it is waiting for the job ahead of it on the same server.
        detail = f"#{job['position']} in queue"
    elif job["state"] == "RUNNING":
        detail = job["node"]
    else:
        detail = job["exit_code"] and f"exit {job['exit_code']}"
    return [state, html.Div(detail, className="bf-muted")] if detail else state


def _job_parameters(job):
    if job["draugr_args"] is None:
        return html.Span("not recorded", className="bf-muted")
    return html.Details([
        html.Summary("show"),
        html.Pre(
            " ".join(shlex.quote(a) for a in job["draugr_args"]) + f"\n\nlog: {job['log']}",
            style={"whiteSpace": "pre-wrap", "textAlign": "left", "maxWidth": "40vw"},
        ),
    ])


def _job_row(job, run_folder):
    cancel = (
        dbc.Button(
            "Cancel",
            # The state picks the wording of the confirmation dialog.
            id={"type": "cancel-job", "id": job["jobid"], "state": job["state"]},
            className="bf-btn bf-btn--danger",
            size="sm",
        )
        if job["active"]
        else ""
    )
    style = {"background": "rgba(234, 107, 19, 0.08)"} if job["run"] == run_folder else {}
    return html.Tr(
        [
            html.Td(job["jobid"]),
            html.Td(_job_state(job)),
            html.Td(job["run"] or "—"),
            html.Td(", ".join(job["orders"]) or "all"),
            html.Td(job["source"] or "—"),
            html.Td(job["submitter"] or "—"),
            html.Td(job["submitted"].replace("T", " ")),
            html.Td(job["started"].replace("T", " ") or "—"),
            html.Td(job["elapsed"]),
            html.Td(_job_parameters(job)),
            html.Td(cancel),
        ],
        style=style,
    )


_JOB_HEADER = html.Thead(html.Tr([html.Th(h) for h in [
    "Job", "State", "Run", "Orders", "Source", "Submitted by",
    "Submitted", "Started", "Elapsed", "Parameters", "",
]]))  # fmt: skip


def _job_table(jobs, run_folder):
    return html.Table(
        [_JOB_HEADER, html.Tbody([_job_row(job, run_folder) for job in jobs])],
        className="bf-stats",
    )


def queue_view(jobs, run_folder, days):
    """Active jobs in one panel per server, then everything that ended recently."""
    active = [job for job in jobs if job["active"]]
    recent = [job for job in jobs if not job["active"]]

    panels = []
    for server in sorted({job["server"] for job in active}):
        panels.append(html.Div(className="bf-panel", style={"marginBottom": "12px"}, children=[
            html.Div(server, className="bf-panel-header"),
            html.Div(
                _job_table([job for job in active if job["server"] == server], run_folder),
                className="bf-panel-body",
            ),
        ]))  # fmt: skip
    if not panels:
        panels.append(html.P("No draugr jobs are queued or running.", className="bf-muted"))

    panels.append(html.Div(className="bf-panel", children=[
        html.Div(f"Ended in the last {days} days", className="bf-panel-header"),
        html.Div(
            _job_table(recent, run_folder) if recent
            else html.P("None.", className="bf-muted"),
            className="bf-panel-body",
        ),
    ]))  # fmt: skip
    return panels


queue_pane = html.Div(
    style={"paddingTop": "12px"},
    children=[
        html.P(
            "draugr runs one job per instrument server at a time; the others wait in "
            "the queue. Rows for this run are highlighted. Refreshes every 15 seconds.",
            className="bf-muted",
        ),
        dcc.Interval(id="queue-interval", interval=15_000, disabled=True),
        dcc.Store(id="cancel-target"),
        html.Div(id="queue-display"),
    ],
)


# ==================== Sushification status ====================

_SUSHI_STATUS_PILL = {
    sushi_status.SUSHIFIED: "pass",
    sushi_status.READY: "info",
    sushi_status.SUBMITTED: "warn",
    sushi_status.DEMUXING: "info",
    sushi_status.NOT_DEMUXED: "none",
}


def sushi_status_table(rows, order_names, dataset_url):
    """One row per order: its status and, once sushified, a link to the dataset."""

    def dataset_cell(row):
        if row["dataset_id"]:
            return html.A(row["dataset_name"], href=dataset_url(row["dataset_id"]), target="_blank")
        if row["submitted_at"]:
            return html.Span(f"sushified at {row['submitted_at'].replace('T', ' ')}", className="bf-muted")
        return "—"

    return html.Div(className="bf-panel", children=[
        html.Div("Sushification status", className="bf-panel-header"),
        html.Div(className="bf-panel-body", children=html.Table(
            [
                html.Thead(html.Tr([html.Th(h) for h in ["Order", "Name", "Status", "Dataset"]])),
                html.Tbody([
                    html.Tr([
                        html.Td(row["order"]),
                        html.Td(order_names.get(row["order"], "")),
                        html.Td(_pill(row["status"], _SUSHI_STATUS_PILL[row["status"]])),
                        html.Td(dataset_cell(row)),
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
        dbc.ModalHeader(dbc.ModalTitle("Ready to Sushify?")),
        dbc.ModalBody("Are you sure you're ready to sushify?"),
        dbc.ModalFooter(
            dbc.Button("Yes!", id="close2", className="ms-auto", n_clicks=0)
        ),
    ], id="modal2", is_open=False),
])

cancel_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Cancel draugr job?")),
    dbc.ModalBody(id="cancel-modal-body"),
    dbc.ModalFooter([
        dbc.Button("Keep it", id="cancel-dismiss", className="bf-btn", n_clicks=0),
        dbc.Button("Cancel job", id="cancel-confirm", className="bf-btn bf-btn--danger", n_clicks=0),
    ]),
], id="cancel-modal", is_open=False)


# ==================== Documentation ====================

documentation_content = [
    html.H2("Welcome to Draugr UI"),
    html.P([
        "This app serves as the user-interface for ",
        html.A("Draugr,", href="https://gitlab.bfabric.org/Genomics/draugr", target="_blank"),
        " or Demultiplexing wRapper And Updated GRiffin."
    ]),
    html.Br(),
    html.H4("Developer Info"),
    html.P([
        "This app was written for the FGCZ. If you wish to report a bug, please use the \"Report a Bug\" tab. If you wish to contact the developer for other reasons, please use the email:",
        html.A(" falko.noe@fgcz.uzh.ch", href="mailto:falko.noe@fgcz.uzh.ch"),
    ]),
    html.Br(),
    html.H4("Draugr / DMX Tab"),
    html.P([
        html.B("Select Orders to DMX --"),
        " Select the order(s) for which you'd like to re-trigger demultiplexing.",
        html.Br(), html.Br(),
        html.B("Skip GStore Copy --"),
        " Select this option if you don't want to copy to gstore. Mostly useful if you're not sure yet if the current settings will work.",
        html.Br(), html.Br(),
        html.B("Skip Postprocessing --"),
        " Skip the post-demultiplexing processing steps.",
        html.Br(), html.Br(),
        html.B("Skip Demultiplexing --"),
        " Skip the demultiplexing step entirely.",
        html.Br(), html.Br(),
        html.B("Disable Wizard --"),
        " The wizard is Draugr's internal automatic-barcode detection and correction engine. If you're confident that the correct barcodes are assigned, or the wizard is creating barcode conflicts while checking new settings, you should turn the wizard off.",
        html.Br(), html.Br(),
        html.B("Skip RawQC --"),
        " If you would like to skip generation of the RawQC report, select this option.",
        html.Br(), html.Br(),
        html.B("Custom bclconvert flags (Illumina-Specific) --"),
        """ Custom bclconvert flags to use for the standard samples, with arguments
        separated by ';' characters, E.g. "--tiles s_1_2201+s_1_2202;--num-unknown-barcodes-reported 20".
        Use the Illumina-Specific fields below for the bases mask and barcode mismatches — bcl-convert has no
        command-line option for either, and Draugr will reject them if given here. For a full list of possible flags, see the """,
        html.A("bcl-convert documentation", href="https://help.dragen.illumina.com/dragen-v4.5/product-guides/dragen-v4.5/bcl-conversion", target="_blank"),
        html.Br(), html.Br(),
        html.B("Bases mask (Illumina-Specific) --"),
        """ Overrides the automatically computed bases mask. Accepts the comma form
        "y36n*,I8n*,I8n*,y150n*" or the semicolon form "Y36N*;I8N*;I8N*;Y150N*". You must give exactly one
        token per read position in the run, in run order. If the token count doesn't match the run,
        Draugr logs an "Ignoring --bases-mask" warning and silently falls back to the computed mask, so check
        the log if your mask doesn't seem to have applied. Leave empty to use the computed mask.""",
        html.Br(), html.Br(),
        html.B("Barcode mismatches (Illumina-Specific) --"),
        """ Overrides the number of permitted barcode mismatches, which Draugr otherwise derives from
        barcode Hamming distances. Allowed values are 0, 1 and 2; leave on "Auto" to let Draugr decide.""",
        html.Br(), html.Br(),
        html.B("Custom Bases2fastq flags (Element-Specific) --"),
        """ Custom bases2fastq flags to use wrapped in a string, with arguments
        separated by ';' characters, E.g. "--i1-cycles 8;--r2-cycles 40 ". Unlike bcl-convert, bases2fastq
        exposes real settings flags, so masks and mismatch thresholds belong here rather than in the
        Illumina-Specific fields, E.g. "--settings R1FastqMask,R1:y36n*;--settings I1MismatchThreshold,0".
        For a full list of possible flags, see the """,
        html.A("bases2fastq documentation", href="https://docs.elembio.io/docs/bases2fastq/", target="_blank"),
        html.Br(), html.Br(),
    ], style={"marginLeft": "2vw"}),
        html.H4("Sushify Tab"),
    html.P([
        html.B("Select Orders to Sushify --"),
        " Select the order(s) for which you'd like to re-trigger sushification. After clicking \"submit\" and confirming your submission, DraugrUI will send a request to the sushi server to begin creating fastqc and fastqscreen reports. Order statuses will be updated at this stage as well. ",
        html.Br(), html.Br(),
        html.B("Sushification status --"),
        " Each order on the run is shown with one of these statuses. Orders that are Ready are pre-selected.",
        html.Br(),
        html.B("Not demultiplexed:"), " draugr has not produced a dataset for the order on this run yet.",
        html.Br(),
        html.B("Ready:"), " demultiplexed, but no dataset is registered in B-Fabric yet.",
        html.Br(),
        html.B("Submitted:"), """ sushified from DraugrUI within the last hour, and B-Fabric has no dataset
        yet. Registration takes a few minutes; sushifying again before it lands registers a duplicate dataset.""",
        html.Br(),
        html.B("Sushified:"), " B-Fabric holds a dataset for the order and this run, linked in the table.",
        html.Br(),
        html.B("Demultiplexing:"), " a draugr job for the order is queued or running.",
        html.Br(), html.Br(),
    ], style={"marginLeft": "2vw"}),
    html.H4("Queue Tab"),
    html.P([
        """Submitting on the Draugr / DMX tab does not start draugr straight away: it queues a SLURM job.
        Each instrument server runs one draugr job at a time, because demultiplexing needs the whole server,
        and the next job for that server starts when the previous one finishes. Automatic runs started by
        draugr's run monitor wait in the same queue.""",
        html.Br(), html.Br(),
        """The Queue tab lists the queued and running jobs for each server, with their place in the queue,
        and the jobs that ended in the last seven days. "Parameters" shows the exact draugr arguments a job
        was given and where its log is. Rows belonging to the run you opened are highlighted.""",
        html.Br(), html.Br(),
        html.B("Cancel --"),
        """ removes a queued job from the queue. On a running job it stops draugr on the server,
        bcl-convert included. A cancelled run leaves whatever it had already written in place.""",
        html.Br(), html.Br(),
    ], style={"marginLeft": "2vw"}),
]
