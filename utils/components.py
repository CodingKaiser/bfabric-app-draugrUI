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

def lane_card(lane_position, container_ids, highlight=False):
    card_content = [
        dbc.CardHeader(f"Lane {lane_position}"),
        dbc.CardBody(
            [html.P("Container IDs:")] + [html.H5(name) for name in container_ids]
            if container_ids
            else html.P("[None Assigned]", style={"color": "gray"})
        ),
    ]
    style = {"max-width": "25vw", "margin": "10px"}
    if highlight:
        style["border"] = "4px solid #007bff"
        style["background-color"] = "rgba(0, 123, 255, 0.1)"
    
    return dbc.Card(card_content, style=style)


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

def _instrument_section(title, note, colour, children):
    """Box a group of instrument-specific inputs so it reads as its own unit."""
    return html.Div(
        [
            html.P(
                title,
                style={"font-weight": "bold", "margin-bottom": "2px", "color": colour},
            ),
            html.P(
                note,
                style={"font-size": "0.7em", "color": "#666", "margin-bottom": "8px"},
            ),
        ] + children,
        style={
            "border": f"2px solid {colour}",
            "border-radius": "6px",
            "background-color": "rgba(0, 0, 0, 0.03)",
            "padding": "10px",
            "margin-top": "8px",
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
        dbc.Input(value="", placeholder='Custom bclconvert flags', id='bclconvert-input'),
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
                    style={"width": "12vw", "font-size": "0.8em"},
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
        dbc.Input(value="", placeholder='Custom Bases2fastq flags', id='bases2fastq-input'),
    ],
)

default_sidebar = [
    html.P("Select Orders to DMX", id="sidebar_text"),
    dcc.Dropdown([], id='draugr-dropdown', multi=True),
    html.Br(),
    html.Div([_label("Disable Wizard", "tip-disable-wizard"),  daq.BooleanSwitch(id='disable-wizard', on=False)], style=_switch_row_style),
    html.Div([_label("Skip RawQC",    "tip-skip-raw-qc"),daq.BooleanSwitch(id='skip-raw-qc', on=True)], style=_switch_row_style),
    html.Br(),
    illumina_specific_section,
    element_specific_section,
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
        dbc.ModalHeader(dbc.ModalTitle("Ready to Sushify?")),
        dbc.ModalBody("Are you sure you're ready to sushify?"),
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
    ], style={"margin-left": "2vw"}),
        html.H4("Sushify Tab"),
    html.P([
        html.B("Select Orders to Sushify --"),
        " Select the order(s) for which you'd like to re-trigger sushification. After clicking \"submit\" and confirming your submission, DraugrUI will send a request to the sushi server to begin creating fastqc and fastqscreen reports. Order statuses will be updated at this stage as well. ",
        html.Br(), html.Br(),
    ], style={"margin-left": "2vw"}),
]
