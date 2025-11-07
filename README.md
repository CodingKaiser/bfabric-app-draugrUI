# bfabric-app-template
Template Application for Bfabric Webapp Concept (written in Python3) 

## Deployment 

1) Fork the Repo 

2) Clone your Repo

```shell
git clone https://github.com/your/bfabric-app-template/fork.git && cd bfabric-app-template
```

3) Installing dependencies

#### Option #1: Use `uv` (**recommended**)

Install (uv)[https://docs.astral.sh/uv/getting-started/installation/] and run

```shell
uv sync
```

#### Option #2: Set up virtual environment & install requirements

3.1) 

For using virtualenv: 
```shell
python3 -m venv my_app_1
source my_app_1/bin/activate
```

For using conda: 

```shell
conda create -n my_app_1 pip
conda activate my_app_1
```

For using mamba: 
```shell
mamba create -n my_app_1 pip
conda activate my_app_1
```

3.2) Install remaining dependencies:

```shell
pip install .
``` 

4) Create a PARAMS.py file with your host and port!

```python
# PARAMS.py
HOST = "0.0.0.0"
PORT = 8050
DEV = False
CONFIG_FILE_PATH = "~/.bfabricpy.yml"
```

5) Run the application 

```shell
python3 index.py
```

or

```shell
uv run index.py
```

6) Check it out! 

Visit http://localhost:8050 to see your site in action.
