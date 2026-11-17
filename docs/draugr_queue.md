# Queueing draugr runs from DraugrUI

With [fgcz/draugr#27](https://github.com/fgcz/draugr/pull/27), draugr no longer runs from a `screen` session
that starts it as soon as a run finishes. Every draugr run now goes through a **task spooler (`tsp`) queue on the
instrument server that holds the data** (fgcz-s-023, -024, -025, -034). The queue has one slot, so a server runs one
draugr job at a time and the rest wait their turn. Cron, people on the command line and DraugrUI all submit to the
same queue, through draugr's `draugr-queue` command.

This replaces the way DraugrUI used to start draugr (`ssh … nohup uv run draugr.py … &`), which ran draugr
alongside whatever else was running on the server, and the SLURM approach on the `feat/slurm-queue` branch: the
instrument servers cannot reach the SLURM controller. DraugrUI's side is `utils/draugr_queue.py`.

The authoritative reference is draugr's
[`docs/automated_execution.md`](https://github.com/fgcz/draugr/blob/main/docs/automated_execution.md). This page is
the part DraugrUI needs.

## What DraugrUI is responsible for

1. **Submitting.** Turn the operator's choices (orders, flags) into draugr arguments and queue them with
   `draugr-queue submit` on the run's server. Record the tsp job id it prints, and say "queued", not "started".
2. **Chaining**, when a run is processed in steps (e.g. lanes separately, then delivery for all orders), with
   `--after`, so a later step runs only if the earlier ones succeeded.
3. **Showing the queue.** Poll `draugr-queue status` on each server and show what is queued, running and finished,
   with which parameters, plus the history and any `lost` jobs.
4. **Removing** queued jobs (and clearing `lost` ones) with `draugr-queue remove`, and **stopping** running jobs
   with `draugr-queue stop`.

DraugrUI does not start draugr itself, wait for it, or keep its own record of jobs: the queue and its history are the
record. Everything runs as `illumina` over ssh, as today.

## Calling draugr-queue

There is no `module` command in a non-interactive ssh session, so call uv by its full path (it must be bumped
together with the `Dev/uv` module on the servers):

```text
ssh -o BatchMode=yes illumina@<server> \
    /usr/local/ngseq/packages/Dev/uv/0.13.7/uv run --frozen \
    --directory /export/local/analyses/draugr_exec draugr-queue <command> ...
```

**Quoting.** ssh joins its arguments into one string that the server's shell parses again. draugr arguments
legitimately contain `;`, spaces, `*` and leading `-` (bases masks, custom bcl-convert flags). Build the remote
command as a list and quote it once with `shlex.join`, and run ssh without a local shell:

```python
import shlex
import subprocess

UV = "/usr/local/ngseq/packages/Dev/uv/0.13.7/uv"
DRAUGR_DIR = "/export/local/analyses/draugr_exec"


def draugr_queue(server: str, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    remote = [UV, "run", "--frozen", "--directory", DRAUGR_DIR, "draugr-queue", *args]
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", f"illumina@{server}", shlex.join(remote)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
```

No other quoting is needed: `draugr-queue` passes draugr's arguments to `draugr.py` as separate argv items all the
way through, so the list from `build_draugr_args()` (`utils/draugr_utils.py`) goes in as it is.

Exit codes of `draugr-queue` itself: `0` success; `1` refused, with the reason on stderr as
`draugr-queue: <reason>` (show it to the operator); anything else is a failed `tsp` call, also explained on stderr.
ssh exits with `255` if it could not connect.

## Submitting a run

```text
draugr-queue submit --run-folder /export/local/data/<RUN_FOLDER> \
    --source ui --submitter <B-Fabric login> [--after <tsp id>]... \
    -- <draugr arguments>
```

- Prints the **tsp job id** on stdout (e.g. `7`).
- `--run-folder` goes **before** `--`. Giving it among draugr's arguments is refused.
- `--source ui --submitter <login>`: always pass both, with the B-Fabric user from the launch token. Without
  `--submitter` the job is recorded as submitted by `illumina`.
- Everything after `--` is passed to `draugr.py` unchanged. Pass `--logger-rep /srv/GT/analysis/falkonoe/dmx_logs/prod`
  (draugr's default is the test log folder). The other paths DraugrUI passes today are draugr's defaults, so they may
  stay or go; any path given must be absolute. Keep using `--flag=value` for values that can start with `-`.
- The same run folder, even the exact same arguments, can be queued as often as needed. Nothing is refused because a
  run is already queued, so guard against double clicks in the UI.

Example (Python, using the helper above):

```python
result = draugr_queue(
    server, "submit",
    "--run-folder", f"/export/local/data/{run_folder}",
    "--source", "ui", "--submitter", user_login,
    "--", *draugr_args,
)
if result.returncode == 0:
    tsp_id = int(result.stdout.strip())
else:
    show_error(result.stderr.strip())
```

### Chaining with `--after`

`--after <tsp id>` (repeatable) makes a job run draugr only if each of those jobs **succeeded** (exit code 0).
Typical use, demultiplexing lanes separately and delivering all orders together:

```python
lane7 = submit(["--reprocess-orders", "<lane 7 order>", "--skip-post-demux", "--skip-gstore-copy"])
lane8 = submit(["--reprocess-orders", "<lane 8 order>", "--skip-post-demux", "--skip-gstore-copy"])
submit(["--reprocess-orders", "<all orders>", "--skip-demux"], after=[lane7, lane8])
```

- If one of them failed, the job does not run draugr. It ends with **exit code 99** and its log says why. That counts
  as a failure, so jobs chained `--after` it do not run either.
- `submit` refuses (exit 1) an id that is not in the queue, was not queued by `draugr-queue`, or has already failed.
- Only ids of jobs on the **same server** make sense, and they must be submitted first (use the ids `submit`
  returned). Do not reorder the queue (`tsp -u`/`-U`): a job moved ahead of a job it waits on does not run.

## Polling the queue

```text
draugr-queue status [--history N]
```

prints one JSON object (default `--history 50`; `0` leaves the history out). One call per server; it is cheap (one
`tsp -l`, one `tsp -i` per queued/running job, one read of the history file), so polling every 10–30 s while the
page is open is fine. Poll each server the operator cares about; there is no central view.

```json
{
  "server": "fgcz-s-023",
  "jobs": [
    {
      "tsp_id": 4, "state": "running", "log": "/export/local/analyses/draugr_tsp/output/ts-out.KMy8uj",
      "exit_code": null,
      "key": "0c9d…", "run": "<RUN_FOLDER>", "run_folder": "/export/local/data/RunFolders/<RUN_FOLDER>",
      "draugr_args": ["--reprocess-orders", "12345", "--skip-demux"],
      "source": "ui", "submitter": "<login>", "submitted_from": "<draugrui host>",
      "submitted_at": "2026-11-17T15:02:11", "after": [{"tsp_id": 2, "key": "7a1e…", "run": "<RUN_FOLDER>"}],
      "enqueued_at": "2026-11-17T15:02:11", "started_at": "2026-11-17T15:40:03"
    }
  ],
  "lost": [],
  "history": [ {"event": "submitted", "...": "..."}, {"event": "finished", "...": "..."} ]
}
```

### `jobs`: what tsp currently knows (the last ~100 jobs)

| Field | Meaning |
|---|---|
| `tsp_id` | tsp's job id. **Not unique over time**: it restarts at 0 when the tsp server restarts (e.g. reboot). |
| `key` | Unique job id. Use this to identify jobs and to join with `history`. |
| `state` | `queued`, `running` or `finished`. |
| `exit_code` | Once finished: `0` success, `1` draugr failed, `2` draugr rejected its arguments, `99` not run because an `--after` job failed, `-1` killed (`draugr-queue stop`). `null` until finished. |
| `log` | The job's console output (draugr's stdout/stderr) on the server; `null` while queued. |
| `run`, `run_folder` | Run folder name and resolved path (`/export/local/data/<run>` may be a symlink, e.g. into `RunFolders/`, so match on `run`). |
| `draugr_args` | draugr's arguments, exactly as submitted. |
| `source`, `submitter`, `submitted_from`, `submitted_at` | Who queued it (`ui`, `manual`, or `auto` for cron), from where, when. |
| `after` | The jobs it waits on (`tsp_id`, `key`, `run`); `[]` if none. |
| `enqueued_at`, `started_at`, `ended_at` / `finished_at` | Times. Finished jobs carry `started_at`/`finished_at` from the history. |

The queue order is the `tsp_id` order of the `queued` jobs; at most one job is `running`.

### `history`: the durable record

`history.jsonl` on the server keeps every job forever, across reboots. Each line is an event with the job's fields
above:

| `event` | When | Adds |
|---|---|---|
| `submitted` | job queued | `tsp_id` |
| `started` | job starts draugr (not written for exit 99) | `started_at` |
| `finished` | job ended | `tsp_id`, `exit_code`, `log`, `started_at`, `finished_at` |
| `removed` | `draugr-queue remove` | `removed_at` |
| `stopped` | `draugr-queue stop`; the `finished` line (exit code `-1`) follows | `stopped_by`, `stopped_at` |

Join events on `key`. For a page showing past runs of the current run folder, filter on `run`. If more history is
needed than `--history` returns, ask for more, or read `/export/local/analyses/draugr_tsp/history.jsonl` directly
over ssh.

### `lost`: jobs that need attention

Jobs that were submitted but have neither finished nor been removed, and that tsp no longer knows. This happens when
the server reboots (tsp keeps its queue in memory only): waiting jobs are dropped without running. Each entry is the
job's `submitted` record plus `interrupted`:

- `false`: draugr never started; it is safe to queue the same arguments again.
- `true`: draugr was running when it was lost and may have left partial output; check before re-running.

Show these prominently, offer to queue the job again, and then clear the entry with `remove`.

## Removing a job

```text
draugr-queue remove <key>
```

Takes a `queued` job off the queue, or clears a `lost` (or finished-but-unrecorded) job from `lost`; records a
`removed` event. It refuses a running job (stop it instead). Do not use `tsp -r` directly: such a job would show up
as `lost`.

## Stopping a running job

```text
draugr-queue stop <key> --by <B-Fabric login>
```

Kills the running job's process group (draugr and bcl-convert) and records a `stopped` event with `stopped_by`. It
refuses (exit 1) a job that is queued (use `remove`) or no longer running.

- The job then finishes with exit code `-1`. Jobs chained `--after` it do not run (exit `99`), and the next job in
  the queue starts.
- draugr is killed wherever it was: the run folder may hold partial output, the run's B-Fabric status stays at
  demultiplexing, and no failure email is sent. Ask the operator to confirm, and say this in the dialog.
- Show a job that finished with `-1` and has a `stopped` event as stopped (by whom), not as failed. Go by the exit
  code: if the job finished on its own just as it was stopped, it has a `stopped` event but its real exit code.
- A job can finish between the page's last poll and the click. `stop` then refuses with "is not running"; refresh
  the status rather than showing it as an error.

## Showing a job's log

The `log` path is on the server. To show the tail (works while the job runs):

```python
subprocess.run(["ssh", "-o", "BatchMode=yes", f"illumina@{server}", shlex.join(["tail", "-n", "200", log])],
               capture_output=True, text=True, timeout=30)
```

draugr's detailed log still goes to its `--logger-rep` folder, and run status and errors to B-Fabric and email as
before.

## Things to keep in mind

- **Deployment.** This needs draugr with `draugr-queue` deployed on each server (fgcz/draugr#27). Until then the
  command does not exist there and every call fails; check the exit code rather than assuming.
- **Same server only.** Each server has its own queue; ids and `--after` refer to that server's queue.
- **Cron also queues.** When a run finishes, cron queues the full automatic run (`source: auto`). Jobs DraugrUI
  queues run in addition to, and in order with, that run; they never stop it.
- **Wording.** "Submitted" means queued: tell the operator the job's position (e.g. "3 jobs ahead"), not that
  demultiplexing has begun.
- **Logging to B-Fabric.** Keep logging each submission (`L.log_operation`), now with the tsp id, key and arguments.
