"""
Domain-specific UI components for DraugrUI.

Only contains components unique to the Draugr workflow:
lane cards, DMX/Sushi sidebars, confirmation modals, and documentation.
Generic auth/layout components are now provided by bfabric_web_apps.
"""

import dash_bootstrap_components as dbc
from dash import html, dcc
import dash_daq as daq


# ==================== Lane Cards ====================

def lane_card(lane_position, container_ids):
    card_content = [
        dbc.CardHeader(f"Lane {lane_position}"),
        dbc.CardBody(
            [html.P("Container IDs:")] + [html.H5(name) for name in container_ids]
            if container_ids
            else html.P("[None Assigned]", style={"color": "gray"})
        ),
    ]
    return dbc.Card(card_content, style={"max-width": "25vw", "margin": "10px"})


# ==================== Sidebars ====================

_switch_row_style = {
    "display": "flex",
    "align-items": "center",
    "justify-content": "space-between",
    "margin-bottom": "8px",
}
_icon_style = {"cursor": "help", "color": "#888", "font-size": "0.8em", "margin-left": "4px"}

def _label(text, tip_id):
    return html.Span([text, html.Span(" ⓘ", id=tip_id, style=_icon_style)])

default_sidebar = [
    html.P("Select Orders to DMX", id="sidebar_text"),
    dcc.Dropdown([], id='draugr-dropdown', multi=True),
    html.Br(),
    html.Div([_label("Disable Wizard", "tip-wizard"),  daq.BooleanSwitch(id='wizard', on=False)],          style=_switch_row_style),
    html.Div([_label("Is Multiome",    "tip-multiome"),daq.BooleanSwitch(id='multiome', on=False)],        style=_switch_row_style),
    html.Br(),
    dbc.Input(value="", placeholder='Custom Bcl2fastq flags', id='bcl-input'),
    html.Br(),
    dbc.Input(value="", placeholder='Custom Cellranger flags', id='cellranger-input'),
    html.Br(),
    dbc.Input(value="", placeholder='Custom Bases2fastq flags', id='bases2fastq-input'),
    html.Br(),
    html.P("Advanced Options", style={"font-weight": "bold", "margin-bottom": "4px"}),
    html.Div([_label("Skip GStore Copy",    "tip-gstore"),             daq.BooleanSwitch(id='gstore', on=False)],            style=_switch_row_style),
    html.Div([_label("Skip Postprocessing", "tip-skip-postprocessing"),daq.BooleanSwitch(id='skip-postprocessing', on=False)], style=_switch_row_style),
    html.Div([_label("Skip Demultiplexing", "tip-skip-demux"),         daq.BooleanSwitch(id='skip-demux', on=False)],         style=_switch_row_style),
    html.Br(),
    dbc.Button('Submit', id='draugr-button'),
]

sushi_sidebar = [
    html.P(id="sidebar_text2", children="Select Orders to Sushify"),
    dcc.Dropdown([], id='draugr-dropdown-2', multi=True),
    html.Br(),
    html.Div(id="submit-btn-wrapper-2", children=dbc.Button('Submit', id='draugr-button-2')),
]


# ==================== Modals ====================

modal = html.Div([
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Ready to DMX?")),
        dbc.ModalBody("Are you sure you're ready to demux?"),
        dbc.ModalFooter(
            dbc.Button("Yes!", id="close", className="ms-auto", n_clicks=0)
        ),
    ], id="modal", is_open=False),
])

modal2 = html.Div([
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Ready to Prepare Fastq Reports?")),
        dbc.ModalBody("Are you sure you're ready to begin preparing FastqScreen and FastQC reports?"),
        dbc.ModalFooter(
            dbc.Button("Yes!", id="close2", className="ms-auto", n_clicks=0)
        ),
    ], id="modal2", is_open=False),
])


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
        html.B("Is Multiome --"),
        " If you're processing a multiome run, select this option.",
        html.Br(), html.Br(),
        html.B("Custom Bcl2fastq flags --"),
        """ Custom bcl2fastq flags to use for the standard samples wrapped in a
        string, with arguments separated by '|' characters, E.g. "--barcode-
        mismatches 2|--minimum-trimmed-read-length ". For a full list of possible flags, see the """,
        html.A(" bcl2fastq documentation.", href="https://support.illumina.com/content/dam/illumina-support/documents/documentation/software_documentation/bcl2fastq/bcl2fastq_letterbooklet_15038058brpmi.pdf", target="_blank"),
        html.Br(), html.Br(),
        html.B("Custom Cellranger flags --"),
        """ Custom cellranger mkfastq flags to use for the 10x samples wrapped in a
        string, with arguments separated by '|' characters, E.g. "--barcode-
        mismatches 2|--delete-undetermined". For a full list of possible flags, see the """,
        html.A("cellranger documentation", href="https://support.10xgenomics.com/single-cell-gene-expression/software/pipelines/latest/using/mkfastq", target="_blank"),
        html.Br(), html.Br(),
        html.B("Custom Bases2fastq flags --"),
        """ Custom bases2fastq flags to use wrapped in a string, with arguments
        separated by ';' characters, E.g. "--i1-cycles 8;--r2-cycles 40 ". For a full list of possible flags, see the """,
        html.A("bases2fastq documentation", href="https://docs.elembio.io/docs/bases2fastq/", target="_blank"),
        html.Br(), html.Br(),
    ], style={"margin-left": "2vw"}),
    html.H4("Prepare Raw Data Tab"),
    html.P([
        "This tab is currently disabled, and will be enabled in a future release, after raw-data processing is added to draugr."
    ], style={"margin-left": "2vw"}),
    html.Br(),
    html.H4("Sushify Tab"),
    html.P([
        html.B("Select Orders to Sushify --"),
        " Select the order(s) for which you'd like to re-trigger sushification. After clicking \"submit\" and confirming your submission, DraugrUI will send a request to the sushi server to begin creating fastqc and fastqscreen reports. Order statuses will be updated at this stage as well. ",
        html.Br(), html.Br(),
    ], style={"margin-left": "2vw"}),
]
