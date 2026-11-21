"""Read bounded monitoring records and derive scoped process metrics."""
import json
import math
import os
from collections import Counter, defaultdict

from .logs import MAX_LINE
from .paths import require_regular

PROCESS_FIELDS = (
    "cpu_seconds", "working_set_bytes", "read_transfer_bytes", "write_transfer_bytes", "age_seconds",
)
SYSTEM_FIELDS = (
    "available_memory_bytes", "total_memory_bytes", "system_disk_read_bytes_per_second",
    "system_disk_write_bytes_per_second",
)
CSV_FIELDS = (
    "elapsed_seconds", "process", "process_state", *PROCESS_FIELDS, "cpu_normalized_percent", *SYSTEM_FIELDS,
)


def nonnegative(value):
    if type(value) is int and 0 <= value <= 2**64 - 1:
        return value
    if type(value) is float and math.isfinite(value) and 0 <= value <= 2**64 - 1:
        return value
    return None


def _start(record):
    if record.get("type") != "start" or type(record.get("schema_version")) is not int or record["schema_version"] != 1:
        raise ValueError("Expected a version 1 monitoring start record")
    if type(record.get("logical_processors")) is not int or not 1 <= record["logical_processors"] <= 65536:
        raise ValueError("Invalid logical processor count")
    interval = record.get("interval_seconds")
    if type(interval) is not int or not 1 <= interval <= 300:
        raise ValueError("Invalid sampling interval")
    processes = record.get("processes")
    if not isinstance(processes, list) or not 1 <= len(processes) <= 16:
        raise ValueError("Invalid monitoring process selection")
    ids = [process.get("id") for process in processes if isinstance(process, dict)]
    if (len(ids) != len(processes) or any(type(i) is not int or not 1 <= i <= 2147483647 for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Invalid monitoring process identifiers")
    return {pid: f"process{i:02d}" for i, pid in enumerate(ids, 1)}


def _sample(record, ids, last_elapsed, exited):
    elapsed = nonnegative(record.get("elapsed_seconds"))
    if elapsed is None or (last_elapsed is not None and elapsed <= last_elapsed):
        raise ValueError("Non-increasing sample time")
    processes = record.get("processes")
    if not isinstance(processes, list) or not 1 <= len(processes) <= len(ids):
        raise ValueError("Invalid process samples")
    rows = {}
    for item in processes:
        if not isinstance(item, dict):
            raise ValueError("Invalid process sample")
        pid = item.get("id")
        state = item.get("state")
        if (type(pid) is not int or pid not in ids or pid in rows or pid in exited
                or state not in ("sampled", "unavailable", "exited")):
            raise ValueError("Invalid process sample identity or state")
        rows[pid] = {
            "process": ids[pid], "process_state": state,
            **{key: nonnegative(item.get(key)) if state == "sampled" or key == "age_seconds" else None
               for key in PROCESS_FIELDS},
        }
    if set(rows) != ids.keys() - exited:
        raise ValueError("Incomplete process sample")
    return elapsed, rows


def _read_records(path):
    with path.open("rb") as stream:
        remaining = os.fstat(stream.fileno()).st_size
        for _ in range(86403):
            if not remaining:
                return
            try:
                data = stream.readline(min(remaining, MAX_LINE + 1))
            except OSError:
                yield None
                return
            remaining -= len(data)
            if not data or len(data) > MAX_LINE or not data.endswith(b"\n"):
                yield None
                return
            try:
                record = json.loads(data.decode("utf-8-sig"))
            except (ValueError, RecursionError):
                record = None
            yield record if isinstance(record, dict) else None
        yield None


def _gap(reason):
    return {"capture_state": reason, "limitations": ["Monitoring evidence was unavailable."]}, []


def analyze_monitor(path, emit_sample=None):
    if path is None:
        return _gap("not_selected")
    try:
        require_regular(path)
    except (OSError, ValueError):
        return _gap("missing_or_invalid")
    return _analyze(path, emit_sample)


def _analyze(path, emit_sample):
    records = _read_records(path)
    try:
        try:
            start = next(records, None)
            if start is None:
                return _gap("missing_or_invalid")
            ids = _start(start)
        except (OSError, ValueError):
            return _gap("missing_or_invalid")
        return _summarize(start, ids, records, emit_sample)
    finally:
        records.close()


def _cpu_percent(delta, seconds, logical_processors):
    if delta < 0 or seconds < 0.001:
        return None
    percent = 100 * (delta / seconds) / logical_processors
    # Counter reset, acquisition skew, or a CPU capacity assumption can invalidate a delta.
    return percent if percent <= 100.0 else None


def _summarize(start, ids, records, emit_sample):
    cpu_count = start["logical_processors"]
    previous = {}
    exited = set()
    series = []
    emit = emit_sample if emit_sample is not None else series.append
    availability = Counter()
    process_summaries = defaultdict(dict)
    diagnostics = Counter()
    last_elapsed = None
    end_elapsed = None
    reason = "no_end_record"
    observed_seconds = 0
    aggregate_cpu_seconds = 0
    peak_ws = None
    min_free = None
    min_free_ratio = None
    max_disk_read = None
    max_disk_write = None
    ticks = 0
    for record in records:
        if end_elapsed is not None:
            diagnostics["invalid_records"] += 1
            reason = "invalid_end_record"
            end_elapsed = None
            break
        if record is None:
            diagnostics["invalid_records"] += 1
            previous = {}
            continue
        if record.get("type") == "end":
            candidate = nonnegative(record.get("elapsed_seconds"))
            terminal = record.get("reason")
            if (candidate is None or (last_elapsed is not None and candidate < last_elapsed)
                    or terminal not in ("duration_limit", "processes_exited", "interrupted")
                    or (terminal == "processes_exited" and exited != ids.keys())):
                reason = "invalid_end_record"
                diagnostics["invalid_records"] += 1
                break
            end_elapsed, reason = candidate, terminal
            continue
        try:
            if record.get("type") != "sample":
                raise ValueError("Invalid record type")
            elapsed, rows = _sample(record, ids, last_elapsed, exited)
        except ValueError:
            diagnostics["invalid_records"] += 1
            previous = {}
            continue

        ticks += 1
        system = {field: nonnegative(record.get(field)) for field in SYSTEM_FIELDS}
        availability.update(field for field, value in system.items() if value is not None)
        for pid, row in rows.items():
            for field in PROCESS_FIELDS:
                if row[field] is not None:
                    availability[field] += 1
            if row["age_seconds"] is not None:
                process_summaries[pid]["last_observed_age_seconds"] = row["age_seconds"]
            if row["process_state"] == "exited":
                exited.add(pid)
                if row["age_seconds"] is not None:
                    process_summaries[pid]["lifetime_seconds"] = row["age_seconds"]
            row["cpu_normalized_percent"] = None
            prior = previous.get(pid, {})
            for direction in ("read", "write"):
                field = f"{direction}_transfer_bytes"
                if row[field] is not None and prior.get(field) is not None:
                    delta = row[field] - prior[field]
                    if delta < 0:
                        diagnostics["unusable_transfer_deltas"] += 1
                    else:
                        summary = process_summaries[pid]
                        key = f"observed_{field}"
                        summary[key] = summary.get(key, 0) + delta
            if row["cpu_seconds"] is not None and prior.get("cpu_seconds") is not None:
                delta = row["cpu_seconds"] - prior["cpu_seconds"]
                row["cpu_normalized_percent"] = _cpu_percent(delta, elapsed - last_elapsed, cpu_count)
                if row["cpu_normalized_percent"] is None:
                    diagnostics["unusable_cpu_deltas"] += 1
            emit({"elapsed_seconds": elapsed, **row, **system})

        if rows.keys() == ids.keys() and not exited:
            availability["full_set_live_ticks"] += 1
            if all(row["working_set_bytes"] is not None for row in rows.values()):
                peak_ws = max(peak_ws or 0, sum(row["working_set_bytes"] for row in rows.values()))
                availability["full_working_set_ticks"] += 1
            if all(row["cpu_normalized_percent"] is not None for row in rows.values()):
                delta = sum(row["cpu_seconds"] - previous[pid]["cpu_seconds"] for pid, row in rows.items())
                seconds = elapsed - last_elapsed
                if _cpu_percent(delta, seconds, cpu_count) is not None:
                    aggregate_cpu_seconds += delta
                    observed_seconds += seconds
                    availability["full_cpu_intervals"] += 1
                else:
                    diagnostics["unusable_cpu_deltas"] += 1
        free, total, disk_read, disk_write = system.values()
        if free is not None and total and free <= total:
            availability["valid_memory_ticks"] += 1
            ratio = free / total
            min_free = free if min_free is None else min(min_free, free)
            min_free_ratio = ratio if min_free_ratio is None else min(min_free_ratio, ratio)
        if disk_read is not None:
            max_disk_read = max(max_disk_read or 0, disk_read)
        if disk_write is not None:
            max_disk_write = max(max_disk_write or 0, disk_write)
        previous, last_elapsed = rows, elapsed

    notes = []
    if reason != "processes_exited":
        notes.append("The capture may cover only part of the selected processes' lifetimes.")
    if diagnostics:
        notes.append("Malformed or unusable monitoring data created gaps. See measurement issue counts.")
    if not observed_seconds:
        notes.append("No valid CPU interval covered the full selected process set.")
    if not availability["valid_memory_ticks"]:
        notes.append("System available physical memory was unavailable.")
    if any(f"observed_{direction}_transfer_bytes" not in process_summaries[pid]
           for pid in ids for direction in ("read", "write")):
        notes.append("Some or all process transfer counters were unavailable.")
    if start.get("system_disk_requested") is True and (max_disk_read is None or max_disk_write is None):
        notes.append("Requested system disk throughput counters were unavailable.")
    return {
        "capture_state": reason,
        "monitoring_duration_seconds": end_elapsed,
        "last_sample_elapsed_seconds": last_elapsed,
        "interval_requested_seconds": start["interval_seconds"],
        "logical_processors": cpu_count,
        "selected_process_count": len(ids),
        "sample_ticks": ticks,
        "available_observations": dict(availability),
        "measurement_issues": dict(diagnostics),
        "full_set_cpu_duration_seconds": observed_seconds if observed_seconds else None,
        "mean_cpu_normalized_percent": _cpu_percent(aggregate_cpu_seconds, observed_seconds, cpu_count),
        "peak_sampled_working_set_sum_bytes": peak_ws,
        "minimum_system_available_memory_bytes": min_free,
        "minimum_system_available_memory_fraction": min_free_ratio,
        "peak_system_disk_read_bytes_per_second": max_disk_read,
        "peak_system_disk_write_bytes_per_second": max_disk_write,
        "processes": [{"process": alias, "exit_observed": pid in exited, **process_summaries[pid]}
                      for pid, alias in ids.items()],
        "limitations": notes,
    }, series
