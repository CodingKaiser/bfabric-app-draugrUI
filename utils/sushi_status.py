"""
Sushification status of each order on a run.

An order moves through these states:

  Not demultiplexed  draugr has not written a block for it into the run's
                     <RUN>_sushification.sh yet
  Ready              the block exists, but no dataset is registered in B-Fabric
  Submitted          sushified from this app recently and still not registered.
                     Registration is asynchronous, and sushifying again in the
                     meantime registers a duplicate dataset
  Sushified          B-Fabric holds a dataset for the order and the run

An order with a pending or running draugr job shows as being demultiplexed
instead, whatever its state before.

Sushification is checked against B-Fabric, not by where the script sits:
scripts are left in place after a successful run, and the script's trailing
`mv <RUN>* processed` runs even when a block failed.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from utils import slurm_queue
from utils.bfabric_utils import get_logger, get_user_wrapper

DATASETS_DIR = Path("/srv/GT/analysis/datasets")
# Where draugr writes the script (ISeq for QC runs), and where it moves itself.
SCRIPT_DIRS = [DATASETS_DIR, DATASETS_DIR / "ISeq", DATASETS_DIR / "processed"]
SUBMITTED_WINDOW = timedelta(hours=1)

NOT_DEMUXED = "Not demultiplexed"
READY = "Ready"
SUBMITTED = "Submitted"
SUSHIFIED = "Sushified"
DEMUXING = "Demultiplexing"


def find_sushi_script(run_name, dirs=None):
    """Path of the run's <RUN>_sushification.sh, or None if draugr has not written one."""
    for folder in dirs or SCRIPT_DIRS:
        path = folder / f"{run_name}_sushification.sh"
        if path.is_file():
            return path
    return None


def demuxed_orders(script_text, run_name):
    """Order ids that have a dataset block for this run in the sushification script."""
    orders = set()
    for name in re.findall(r"--dataset_name (\S+)", script_text):
        match = re.fullmatch(rf"o(\d+)_.*_{re.escape(run_name)}", name)
        if match:
            orders.add(match.group(1))
    return orders


def matching_dataset(datasets, order_id, run_name):
    """
    The B-Fabric dataset registered for this order and run, if any.

    Its name is the script's dataset name, o<order>_<instrument>_<date>_<RUN>,
    with the SUSHI dataset id appended, so match the pattern, not the exact name.
    """
    pattern = re.compile(rf"o{order_id}_.*_{re.escape(run_name)}(_\d+)?")
    for dataset in datasets:
        if pattern.fullmatch(dataset.get("name", "")):
            return dataset
    return None


def record_submission(run_name, orders, submitter, jobs_dir=None):
    """Note that orders were sushified from the app, for the Submitted status."""
    folder = (jobs_dir or slurm_queue.JOBS_DIR) / "sushify"
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    record = {
        "run": run_name,
        "orders": [str(o) for o in orders],
        "submitter": submitter,
        "submitted_at": now.isoformat(timespec="seconds"),
    }
    (folder / f"{run_name}_{now:%Y%m%dT%H%M%S}.json").write_text(json.dumps(record, indent=2))


def recent_submissions(run_name, now=None, jobs_dir=None):
    """Order id -> time it was last sushified from the app, within SUBMITTED_WINDOW."""
    now = now or datetime.now()
    folder = (jobs_dir or slurm_queue.JOBS_DIR) / "sushify"
    submitted = {}
    for path in sorted(folder.glob(f"{run_name}_*.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        # The glob also matches runs whose name merely starts with this one.
        if record.get("run") != run_name:
            continue
        when = datetime.fromisoformat(record["submitted_at"])
        if now - when <= SUBMITTED_WINDOW:
            for order in record["orders"]:
                submitted[order] = record["submitted_at"]
    return submitted


def derive_statuses(orders, run_name, demuxed, datasets_by_order, submissions, demuxing):
    """
    One status row per order. Pure, so it can be tested without B-Fabric or files.

    Args:
        orders: order ids on the run.
        demuxed: order ids with a block in the sushification script.
        datasets_by_order: order id -> B-Fabric datasets in that order's container.
        submissions: order id -> time it was last sushified from the app.
        demuxing: order ids in a pending or running draugr job.
    """
    rows = []
    for order in (str(o) for o in orders):
        dataset = matching_dataset(datasets_by_order.get(order, []), order, run_name)
        if order in demuxing:
            status = DEMUXING
        elif dataset:
            status = SUSHIFIED
        elif order in submissions:
            status = SUBMITTED
        elif order in demuxed:
            status = READY
        else:
            status = NOT_DEMUXED
        rows.append({
            "order": order,
            "status": status,
            "dataset_id": dataset.get("id") if dataset else None,
            "dataset_name": dataset.get("name") if dataset else None,
            "submitted_at": submissions.get(order),
        })
    return rows


def fetch_datasets(token_data, orders):
    """Order id -> datasets in that order's container, read with the user's permissions."""
    if not orders:
        return {}
    L = get_logger(token_data)
    datasets = L.logthis(
        api_call=get_user_wrapper(token_data).read,
        endpoint="dataset",
        obj={"containerid": [str(o) for o in orders]},
        max_results=None,
        flush_logs=True,
    )
    by_order = {}
    for dataset in datasets:
        container = str(dataset.get("container", {}).get("id", ""))
        by_order.setdefault(container, []).append(dataset)
    return by_order


def order_statuses(token_data, run_name, run_folder, orders, jobs):
    """
    Status rows for every order on the run, from the script, B-Fabric, the app and the queue.

    run_name is the B-Fabric run name (X570), which names the script and the
    datasets; run_folder is the run's data folder, which names its draugr jobs.
    """
    script = find_sushi_script(run_name)
    demuxed = demuxed_orders(script.read_text(), run_name) if script else set()
    demuxing = {
        str(order)
        for job in slurm_queue.active_for_run(jobs, run_folder)
        for order in job["orders"]
    }
    return derive_statuses(
        orders,
        run_name,
        demuxed,
        fetch_datasets(token_data, orders),
        recent_submissions(run_name),
        demuxing,
    )
