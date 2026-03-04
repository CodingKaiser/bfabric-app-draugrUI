# DraugrUI

User interface for triggering and managing [Draugr](https://gitlab.bfabric.org/Genomics/draugr) (Demultiplexing wRapper And Updated GRiffin) runs at the FGCZ. Built on the [bfabric-web-apps](https://github.com/fgcz/bfabric-web-apps) framework.

## What it does

DraugrUI is launched from B-Fabric when a user selects a sequencing run. It:

1. Reads the run's lane/container structure from B-Fabric
2. Lets the operator select which orders to process and configure Draugr flags
3. Fires an SSH command to the sequencing server to start Draugr in the background
4. Lets the operator trigger FastQC/FastQScreen reports (Sushi pipeline) once demultiplexing is done

---

## Project structure

```
bfabric-app-draugrUI/
├── index.py                    # App entry point: layout, callbacks, and server startup
├── utils/
│   ├── bfabric_utils.py        # B-Fabric wrappers and logger (local credential overrides)
│   ├── components.py           # Domain-specific UI components (lane cards, sidebars, modals)
│   ├── draugr_utils.py         # SSH command builders for Draugr and Sushi pipelines
│   └── run_data.py             # B-Fabric data fetcher: traverses Run → lane → container
├── pyproject.toml              # Dependencies (single bfabric-web-apps dep + dev tools)
└── .env                        # Runtime config: HOST, PORT, APP_TITLE (gitignored)
```

---

## File descriptions

### `index.py`
The main application file. Contains:
- **App initialisation** via `bfabric_web_apps.create_app()`
- **Layout** — banner, header (B-Fabric entity link + View Logs), persistent DMX sidebar, and a flat tab structure (DMX, Raw Data, Fastq Reports, Documentation, Report a Bug)
- **Callbacks** — authentication/token validation, dropdown population, lane card display, modal toggles, Draugr/Sushi command execution, sidebar visibility toggling, and submit-button enable/disable logic

### `utils/bfabric_utils.py`
Wraps the `bfabric` Python library with helpers used throughout the app:
- `get_power_user_wrapper()` — reads credentials from `~/.bfabricpy.yml` for writing log entries
- `get_user_wrapper(token_data)` — builds a wrapper from the token's user credentials for data reads
- `get_logger(token_data)` — creates a Logger that writes audit entries to B-Fabric, using the power user wrapper

### `utils/components.py`
All domain-specific Dash/HTML components:
- `lane_card()` — renders a single sequencing lane as a Bootstrap card
- `default_sidebar` — DMX options: order dropdown, boolean switches (Wizard, Multiome, Skip flags), custom flag inputs
- `sushi_sidebar` — order dropdown + submit button for the Fastq Reports tab
- `modal`, `modal2` — confirmation dialogs shown before executing commands
- `documentation_content` — the HTML content rendered in the Documentation tab

### `utils/draugr_utils.py`
Builds the shell commands executed on remote servers via SSH:
- `generate_draugr_command()` — constructs the full SSH + `nohup` call to start Draugr on the sequencing server (`illumina@<server>`), including all flag options selected in the UI
- `generate_sushi_command()` — checks where the run's dataset file lives on `fgcz-h-082`, then builds two SSH commands: one to `grep` the selected orders into a Sushi bash script and one to execute that script

### `utils/run_data.py`
Fetches run-specific data from B-Fabric that the framework's generic entity read does not expose. Traverses the B-Fabric hierarchy:

```
Run → RunUnit → RunUnitLane → Sample → Container
```

Returns the lane-to-container mapping, server location, and data folder name needed to populate the UI and build the Draugr SSH command.

---

## Setup

### Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) (recommended package manager)
- B-Fabric power-user credentials at `~/.bfabricpy.yml`

### 1. Clone and install

```shell
git clone https://github.com/CodingKaiser/bfabric-app-draugrUI.git
cd bfabric-app-draugrUI
uv sync
```

### 2. Configure

Create a `.env` file in the project root (this file is gitignored):

```
HOST=0.0.0.0
PORT=10101
APP_TITLE=DraugrUI
```

### 3. Run

```shell
uv run python index.py
```

### 4. Trigger the app

Navigate to the B-Fabric test (or production) server, open a sequencing **Run** entity, and click the DraugrUI app link. B-Fabric will send a signed token to the app, which validates it and loads the run data automatically.

---

## Tab overview

| Tab | Purpose |
|---|---|
| **Draugr / DMX** | Configure options and launch a Draugr demultiplexing run |
| **Fastq Reports** | Trigger FastQC and FastQScreen reports via the Sushi pipeline |
| **Documentation** | In-app usage guide for all options and flags |
| **Report a Bug** | Submit a bug report (stored as a log entry in B-Fabric) |

The DMX sidebar (order dropdown, flag switches, custom inputs, submit button) is **persistent** — it stays in the DOM across all tabs so entered values are not lost when switching tabs. On the Documentation tab it swaps the Submit button for a "Go to Submission" button that returns you to DMX with all values intact.
