import shlex

from utils import components
from utils.draugr_utils import build_draugr_args


def _text(node):
    if isinstance(node, str):
        return node
    children = node.children
    if children is None:
        return ""
    if isinstance(children, (list, tuple)):
        return "".join(_text(c) for c in children)
    return _text(children)


def _spans(node, found=None):
    found = [] if found is None else found
    if isinstance(node, str) or node is None:
        return found
    if type(node).__name__ == "Span":
        found.append(node)
    children = node.children
    for c in children if isinstance(children, (list, tuple)) else [children]:
        _spans(c, found)
    return found


def test_parameters_mute_fixed_paths_only():
    args = build_draugr_args([123, 456], skip_gstore=True)
    pre = components._parameters({"key": "k", "draugr_args": args}, ()).children[1]

    muted = [_text(s) for s in _spans(pre) if s.className == "bf-muted"]
    assert muted == [
        "--login-config /home/illumina/bfabric_cred/.bfabricpy.yml",
        "--analysis-folder /export/local/analyses",
        "--scripts-destination /srv/GT/analysis/datasets",
    ]
    text = _text(pre)
    assert "--skip-gstore-copy --reprocess-orders 123,456" in text
    assert not any(
        "--skip-gstore-copy" in m or "--reprocess-orders" in m for m in muted
    )


def test_parameters_text_is_the_shell_command():
    args = build_draugr_args([1], bclconvert_flags="--foo bar")
    pre = components._parameters({"key": "k", "draugr_args": args}, ()).children[1]

    assert _text(pre) == shlex.join(args)


def test_parameters_empty_for_auto_jobs():
    pre = components._parameters({"key": "k", "draugr_args": []}, ()).children[1]
    assert _text(pre) == ""


def test_parameters_open_state_follows_open_keys():
    job = {"key": "k1", "draugr_args": ["--reprocess-orders", "1"]}
    closed = components._parameters(job, open_keys=["other"])
    opened = components._parameters(job, open_keys=["k1"])
    assert not closed.open
    assert opened.open
    assert opened.children[0].id == {"type": "queue-params", "key": "k1"}


def test_queue_view_keeps_open_parameters_across_tables():
    job = {
        "key": "k1",
        "tsp_id": 7,
        "run": "/r",
        "orders": [],
        "draugr_args": [],
        "event": "finished",
        "exit_code": 0,
    }
    state = {"server": "s", "lost": [], "jobs": [], "past": [job]}
    view = components.queue_view(state, "/r", open_keys=["k1"])
    details = [n for n in _walk(view) if type(n).__name__ == "Details"]
    assert [d.open for d in details] == [True]


def _walk(node):
    if isinstance(node, (list, tuple)):
        for n in node:
            yield from _walk(n)
    elif node is not None and not isinstance(node, (str, int, float)):
        yield node
        yield from _walk(getattr(node, "children", None))


def test_parameters_details_keyed_by_job():
    # Dash keys React elements by id, so a row that now shows another job gets a
    # fresh <details> rather than inheriting the previous job's open state.
    details = components._parameters({"key": "k1", "draugr_args": []}, ())
    assert details.id == {"type": "queue-params-details", "key": "k1"}


def test_queue_view_shows_each_job_once():
    running = {
        "key": "k1",
        "tsp_id": 7,
        "run": "/r",
        "orders": [],
        "draugr_args": [],
        "state": "running",
        "position": None,
    }
    ended = dict(running, event="finished", exit_code=0)
    state = {"server": "s", "lost": [], "jobs": [running], "past": [ended]}
    ids = [
        n.id
        for n in _walk(components.queue_view(state, "/r"))
        if getattr(n, "id", None) and n.id.get("type") == "queue-params"
    ]
    assert ids == [{"type": "queue-params", "key": "k1"}]
