"""Combine scoped observations and apply documented diagnostic rules."""
import re
from datetime import datetime, timezone
from uuid import uuid4

from . import SCHEMA_VERSION, __version__
from .logs import analyze_logs
from .monitor import analyze_monitor
from .paths import require_regular

RUN_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
OUTPUT_SUFFIXES = {".odb", ".sim", ".fil", ".sel"}
CONFIG_FIELDS = {
    "solver": ("standard", "explicit"),
    "parallel_mode": ("threads", "mpi", "hybrid"),
    "precision": ("single", "double"),
}

MEASURES = {
    "job_elapsed_seconds": ("Job elapsed", "s"),
    "solver_wallclock_seconds": ("Solver wall-clock summary", "s"),
    "compiling_seconds": ("Compilation phase", "s"),
    "linking_seconds": ("Linking phase", "s"),
    "preprocessing_seconds": ("Input processing phase", "s"),
    "standard_seconds": ("Standard analysis phase", "s"),
    "explicit_seconds": ("Explicit analysis phase", "s"),
    "monitoring_duration_seconds": ("Capture duration", "s"),
    "full_set_cpu_duration_seconds": ("CPU interval coverage", "s"),
    "mean_cpu_normalized_percent": ("Mean CPU for selected process set", "%"),
    "peak_sampled_working_set_sum_bytes": ("Peak sampled sum of process working sets", "bytes"),
    "minimum_system_available_memory_bytes": ("Minimum sampled system available physical memory", "bytes"),
    "minimum_system_available_memory_fraction": ("Minimum sampled system available memory fraction", "fraction"),
    "peak_system_disk_read_bytes_per_second": ("Peak sampled system disk read rate", "bytes/s"),
    "peak_system_disk_write_bytes_per_second": ("Peak sampled system disk write rate", "bytes/s"),
    "attempt_rows": ("Observed Standard attempt rows", "count"),
    "completed_increments": ("Completed increments in usable rows", "count"),
    "unsuccessful_attempts": ("Unsuccessful attempts in usable rows", "count"),
    "observed_cutbacks": ("Observed reductions after unsuccessful attempts", "count"),
    "cutback_messages": ("Recognized cutback messages", "count"),
    "output_size_bytes": ("Total size of selected output files", "bytes"),
}
PHASE_FIELDS = {
    "job": "job_elapsed_seconds", "compiling": "compiling_seconds", "linking": "linking_seconds",
    "preprocessing": "preprocessing_seconds", "standard": "standard_seconds", "explicit": "explicit_seconds",
}

