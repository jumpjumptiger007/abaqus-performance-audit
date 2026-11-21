"""Compare known measurements without copying arbitrary imported report text."""
import json
import math
import re

from . import SCHEMA_VERSION, __version__
from .analysis import CONFIG_FIELDS, MEASURES, METRIC_BASES, MONITOR_BASES, OUTPUT_SUFFIXES, utc_now
from .monitor import nonnegative
from .paths import require_regular

RUN_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
VERSION = re.compile(r"20[0-9]{2}(?: (?:HF|FD) ?[0-9]{1,3})?")
CAPTURE_STATES = {"duration_limit", "processes_exited"}
VALIDATION = "Numerical equivalence and physical validation require separate checks. Timing differences do not establish an improvement."


def _dict(value):
    return value if isinstance(value, dict) else {}


def _in(value, choices):
    return isinstance(value, str) and value in choices


def _load(path):
    require_regular(path)
    with path.open("rb") as stream:
        data = stream.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("An input report exceeds the comparison size limit")
    try:
        report = json.loads(data)
    except (ValueError, RecursionError):
        raise ValueError("An input is not a valid JSON audit report") from None
    report = _dict(report)
    if (report.get("kind") != "audit" or type(report.get("schema_version")) is not int
            or report["schema_version"] != SCHEMA_VERSION):
        raise ValueError("Comparison requires version 1 audit reports")
    run_id = report.get("run_id")
    if not isinstance(run_id, str) or RUN_ID.fullmatch(run_id) is None:
        raise ValueError("An input audit has an invalid run identifier")
    return report


def _observation(report, key):
    metric = _dict(_dict(report.get("observations")).get(key))
    value = nonnegative(metric.get("value"))
    basis = metric.get("basis")
    if metric.get("unit") == MEASURES[key][1] and _in(basis, METRIC_BASES[key]):
        return value, basis
    return None, None


def _context(report):
    config = _dict(report.get("configuration"))
    safe = {key: config.get(key) if _in(config.get(key), choices) else None for key, choices in CONFIG_FIELDS.items()}
    cpus = config.get("requested_cpus")
    safe["requested_cpus"] = cpus if type(cpus) is int and 1 <= cpus <= 65536 else None
    version = report.get("abaqus_version")
    safe["abaqus_version"] = version if isinstance(version, str) and VERSION.fullmatch(version) else None
    completeness = _dict(report.get("data_completeness"))
    monitor = _dict(completeness.get("monitoring"))
    for key in ("logical_processors", "selected_process_count", "interval_requested_seconds"):
        value = monitor.get(key)
        safe[key] = value if type(value) is int and 1 <= value <= 65536 else None
    return safe


def _kinds(report, field, allowed):
    items = _dict(report.get("data_completeness")).get(field)
    if not isinstance(items, list) or not items:
        return None
    kinds = []
    for item in items:
        item = _dict(item)
        if field == "selected_output_files":
            kind = item.get("kind")
            if nonnegative(item.get("bytes")) is None:
                return None
        else:
            name = item.get("file")
            kind = name[-4:] if isinstance(name, str) else None
            if item.get("state") != "read":
                return None
        if not _in(kind, allowed):
            return None
        kinds.append(kind)
    return sorted(kinds)


def _run_state(report):
    state = _dict(report.get("termination")).get("state")
    return state if _in(state, ("successful", "failed", "incomplete", "unknown")) else "unknown"


