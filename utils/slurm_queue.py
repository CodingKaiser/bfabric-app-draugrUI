"""
The SLURM queue of draugr runs: submit, list and cancel.

Submission goes through draugr's own submit script, run in draugr's uv
environment. That script is shared with draugr's monitor_runs.py and owns the
rules every draugr job follows: one job named draugr-<server> per instrument
server at a time (--dependency=singleton), and a JSON record of each job's
parameters in JOBS_DIR/jobs/<jobid>.json. This module only calls it, and reads
the queue back from squeue, sacct and those records.

singleton is per SLURM user, so the app must run as the same account as
monitor_runs.py, or the two would not wait for each other.
"""

import json
import os
import subprocess
from pathlib import Path

# The deployed draugr checkout whose bin/slurm/submit.py queues the runs.
DRAUGR_DEPLOY_DIR = "/usr/local/ngseq/opt/draugr"
# Shared with the submit script, which reads the same variable.
JOBS_DIR = Path(os.environ.get("DRAUGR_JOBS_DIR", "/srv/GT/analysis/draugr_slurm"))
JOB_PREFIX = "draugr-"

ACTIVE_STATES = {"PENDING", "RUNNING", "CONFIGURING", "COMPLETING", "SUSPENDED"}


class SlurmError(RuntimeError):
    """A SLURM command failed; the message is its stderr."""


def _run(argv):
    result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode:
        raise SlurmError(result.stderr.strip() or f"{argv[0]} exited with {result.returncode}")
    return result.stdout


def submit(server, run_folder, orders, draugr_args, submitter):
    """Queue a draugr run and return its SLURM job id."""
    argv = [
        "uv", "run", "--frozen", "--directory", DRAUGR_DEPLOY_DIR, "bin/slurm/submit.py",
        "--server", server,
        "--run-folder", run_folder,
        "--source", "ui",
        "--submitter", submitter,
        "--orders", ",".join(str(o) for o in orders),
        "--", *draugr_args,
    ]
    return _run(argv).strip()


def _server(job_name):
    return job_name[len(JOB_PREFIX):]


def parse_squeue(text):
    """Parse `squeue -o '%i|%j|%T|%V|%S|%M|%r|%N|%k'` into job dicts."""
    jobs = []
    for line in text.splitlines():
        jobid, name, state, submitted, started, elapsed, reason, node, comment = line.split("|", 8)
        if not name.startswith(JOB_PREFIX):
            continue
        jobs.append({
            "jobid": jobid,
            "server": _server(name),
            "state": state,
            "submitted": submitted,
            # For a pending job %S is only SLURM's estimate, not a start.
            "started": "" if state == "PENDING" or started in ("N/A", "Unknown") else started,
            "ended": "",
            "elapsed": elapsed,
            "reason": "" if reason == "None" else reason,
            "node": node,
            "exit_code": "",
            # The submit script sets the comment to run=<RUN>, so the run is known
            # even for a job whose parameter record is missing.
            "run": comment[len("run="):] if comment.startswith("run=") else "",
        })
    return jobs


def parse_sacct(text):
    """Parse `sacct -X -n -P --format=JobID,JobName,State,Submit,Start,End,Elapsed,ExitCode`."""
    jobs = []
    for line in text.splitlines():
        jobid, name, state, submitted, started, ended, elapsed, exit_code = line.split("|")
        if not name.startswith(JOB_PREFIX):
            continue
        jobs.append({
            "jobid": jobid,
            "server": _server(name),
            # "CANCELLED by 47717" -> "CANCELLED"
            "state": state.split()[0],
            "submitted": submitted,
            "started": "" if started in ("None", "Unknown") else started,
            "ended": "" if ended in ("None", "Unknown") else ended,
            "elapsed": elapsed,
            "reason": "",
            "node": "",
            "exit_code": exit_code,
            "run": "",
        })
    return jobs


def read_sidecar(jobid, jobs_dir=None):
    """The parameter record the submit script wrote, or None for a job it did not submit."""
    path = (jobs_dir or JOBS_DIR) / "jobs" / f"{jobid}.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def merge_jobs(active, history, jobs_dir=None):
    """
    Combine squeue and sacct rows with the parameter records.

    squeue wins for jobs it still lists, since only it knows why a pending job is
    waiting. Each pending job gets its position in its server's queue, by
    submission time, with 1 next to run.
    """
    by_id = {job["jobid"]: job for job in history}
    by_id.update({job["jobid"]: job for job in active})

    jobs = []
    for job in by_id.values():
        record = read_sidecar(job["jobid"], jobs_dir) or {}
        jobs.append({
            **job,
            "run": record.get("run") or job["run"],
            "orders": record.get("orders", []),
            "source": record.get("source", ""),
            "submitter": record.get("submitter", ""),
            "draugr_args": record.get("draugr_args"),
            "log": record.get("log", ""),
            "active": job["state"] in ACTIVE_STATES,
            "position": None,
        })

    pending = sorted(
        (job for job in jobs if job["state"] == "PENDING"),
        key=lambda job: (job["server"], job["submitted"]),
    )
    counter = {}
    for job in pending:
        counter[job["server"]] = counter.get(job["server"], 0) + 1
        job["position"] = counter[job["server"]]

    # Active jobs first, then newest first.
    jobs.sort(key=lambda job: job["submitted"], reverse=True)
    jobs.sort(key=lambda job: not job["active"])
    return jobs


def list_jobs(days=7):
    """Active draugr jobs and those that ended in the last `days` days, newest first."""
    active = parse_squeue(_run(["squeue", "--me", "-h", "-o", "%i|%j|%T|%V|%S|%M|%r|%N|%k"]))
    history = parse_sacct(_run([
        "sacct", "-X", "-n", "-P", "-S", f"now-{days}days",
        "--format=JobID,JobName,State,Submit,Start,End,Elapsed,ExitCode",
    ]))
    return merge_jobs(active, history)


def active_for_run(jobs, run_name):
    """The pending and running jobs for one run."""
    return [job for job in jobs if job["active"] and job["run"] == run_name]


def cancel(jobid):
    """
    Cancel a draugr job: a pending one leaves the queue, a running one is stopped
    on the server too (draugr's job script handles that on SIGTERM).

    Only jobs currently listed as active draugr jobs can be cancelled, so a
    stale or forged id from the browser cannot reach anything else.
    """
    jobid = str(jobid)
    if not any(job["jobid"] == jobid and job["active"] for job in list_jobs(days=0)):
        raise SlurmError(f"Job {jobid} is not a queued or running draugr job.")
    _run(["scancel", jobid])
