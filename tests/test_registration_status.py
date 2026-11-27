import json
from datetime import datetime, timedelta
from pathlib import Path

from utils import registration_status as ss

FIXTURES = Path(__file__).parent / "fixtures"


def test_demuxed_orders_from_real_script():
    text = (FIXTURES / "X570_sushification.sh").read_text()
    assert ss.demuxed_orders(text, "X570") == {"12345", "12399"}


def test_demuxed_orders_needs_the_exact_run_name():
    # X57 must not pick up X570's datasets.
    text = (FIXTURES / "X570_sushification.sh").read_text()
    assert ss.demuxed_orders(text, "X57") == set()


def test_find_registration_script_prefers_the_first_folder(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    for folder in (first, second):
        folder.mkdir()
        (folder / "X570_sushification.sh").write_text("")
    (second / "X57_sushification.sh").write_text("")
    assert (
        ss.find_registration_script("X570", [first, second])
        == first / "X570_sushification.sh"
    )
    assert (
        ss.find_registration_script("X57", [first, second])
        == second / "X57_sushification.sh"
    )
    assert ss.find_registration_script("X999", [first, second]) is None


def test_matching_dataset_allows_the_sushi_id_suffix():
    datasets = [
        {"id": 1, "name": "o12345_Fastqc"},
        {"id": 2, "name": "o12345_NovaSeq_261016_X5700_70001"},
        {"id": 3, "name": "o12345_NovaSeq_261016_X570_70002"},
    ]
    assert ss.matching_dataset(datasets, "12345", "X570")["id"] == 3
    assert ss.matching_dataset(datasets, "12399", "X570") is None


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
        ss.REGISTERED,
        ss.DEMUXING,  # an active draugr job outranks an earlier BF registration
    ]
    assert rows[3]["dataset_id"] == 70


def test_recent_submissions_expire_and_ignore_other_runs(tmp_path):
    now = datetime(2026, 10, 20, 12, 0, 0)
    folder = tmp_path / "registered"
    folder.mkdir()
    for name, run, when, orders in [
        ("X570_a.json", "X570", now - timedelta(minutes=10), ["1"]),
        ("X570_b.json", "X570", now - timedelta(hours=3), ["2"]),
        ("X5700_c.json", "X5700", now, ["3"]),
    ]:
        (folder / name).write_text(json.dumps({
            "run": run, "orders": orders, "submitted_at": when.isoformat(timespec="seconds"),
        }))  # fmt: skip
    assert set(ss.recent_submissions("X570", now=now, state_dir=tmp_path)) == {"1"}


def test_record_then_read_submission(tmp_path):
    ss.record_submission("X570", [12345], "falkonoe", state_dir=tmp_path)
    assert set(ss.recent_submissions("X570", state_dir=tmp_path)) == {"12345"}


def test_demuxing_orders_counts_a_full_run_for_every_order():
    from utils import draugr_queue

    state = draugr_queue.annotate({
        "server": "fgcz-s-023",
        "jobs": [
            {"tsp_id": 1, "state": "queued", "key": "a", "run": "R", "draugr_args": ["--reprocess-orders", "1"]},
            {"tsp_id": 2, "state": "finished", "key": "b", "run": "R", "draugr_args": []},
        ],
        "lost": [],
    })  # fmt: skip
    assert ss.demuxing_orders(state, "R", [1, 2, 3]) == {"1"}
    state["jobs"][0]["orders"] = None  # a full run, e.g. the automatic one
    assert ss.demuxing_orders(state, "R", [1, 2, 3]) == {"1", "2", "3"}
    assert ss.demuxing_orders(state, "other", [1, 2, 3]) == set()


# draugr 3.1+ gives each delivery its own gStore folder and dates it in --run_alias.
# 12345 kept its delivery from 20 Nov, and 12399 was reprocessed on 27 Nov. 12399
# mixes sample types, so the script also has an o12399-10X block with the same date.
DELIVERED_12345 = datetime(2026, 11, 20, 8, 0, 0)
DELIVERED_12399 = datetime(2026, 11, 27, 10, 15, 42)


def test_delivery_times_from_the_run_alias():
    text = (FIXTURES / "X580_sushification.sh").read_text()
    assert ss.demuxed_orders(text, "X580") == {"12345", "12399"}
    assert ss.delivery_times(text, "X580") == {
        "12345": DELIVERED_12345,
        "12399": DELIVERED_12399,
    }
    assert ss.delivery_times(text, "X58") == {}


def test_pre_3_1_script_has_no_delivery_times():
    text = (FIXTURES / "X570_sushification.sh").read_text()
    assert ss.delivery_times(text, "X570") == {}


def _x580_statuses(datasets_by_order):
    text = (FIXTURES / "X580_sushification.sh").read_text()
    return ss.derive_statuses(
        orders=[12345, 12399],
        run_name="X580",
        demuxed=ss.demuxed_orders(text, "X580"),
        datasets_by_order=datasets_by_order,
        submissions={},
        demuxing=set(),
        delivered=ss.delivery_times(text, "X580"),
    )


def test_redemultiplexed_order_with_only_an_older_dataset_is_ready():
    rows = _x580_statuses({
        "12345": [{"id": 1, "name": "o12345_NovaSeq_261120_X580_101", "created": "2026-11-20 14:00:00"}],
        "12399": [{"id": 2, "name": "o12399_NovaSeq_261120_X580_102", "created": "2026-11-20 14:00:05"}],
    })  # fmt: skip
    assert [r["status"] for r in rows] == [ss.REGISTERED, ss.READY]
    assert rows[1]["dataset_id"] is None


def test_dataset_created_after_the_delivery_is_registered():
    rows = _x580_statuses({
        "12399": [
            {"id": 2, "name": "o12399_NovaSeq_261120_X580_102", "created": "2026-11-20 14:00:05"},
            {"id": 3, "name": "o12399_NovaSeq_261120_X580_103", "created": "2026-11-27 11:02:00"},
        ],
    })  # fmt: skip
    assert [r["status"] for r in rows] == [ss.READY, ss.REGISTERED]
    assert rows[1]["dataset_id"] == 3


def test_the_newest_matching_dataset_is_linked():
    datasets = [
        {"id": 3, "name": "o12399_NovaSeq_261120_X580_103", "created": "2026-11-27 11:02:00"},
        {"id": 2, "name": "o12399_NovaSeq_261120_X580_102", "created": "2026-11-20 14:00:05"},
    ]  # fmt: skip
    assert ss.matching_dataset(datasets, "12399", "X580")["id"] == 3
    assert ss.matching_dataset(datasets[::-1], "12399", "X580")["id"] == 3