def _monitor_issue(left, right, key):
    for report in (left, right):
        monitoring = _dict(_dict(report.get("data_completeness")).get("monitoring"))
        if not _in(monitoring.get("capture_state"), CAPTURE_STATES) or monitoring.get("measurement_issues") != {}:
            return "Monitoring was interrupted, incomplete, or contained measurement gaps."
        if key not in {"monitoring_duration_seconds", "mean_cpu_normalized_percent", "full_set_cpu_duration_seconds"}:
            ticks = monitoring.get("sample_ticks")
            counts = _dict(monitoring.get("available_observations"))
            count_key = {
                "peak_sampled_working_set_sum_bytes": "full_working_set_ticks",
                "minimum_system_available_memory_bytes": "valid_memory_ticks",
                "minimum_system_available_memory_fraction": "valid_memory_ticks",
                "peak_system_disk_read_bytes_per_second": "system_disk_read_bytes_per_second",
                "peak_system_disk_write_bytes_per_second": "system_disk_write_bytes_per_second",
            }[key]
            if key == "peak_sampled_working_set_sum_bytes":
                ticks = counts.get("full_set_live_ticks")
            if type(ticks) is not int or ticks < 1 or counts.get(count_key) != ticks:
                return "The measurement was unavailable for some monitoring samples."
        if key in {"mean_cpu_normalized_percent", "full_set_cpu_duration_seconds"}:
            coverage, _ = _observation(report, "full_set_cpu_duration_seconds")
            duration, _ = _observation(report, "monitoring_duration_seconds")
            if coverage is None or not duration or not 0.8 * duration <= coverage <= duration:
                return "CPU coverage is insufficient for comparing capture windows."
    first, second = _context(left), _context(right)
    keys = ("selected_process_count", "logical_processors", "interval_requested_seconds")
    if any(first[key] is None or first[key] != second[key] for key in keys):
        return "Process count, CPU normalization capacity, or requested sample interval differs or is unknown."
    a, _ = _observation(left, "monitoring_duration_seconds")
    b, _ = _observation(right, "monitoring_duration_seconds")
    if key != "monitoring_duration_seconds" and (not a or not b or min(a, b) < 0.8 * max(a, b)):
        return "The monitoring windows differ substantially or their durations are unavailable."
    return None


def _metric_issue(left, right, key, bases):
    if bases[0] != bases[1] or "partial" in bases:
        return "The evidence bases differ or status records were inconsistent."
    if key in MONITOR_BASES:
        return _monitor_issue(left, right, key)
    if _run_state(left) != "successful" or _run_state(right) != "successful":
        return "A selected run lacks successful termination evidence."
    if key == "output_size_bytes":
        field, allowed = "selected_output_files", OUTPUT_SUFFIXES
    elif key == "cutback_messages":
        field, allowed = "diagnostic_files", (".log", ".sta", ".msg", ".dat")
    else:
        return None
    a, b = _kinds(left, field, allowed), _kinds(right, field, allowed)
    if a is None or a != b:
        return "The selected file types or their availability differ."
    return None


def _compare_metric(left, right, key):
    a, basis_a = _observation(left, key)
    b, basis_b = _observation(right, key)
    result = {
        "metric": key, "unit": MEASURES[key][1], "baseline_value": a, "candidate_value": b,
        "baseline_basis": basis_a, "candidate_basis": basis_b, "delta": None, "percent_change": None,
    }
    if a is None or b is None:
        result.update(state="missing", issue="A measurement is missing or invalid in one or both runs.")
        return result
    issue = _metric_issue(left, right, key, (basis_a, basis_b))
    if issue:
        result.update(state="incomparable", issue=issue)
        return result
    delta = b - a
    percent = delta / a * 100 if a else None
    if percent is not None and not math.isfinite(percent):
        percent = None
    result.update(state="comparable", delta=delta, percent_change=percent)
    return result


def compare(paths):
    reports = [_load(path) for path in paths]
    if len(reports) < 2 or len({report["run_id"] for report in reports}) != len(reports):
        raise ValueError("Supply at least two audit reports with distinct run identifiers")
    baseline, *candidates = reports
    base_config = _context(baseline)
    comparisons = []
    for candidate in candidates:
        candidate_config = _context(candidate)
        config = [
            {"field": key, "baseline": a, "candidate": b,
             "state": "missing" if a is None or b is None else "same" if a == b else "different"}
            for key, a in base_config.items()
            for b in (candidate_config[key],)
        ]
        comparisons.append({
            "candidate_run_id": candidate["run_id"],
            "candidate_termination": _run_state(candidate),
            "configuration": config,
            "measurements": [_compare_metric(baseline, candidate, key) for key in MEASURES],
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "comparison",
        "tool_version": __version__,
        "audit_timestamp_utc": utc_now(),
        "baseline_run_id": baseline["run_id"],
        "baseline_termination": _run_state(baseline),
        "comparisons": comparisons,
        "measurement_limitations": [
            VALIDATION,
            "Deltas use candidate minus baseline. Comparable means the available measurement bases passed the tool's checks.",
            "Operator review must verify equivalent workload, selected processes, sampling window, and output selection.",
        ],
    }
