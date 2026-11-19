import json
import shlex
import subprocess

import pytest

from utils import draugr_queue as dq

# Shaped like `draugr-queue status` output.
STATUS = {
    "server": "fgcz-s-023",
    "jobs": [
        {"tsp_id": 9, "state": "queued", "key": "k9", "run": "R1", "log": None,
         "draugr_args": ["--reprocess-orders", "1,2", "--skip-demux"], "after": [{"tsp_id": 7}]},
        {"tsp_id": 7, "state": "queued", "key": "k7", "run": "R2", "log": None,
         "draugr_args": ["--reprocess-orders=3"], "after": []},
        {"tsp_id": 4, "state": "running", "key": "k4", "run": "R1", "log": "/l/4",
         "draugr_args": ["--logger-rep", "/x"], "after": []},
        {"tsp_id": 2, "state": "finished", "key": "k2", "run": "R1", "log": "/l/2",
         "exit_code": 0, "draugr_args": [], "after": []},
    ],
    "lost": [{"tsp_id": 1, "key": "k1", "run": "R1", "interrupted": False, "draugr_args": ["--x"]}],
    "history": [
        {"event": "submitted", "key": "k2", "run": "R1", "submitted_at": "2026-11-17T09:00:00"},
        {"event": "finished", "key": "k2", "run": "R1", "exit_code": 0, "finished_at": "2026-11-17T10:00:00"},
        {"event": "submitted", "key": "k3", "run": "R1", "draugr_args": ["--reprocess-orders", "5"]},
        {"event": "stopped", "key": "k3", "run": "R1", "stopped_by": "falkonoe", "stopped_at": "2026-11-17T11:00:00"},
        {"event": "finished", "key": "k3", "run": "R1", "exit_code": -1, "finished_at": "2026-11-17T11:00:01"},
        {"event": "submitted", "key": "k5", "run": "R2"},
        {"event": "removed", "key": "k5", "run": "R2", "removed_at": "2026-11-17T08:00:00"},
        {"event": "submitted", "key": "k4", "run": "R1"},
        {"event": "started", "key": "k4", "run": "R1"},
    ],
}  # fmt: skip


@pytest.fixture
def state():
    return dq.annotate(json.loads(json.dumps(STATUS)))


@pytest.fixture
def ssh(monkeypatch):
    """Capture the ssh argv and answer with a given CompletedProcess."""
    calls = []

    def answer(returncode=0, stdout="", stderr=""):
        def fake_run(argv, **_):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

        monkeypatch.setattr(dq.subprocess, "run", fake_run)
        return calls

    return answer


def _remote(argv):
    """The command the server's shell runs, as it splits it."""
    assert argv[:5] == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    return shlex.split(argv[-1])


def test_submit_quotes_draugr_args_once_for_the_remote_shell(ssh):
    calls = ssh(stdout="7\n")
    args = [
        "--bases-mask=-y36n*,I8n*",
        "--custom-bclconvert-flags=--tiles s_1;--x 2",
        "--reprocess-orders",
        "1,2",
    ]
    assert (
        dq.submit("fgcz-s-023", "/export/local/data/R1", args, "falkonoe", after=[4, 5])
        == 7
    )

    assert calls[0][5] == "illumina@fgcz-s-023"
    remote = _remote(calls[0])
    assert remote[: remote.index("draugr-queue")] == [
        dq.UV, "run", "--frozen", "--directory", dq.DRAUGR_DIR,
    ]  # fmt: skip
    assert remote[remote.index("draugr-queue") + 1 : remote.index("--")] == [
        "submit", "--run-folder", "/export/local/data/R1", "--source", "ui", "--submitter", "falkonoe",
        "--after", "4", "--after", "5",
    ]  # fmt: skip
    assert remote[remote.index("--") + 1 :] == args


def test_refusal_reports_stderr(ssh):
    ssh(returncode=1, stderr="draugr-queue: job 3 has already failed\n")
    with pytest.raises(dq.QueueError, match="already failed"):
        dq.submit("fgcz-s-023", "/export/local/data/R1", [], "falkonoe", after=[3])


def test_connection_failure_names_the_server(ssh):
    ssh(returncode=255, stderr="ssh: connect to host fgcz-s-023: Connection refused")
    with pytest.raises(dq.QueueError, match="Could not connect to fgcz-s-023"):
        dq.status("fgcz-s-023")


def test_stop_passes_who_stopped_it(ssh):
    calls = ssh()
    dq.stop("fgcz-s-023", "k4", by="falkonoe")
    remote = _remote(calls[0])
    assert remote[remote.index("draugr-queue") + 1 :] == [
        "stop",
        "k4",
        "--by",
        "falkonoe",
    ]


def test_not_running_is_recognised():
    assert dq.not_running(dq.QueueError("draugr-queue: job k4 is not running"))
    assert not dq.not_running(dq.QueueError("draugr-queue: no job with key k4"))


def test_status_is_parsed_and_annotated(ssh):
    calls = ssh(stdout=json.dumps(STATUS))
    state = dq.status("fgcz-s-023", history=0)
    remote = _remote(calls[0])
    assert remote[remote.index("draugr-queue") + 1 :] == ["status", "--history", "0"]
    assert [j["key"] for j in dq.active_jobs(state)] == ["k4", "k7", "k9"]


def test_queue_position_follows_tsp_id(state):
    position = {j["key"]: j["position"] for j in state["jobs"]}
    assert position == {"k7": 1, "k9": 2, "k4": None, "k2": None}


def test_job_orders():
    assert dq.job_orders(["--reprocess-orders", "1,2"]) == ["1", "2"]
    assert dq.job_orders(["--reprocess-orders=3"]) == ["3"]
    assert dq.job_orders(["--skip-demux"]) is None
    assert dq.job_orders(None) is None


def test_active_for_run(state):
    assert [j["key"] for j in dq.active_for_run(state, "R1")] == ["k4", "k9"]


def test_past_jobs_join_history_on_key(state):
    past = {j["key"]: j for j in state["past"]}
    # Still running (k4) is not past; finished and removed jobs are, newest first.
    assert [j["key"] for j in state["past"]] == ["k3", "k2", "k5"]
    assert (
        past["k2"]["submitted_at"] == "2026-11-17T09:00:00"
        and past["k2"]["exit_code"] == 0
    )
    assert past["k3"]["orders"] == ["5"]


def test_stopped_goes_by_the_exit_code(state):
    past = {j["key"]: j for j in state["past"]}
    assert dq.was_stopped(past["k3"])
    # Finished on its own just as it was stopped: its real exit code counts.
    assert not dq.was_stopped({"exit_code": 0, "stopped_by": "falkonoe"})


def test_find_searches_current_lost_and_past(state):
    assert dq.find(state, "k9")["tsp_id"] == 9
    assert dq.find(state, "k1")["interrupted"] is False
    assert dq.find(state, "k5")["event"] == "removed"
    assert dq.find(state, "nope") is None


@pytest.mark.parametrize(
    "stdout", ["", "Welcome to fgcz-s-023\n{}", '{"server": "fgcz-s-023"}']
)
def test_unreadable_status_is_a_queue_error(ssh, stdout):
    # Callers only catch QueueError; anything else would fail the callback.
    ssh(stdout=stdout)
    with pytest.raises(dq.QueueError, match="Unreadable"):
        dq.status("fgcz-s-023")