MONITOR_BASES = {
    "monitoring_duration_seconds": "monotonic_capture_clock",
    "full_set_cpu_duration_seconds": "valid_full_process_set_intervals",
    "mean_cpu_normalized_percent": "valid_full_process_set_intervals",
    "peak_sampled_working_set_sum_bytes": "full_process_set_samples",
    "minimum_system_available_memory_bytes": "system_physical_memory_samples",
    "minimum_system_available_memory_fraction": "system_physical_memory_samples",
    "peak_system_disk_read_bytes_per_second": "system_physical_disk_samples",
    "peak_system_disk_write_bytes_per_second": "system_physical_disk_samples",
}
INCREMENT_KEYS = ("attempt_rows", "completed_increments", "unsuccessful_attempts", "observed_cutbacks")
METRIC_BASES = {
    **{key: ("local_clock", "offset_clock") for key in PHASE_FIELDS.values()},
    **{key: (basis,) for key, basis in MONITOR_BASES.items()},
    **{key: ("observed_rows", "partial") for key in INCREMENT_KEYS},
    "solver_wallclock_seconds": ("solver_timing_summary",),
    "cutback_messages": ("recognized_message_occurrences",),
    "output_size_bytes": ("selected_file_sizes",),
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def output_sizes(paths):
    result = []
    for i, path in enumerate(paths, 1):
        suffix = path.suffix.lower()
        size = None
        try:
            require_regular(path)
            size = path.stat().st_size
        except (OSError, ValueError):
            pass
        result.append({"file": f"output{i:02d}{suffix}", "kind": suffix, "bytes": size})
    return result


def observed_metrics(logs, monitor, outputs):
    metrics = {}

    def add(key, value, basis):
        if value is not None:
            metrics[key] = {"value": value, "unit": MEASURES[key][1], "basis": basis}

    for phase, duration in logs["phase_durations"].items():
        add(PHASE_FIELDS[phase], duration["seconds"], duration["basis"])
    add("solver_wallclock_seconds", logs["solver_wallclock_seconds"], "solver_timing_summary")
    for key, basis in MONITOR_BASES.items():
        add(key, monitor.get(key), basis)
    increments = logs["increment_statistics"]
    if increments:
        for key in INCREMENT_KEYS:
            add(key, increments[key], increments["quality"])
    add("cutback_messages", logs["diagnostic_counts"].get("cutback_message"), "recognized_message_occurrences")
    if outputs and all(item["bytes"] is not None for item in outputs):
        add("output_size_bytes", sum(item["bytes"] for item in outputs), "selected_file_sizes")
    return metrics


def diagnoses(metrics, monitor, logs):
    findings = []

    def value(key):
        return metrics.get(key, {}).get("value")

    coverage = value("full_set_cpu_duration_seconds")
    duration = value("monitoring_duration_seconds") or monitor.get("last_sample_elapsed_seconds")
    cpu = value("mean_cpu_normalized_percent")
    if duration and coverage and coverage >= max(30, 0.8 * duration) and cpu is not None and cpu <= 20:
        findings.append({
            "evidence": ["mean_cpu_normalized_percent", "full_set_cpu_duration_seconds"],
            "hypothesis": "The selected processes may be waiting, running a serial phase, or covering only part of the job.",
            "recommendation": "Confirm the worker PID set and align CPU intervals with timestamped solver phases.",
        })
    available = value("minimum_system_available_memory_fraction")
    if available is not None and available < 0.10:
        findings.append({
            "evidence": ["minimum_system_available_memory_fraction"],
            "hypothesis": "The workstation may have experienced memory pressure during the capture.",
            "recommendation": "Check paging and other system activity in a controlled repeat.",
        })
    cutbacks = value("observed_cutbacks") or 0
    messages = value("cutback_messages") or 0
    if max(cutbacks, messages) >= 3:
        findings.append({
            "evidence": [key for key in ("observed_cutbacks", "cutback_messages") if (value(key) or 0) >= 3],
            "hypothesis": "Repeated time-increment reductions may contribute additional solver work.",
            "recommendation": "Inspect the referenced increments and relevant convergence diagnostics.",
        })
    if (value("output_size_bytes") or 0) >= 2**30:
        findings.append({
            "evidence": ["output_size_bytes"],
            "hypothesis": "Writing the selected volumes of output may contribute to elapsed time.",
            "recommendation": "Compare otherwise equivalent runs with a documented output-frequency change and measured I/O.",
        })
    if logs["termination"]["state"] == "failed":
        findings.append({
            "evidence": ["termination"],
            "hypothesis": "An early failure may shorten the observed runtime and change the work performed.",
            "recommendation": "Review terminal evidence before using this run as a performance baseline.",
        })
    return findings


def validate_run_id(run_id):
    if run_id is not None and (not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None):
        raise ValueError(
            "A simulation run ID must have 1 to 64 lowercase ASCII letters, digits, hyphens or underscores, "
            "starting with a letter or digit"
        )
    return run_id


def audit(log_paths, monitor_path, output_paths, encoding, configuration, raw=None, emit_sample=None, *, run_id=None):
    run_id = validate_run_id(run_id)
    logs = analyze_logs(log_paths, encoding, raw)
    monitor, series = analyze_monitor(monitor_path, emit_sample)
    outputs = output_sizes(output_paths)
    metrics = observed_metrics(logs, monitor, outputs)
    limitations = [*logs["limitations"], *monitor["limitations"]]
    if not log_paths:
        limitations.append("No Abaqus diagnostic files were selected.")
    if "job_elapsed_seconds" not in metrics:
        limitations.append("A complete job clock pair was unavailable. Solver and capture durations have their own scope.")
    if outputs and "output_size_bytes" not in metrics:
        limitations.append("Some selected output file sizes were unavailable.")
    limitations.extend([
        "Selected processes and files may cover only part of the job. Linkage to one specific run is operator-supplied.",
        "Physical disk and available memory counters describe the workstation.",
        "Selected process transfer counters include non-disk I/O. Working-set sums may count shared pages more than once.",
        "A performance change requires a controlled comparison. Numerical equivalence and physical validation require separate checks.",
    ])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "audit",
        "tool_version": __version__,
        "audit_id": str(uuid4()),
        "run_id": run_id,
        "audit_timestamp_utc": utc_now(),
        "abaqus_version": logs["abaqus_version"],
        "configuration": configuration,
        "termination": logs["termination"],
        "observations": metrics,
        "diagnostic_counts": logs["diagnostic_counts"],
        "data_completeness": {
            "diagnostic_files": logs["sources"],
            "monitoring": monitor,
            "selected_output_files": outputs,
        },
        "phase_durations": logs["phase_durations"],
        "increment_statistics": logs["increment_statistics"],
        "evidence": logs["evidence"],
        "diagnostic_hypotheses": diagnoses(metrics, monitor, logs),
        "measurement_limitations": limitations,
    }, series
