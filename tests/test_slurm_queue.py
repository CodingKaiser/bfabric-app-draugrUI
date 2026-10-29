import json
import subprocess

import pytest

from utils import slurm_queue

# Real output shapes, captured on the cluster.
SQUEUE = "\n".join([
    "500|draugr-fgcz-s-023|RUNNING|2026-10-20T09:00:00|2026-10-20T09:00:05|1:02:03|None|fgcz-c-041|run=261016_X570",
    "502|draugr-fgcz-s-023|PENDING|2026-10-20T09:30:00|N/A|0:00|Dependency||run=261017_X571",
    "501|draugr-fgcz-s-023|PENDING|2026-10-20T09:10:00|2026-10-20T12:00:00|0:00|Dependency||run=261016_X570",
    "503|draugr-fgcz-s-034|PENDING|2026-10-20T09:40:00|N/A|0:00|Priority||(null)",
    "999|methods_dataset_116073.sh|PENDING|2026-10-16T09:12:25|N/A|0:00|Dependency||(null)",
])
SACCT = "\n".join([
    "490|draugr-fgcz-s-025|CANCELLED by 47717|2026-10-19T09:00:00|2026-10-19T09:00:10|2026-10-19T09:05:00|00:04:50|0:0",
    "491|draugr-fgcz-s-025|FAILED|2026-10-19T10:00:00|2026-10-19T10:00:10|2026-10-19T11:00:00|00:59:50|2:0",
    "500|draugr-fgcz-s-023|RUNNING|2026-10-20T09:00:00|2026-10-20T09:00:05|Unknown|01:02:03|0:0",
    "998|other-job|COMPLETED|2026-10-19T09:00:00|2026-10-19T09:00:10|2026-10-19T09:05:00|00:04:50|0:0",
])


@pytest.fixture
def jobs_dir(tmp_path):
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "500.json").write_text(json.dumps({
        "jobid": "500", "run": "261016_X570", "orders": ["43291"], "source": "ui",
        "submitter": "falkonoe", "draugr_args": ["--x"], "log": "/l/500.out",
    }))  # fmt: skip
    return tmp_path


def test_only_draugr_jobs_are_listed():
    ids = {j["jobid"] for j in slurm_queue.parse_squeue(SQUEUE) + slurm_queue.parse_sacct(SACCT)}
    assert "999" not in ids and "998" not in ids


def test_merge_prefers_squeue_and_reads_parameters(jobs_dir):
    jobs = slurm_queue.merge_jobs(
        slurm_queue.parse_squeue(SQUEUE), slurm_queue.parse_sacct(SACCT), jobs_dir
    )
    by_id = {j["jobid"]: j for j in jobs}

    running = by_id["500"]
    assert running["node"] == "fgcz-c-041"  # only squeue knows the node
    assert running["submitter"] == "falkonoe" and running["orders"] == ["43291"]

    # No parameter record: the run still comes from the job comment.
    assert by_id["502"]["run"] == "261017_X571"
    assert by_id["502"]["draugr_args"] is None

    assert by_id["490"]["state"] == "CANCELLED"
    assert by_id["491"]["exit_code"] == "2:0"
    # A pending job's %S is an estimate, not a start time.
    assert by_id["501"]["started"] == ""


def test_queue_position_is_per_server_by_submission(jobs_dir):
    jobs = slurm_queue.merge_jobs(slurm_queue.parse_squeue(SQUEUE), [], jobs_dir)
    position = {j["jobid"]: j["position"] for j in jobs}
    assert position == {"500": None, "501": 1, "502": 2, "503": 1}


def test_active_jobs_come_first(jobs_dir):
    jobs = slurm_queue.merge_jobs(
        slurm_queue.parse_squeue(SQUEUE), slurm_queue.parse_sacct(SACCT), jobs_dir
    )
    states = [j["active"] for j in jobs]
    assert states == sorted(states, reverse=True)


def test_active_for_run(jobs_dir):
    jobs = slurm_queue.merge_jobs(
        slurm_queue.parse_squeue(SQUEUE), slurm_queue.parse_sacct(SACCT), jobs_dir
    )
    assert {j["jobid"] for j in slurm_queue.active_for_run(jobs, "261016_X570")} == {"500", "501"}


def test_submit_raises_with_stderr(monkeypatch):
    def fake_run(argv, **_):
        return subprocess.CompletedProcess(argv, 1, "", "sbatch: error: invalid partition\n")

    monkeypatch.setattr(slurm_queue.subprocess, "run", fake_run)
    with pytest.raises(slurm_queue.SlurmError, match="invalid partition"):
        slurm_queue.submit("fgcz-s-023", "/export/local/data/R", [1], ["--x"], "falkonoe")


def test_submit_passes_draugr_args_after_separator(monkeypatch):
    seen = {}

    def fake_run(argv, **_):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, "4242\n", "")

    monkeypatch.setattr(slurm_queue.subprocess, "run", fake_run)
    args = ["--bases-mask=-y36n*", "--x"]
    assert slurm_queue.submit("fgcz-s-023", "/export/local/data/R", [1, 2], args, "falkonoe") == "4242"
    argv = seen["argv"]
    assert argv[argv.index("--") + 1 :] == args
    assert argv[argv.index("--orders") + 1] == "1,2"


def test_cancel_refuses_jobs_that_are_not_active_draugr_jobs(monkeypatch):
    monkeypatch.setattr(slurm_queue, "list_jobs", lambda days=7: [{"jobid": "500", "active": True}])
    called = []
    monkeypatch.setattr(slurm_queue, "_run", lambda argv: called.append(argv))
    with pytest.raises(slurm_queue.SlurmError):
        slurm_queue.cancel("999")
    assert called == []
    slurm_queue.cancel("500")
    assert called == [["scancel", "500"]]
