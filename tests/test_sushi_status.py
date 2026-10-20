import json
from datetime import datetime, timedelta
from pathlib import Path

from utils import sushi_status as ss

FIXTURES = Path(__file__).parent / "fixtures"


def test_demuxed_orders_from_real_script():
    text = (FIXTURES / "X570_sushification.sh").read_text()
    assert ss.demuxed_orders(text, "X570") == {"43291", "43383"}


def test_demuxed_orders_needs_the_exact_run_name():
    # X57 must not pick up X570's datasets.
    text = (FIXTURES / "X570_sushification.sh").read_text()
    assert ss.demuxed_orders(text, "X57") == set()


def test_find_sushi_script_prefers_the_first_folder(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    for folder in (first, second):
        folder.mkdir()
        (folder / "X570_sushification.sh").write_text("")
    (second / "X57_sushification.sh").write_text("")
    assert ss.find_sushi_script("X570", [first, second]) == first / "X570_sushification.sh"
    assert ss.find_sushi_script("X57", [first, second]) == second / "X57_sushification.sh"
    assert ss.find_sushi_script("X999", [first, second]) is None


def test_matching_dataset_allows_the_sushi_id_suffix():
    datasets = [
        {"id": 1, "name": "o43291_Fastqc"},
        {"id": 2, "name": "o43291_NovaSeq_261016_X5700_70001"},
        {"id": 3, "name": "o43291_NovaSeq_261016_X570_70002"},
    ]
    assert ss.matching_dataset(datasets, "43291", "X570")["id"] == 3
    assert ss.matching_dataset(datasets, "43383", "X570") is None


def test_derive_statuses_covers_every_state():
    rows = ss.derive_statuses(
        orders=[1, 2, 3, 4, 5],
        run_name="X570",
        demuxed={"2", "3", "4", "5"},
        datasets_by_order={
            "4": [{"id": 70, "name": "o4_NovaSeq_261016_X570_70"}],
            "5": [{"id": 71, "name": "o5_NovaSeq_261016_X570_71"}],
        },
        submissions={"3": "2026-10-20T10:00:00"},
        demuxing={"5"},
    )
    assert [r["status"] for r in rows] == [
        ss.NOT_DEMUXED,
        ss.READY,
        ss.SUBMITTED,
        ss.SUSHIFIED,
        ss.DEMUXING,  # an active draugr job outranks an earlier sushification
    ]
    assert rows[3]["dataset_id"] == 70


def test_recent_submissions_expire_and_ignore_other_runs(tmp_path):
    now = datetime(2026, 10, 20, 12, 0, 0)
    folder = tmp_path / "sushify"
    folder.mkdir()
    for name, run, when, orders in [
        ("X570_a.json", "X570", now - timedelta(minutes=10), ["1"]),
        ("X570_b.json", "X570", now - timedelta(hours=3), ["2"]),
        ("X5700_c.json", "X5700", now, ["3"]),
    ]:
        (folder / name).write_text(json.dumps({
            "run": run, "orders": orders, "submitted_at": when.isoformat(timespec="seconds"),
        }))  # fmt: skip
    assert set(ss.recent_submissions("X570", now=now, jobs_dir=tmp_path)) == {"1"}


def test_record_then_read_submission(tmp_path):
    ss.record_submission("X570", [43291], "falkonoe", jobs_dir=tmp_path)
    assert set(ss.recent_submissions("X570", jobs_dir=tmp_path)) == {"43291"}
