"""
The draugr queue on each instrument server: submit, status, remove, stop, log.

Every draugr run goes through a task spooler (tsp) queue with one slot on the
instrument server that holds the data, so a server runs one draugr job at a
time. Cron, the command line and this app all submit to it through draugr's
`draugr-queue` command, which this module calls over ssh as illumina. The
queue and its history on the server are the only record of jobs; this app
keeps none of its own.

Each server has its own queue: tsp ids and --after refer to that server only,
and a tsp id is not unique over time (it restarts with the tsp server), so
jobs are identified by their `key`.
"""

import json
import shlex
import subprocess

# There is no `module` command in a non-interactive ssh session, so uv is called
# by its full path. Bump it together with the Dev/uv module on the servers.
UV = "/usr/local/ngseq/packages/Dev/uv/0.13.7/uv"
DRAUGR_DIR = "/export/local/analyses/draugr_exec"
DATA_DIR = "/export/local/data"
# How much of a job's console output the Log dialog shows.
LOG_TAIL_LINES = 200
# draugr deletes job logs older than this (LOG_RETENTION_DAYS in draugr-queue).
LOG_RETENTION_DAYS = 60

# What a finished job's exit code means.
EXIT_CODES = {
    0: "succeeded",
    1: "draugr failed",
    2: "draugr rejected its arguments",
    98: "failed before draugr started (see the job log)",  # module load or the on-start step
    99: "not run: a job it waited for failed or was removed",
    -1: "killed",  # draugr-queue stop, or tsp -k on the server
    -113: "killed",  # how jobs stopped before draugr's fix ended; they stay in the history
}


class QueueError(RuntimeError):
    """A draugr-queue call failed or was refused; the message says why."""


def _ssh(server, remote, timeout):
    """Run `remote` (an argv list) on the server as illumina and return its stdout."""
    # ssh joins its arguments into one string that the server's shell parses
    # again, so the argv is quoted exactly once, here, and no local shell is used.
    argv = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        f"illumina@{server}", shlex.join(remote),
    ]  # fmt: skip
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise QueueError(f"{server} did not answer within {timeout} s.") from None
    except OSError as e:
        raise QueueError(f"Could not run ssh: {e}") from None
    if result.returncode == 255:
        raise QueueError(f"Could not connect to {server}: {result.stderr.strip()}")
    if result.returncode:
        raise QueueError(
            result.stderr.strip() or f"exited with {result.returncode} on {server}"
        )
    return result.stdout


def _draugr_queue(server, *args, timeout=60):
    return _ssh(
        server,
        [
            UV,
            "run",
            "--frozen",
            "--no-sync",
            "--directory",
            DRAUGR_DIR,
            "draugr-queue",
            *args,
        ],
        timeout,
    )


def submit(server, run_folder, draugr_args, submitter, after=()):
    """
    Queue a draugr run on the server and return its tsp id.

    run_folder is the absolute path of the run folder; draugr_args must not
    contain --run-folder. With `after`, the job runs draugr only if each of
    those jobs (tsp ids on the same server) succeeded.
    """
    args = [
        "submit",
        "--run-folder",
        run_folder,
        "--source",
        "ui",
        "--submitter",
        submitter,
    ]
    for tsp_id in after:
        args += ["--after", str(tsp_id)]
    out = _draugr_queue(server, *args, "--", *draugr_args)
    try:
        return int(out.strip())
    except ValueError:
        raise QueueError(f"draugr-queue printed no job id: {out.strip()!r}") from None


def status(server, history=50):
    """The server's queue (jobs, lost, history) with each job's orders and queue position."""
    out = _draugr_queue(server, "status", "--history", str(history), timeout=30)
    # Callers only handle QueueError, so a reply that is not the expected JSON
    # (e.g. a login banner on stdout) must not escape as anything else.
    try:
        return annotate(json.loads(out))
    except (ValueError, KeyError, TypeError) as e:
        raise QueueError(
            f"Unreadable draugr-queue status from {server}: {e!r}"
        ) from None


def remove(server, key):
    """Take a queued job off the queue, or clear a lost one."""
    _draugr_queue(server, "remove", key)


def stop(server, key, by):
    """
    Kill a running job (draugr and bcl-convert); it then finishes with exit code -1.

    Raises QueueError, among other reasons, if the job is no longer running:
    see not_running().
    """
    _draugr_queue(server, "stop", key, "--by", by)


def not_running(error):
    """Whether a stop was refused only because the job had already ended."""
    return "is not running" in str(error)


def already_removed(error):
    """Whether a remove was refused only because the job had already been removed."""
    return "has already been removed" in str(error)


def log_deleted(error):
    """Whether a log could not be read only because draugr had deleted it."""
    return "No such file or directory" in str(error)


def log_tail(server, log, lines=LOG_TAIL_LINES):
    """The last lines of a job's console output; works while the job runs."""
    return _ssh(server, ["tail", "-n", str(lines), log], timeout=30)


# ---- Reading the status ----


def job_orders(draugr_args):
    """The orders a job reprocesses, or None for a full run of every order."""
    args = draugr_args or []
    for i, arg in enumerate(args):
        if arg == "--reprocess-orders" and i + 1 < len(args):
            return args[i + 1].split(",")
        if arg.startswith("--reprocess-orders="):
            return arg.split("=", 1)[1].split(",")
    return None


def past_jobs(history):
    """
    One record per job that has finished or been removed, newest first.

    History events are joined on the job's key, the later event's fields
    winning, so each record carries everything known about the job; a stopped
    job's `finished` event follows its `stopped` one, keeping `stopped_by`.
    """
    merged = {}
    for event in history:
        merged.setdefault(event["key"], {}).update(event)
    ended = [job for job in merged.values() if job["event"] in ("finished", "removed")]
    for job in ended:
        job["orders"] = job_orders(job.get("draugr_args"))
    ended.sort(
        key=lambda job: job.get("finished_at") or job.get("removed_at") or "",
        reverse=True,
    )
    return ended


def annotate(state):
    """
    Add each job's orders, each queued job's place in the queue (1 runs next),
    and the ended jobs from the history as `past`.
    """
    queued = sorted(
        (j for j in state["jobs"] if j["state"] == "queued"), key=lambda j: j["tsp_id"]
    )
    for position, job in enumerate(queued, start=1):
        job["position"] = position
    for job in state["jobs"] + state["lost"]:
        job.setdefault("position", None)
        job["orders"] = job_orders(job.get("draugr_args"))
    state["past"] = past_jobs(state.get("history", []))
    return state


def active_jobs(state):
    """Running and queued jobs, the running one first, then in queue order."""
    return sorted(
        (j for j in state["jobs"] if j["state"] in ("running", "queued")),
        key=lambda j: (j["state"] != "running", j["tsp_id"]),
    )


def active_for_run(state, run):
    """The running and queued jobs for one run folder."""
    return [job for job in active_jobs(state) if job["run"] == run]


def was_stopped(job):
    """
    Whether a finished job was stopped with draugr-queue stop.

    Goes by the exit code: a job that finished on its own just as it was
    stopped has a stopped event but its real exit code.
    """
    return job.get("exit_code") in (-1, -113) and bool(job.get("stopped_by"))


def find(state, key):
    """The job with this key among current, lost and past jobs, or None."""
    for job in state["jobs"] + state["lost"] + state["past"]:
        if job["key"] == key:
            return job
    return None
