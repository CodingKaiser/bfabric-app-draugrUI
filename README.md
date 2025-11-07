# draugrUI

User Interface for Draugr invocations on FGCZ cluster

## Deployment 

### 1) Clone your Repo

```shell
git clone https://github.com/CodingKaiser/bfabric-app-draugrUI.git && cd bfabric-app-draugrUI
```

### 2) Installing dependencies

#### Option #1: Use `uv` (**recommended**)

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run

```shell
uv sync
```

#### Option #2: Set up virtual environment & install requirements

2.1) Set up your virtual env

For using virtualenv: 
```shell
python3 -m venv gi_bfabric-app-draugrUI
source gi_bfabric-app-draugrUI/bin/activate
```

For using conda: 

```shell
conda create -n gi_fabric-app-draugrUI pip
conda activate bfabric-app-draugrUI
```

For using mamba: 
```shell
mamba create -n gi_fabric-app-draugrUI pip
conda activate gi_fabric-app-draugrUI
```

2.2) Install remaining dependencies:

```shell
pip install .
``` 

### 3) Create a PARAMS.py file with your host and port!

```python
# PARAMS.py
HOST = "0.0.0.0"
PORT = 8050
DEV = False
CONFIG_FILE_PATH = "~/.bfabricpy.yml"
```

### 4) Run the application 

```shell
python3 index.py
```

or

```shell
uv run index.py
```

### 5) Check it out! 

Visit http://localhost:8050 to see your site in action.
