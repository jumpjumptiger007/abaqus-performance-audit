"""Conservative parsing of selected Abaqus text files."""
import json
import math
import os
import re
import stat
from collections import Counter, defaultdict
from datetime import datetime

SUFFIXES = {".log", ".sta", ".msg", ".dat"}
MAX_LINE = 64 * 1024
REFERENCE_LIMIT = 5
PHASES = {
    "compiling": r"compiling (?:abaqus/)?(?:standard|explicit) user subroutines",
    "linking": r"linking (?:abaqus/)?(?:standard|explicit) user subroutines",
    "preprocessing": r"analysis input file processor",
    "standard": r"abaqus/standard analysis",
    "explicit": r"abaqus/explicit analysis",
    "job": r"analysis job",
}
PHASE_MARKERS = {
    key: re.compile(r"^(begin|end) " + value + r"(?:\s*[:=-]\s*(.+))?$", re.I)
    for key, value in PHASES.items()
}
VERSION = re.compile(r"^(?:abaqus(?:/standard|/explicit)?\s+|(?:abaqus\s+)?release\s+)(20\d{2}(?:[ .-](?:HF|FD)[ -]?\d{1,3})?)\s*$", re.I)
JOB_END = re.compile(r"""^abaqus job\s+(?:[^\s"']+|"[^"]+"|'[^']+')\s+(completed|aborted)[.!]?$""", re.I)
ANALYSIS_SUCCESS = re.compile(r"^the analysis has completed successfully[.!]?$", re.I)
ANALYSIS_FAILURE = re.compile(
    r"^the analysis (?:has not been completed|has terminated due to (?:previous )?errors)[.!]?$", re.I
)
TOOLCHAIN = re.compile(
    r"^(?:abaqus error:\s*(?:problem during|error during)\s+(?:compilation|linking)\b"
    r"|(?:\*\*\*\s*)?(?:compilation|linking|linker)\s+(?:failed|error)\b"
    r"|(?:fatal error\s+)?LNK\d{4}:)", re.I
)
SOLVER_FAILURE = re.compile(
    r"^(?:abaqus error:\s*)?(?:abaqus/(?:standard|explicit)|analysis input file processor)"
    r"\s+exited with (?:an?\s+)?errors?\b", re.I
)
ERROR = re.compile(r"^(?:\*{3,}\s*(?:fatal\s+)?error\b|abaqus error:)", re.I)
CONVERGENCE_ERROR = re.compile(
    r"^\*{3,}\s*error:\s*(?:too many attempts made for this increment"
    r"|time increment required is less than the minimum specified)[.!]?$", re.I
)
WARNING = re.compile(r"^(?:\*{3,}\s*warning\b|abaqus warning:)", re.I)
CUTBACK = re.compile(r"^\*{3,}\s*(?:note|warning):\s*(?:the\s+)?time increment (?:has been|was) cut back\b", re.I)
PROGRESS = re.compile(r"^(?:increment\s+\d+\s+starts\b|analysis is in progress\b)", re.I)
STANDARD_HEADER = re.compile(r"^step\s+inc\s+att\s+severe\s+equil\s+total\b", re.I)
TIMING_HEADER = re.compile(r"^(?:j o b\s+t i m e\s+s u m m a r y|job time summary)\s*$", re.I)
WALL = re.compile(r"^wallclock time\s*\(\s*sec(?:onds)?\s*\)\s*=\s*(\S+)\s*$", re.I)
NUM = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?", re.ASCII)
UINT = re.compile(r"[0-9]{1,9}")
ATTEMPT = re.compile(r"([0-9]{1,9})([uU]?)")


def number(token):
    if not NUM.fullmatch(token):
        return None
    value = float(token.lower().replace("d", "e"))
    return value if math.isfinite(value) else None


def timestamp(token):
    if not token:
        return None
    try:
        parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
        if "T" in token or (" " in token and ":" in token):
            return parsed
    except ValueError:
        pass
    for pattern in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%y %I:%M:%S %p"):
        try:
            return datetime.strptime(token, pattern)
        except ValueError:
            continue
    return None


def standard_row(line):
    parts = line.split()
    if len(parts) not in (9, 10):
        return None
    if not all(UINT.fullmatch(parts[i]) for i in (0, 1, 3, 4, 5)):
        return None
    attempt = ATTEMPT.fullmatch(parts[2])
    values = tuple(number(token) for token in parts[6:])
    if not attempt or None in values:
        return None
    step, increment, attempt_num = int(parts[0]), int(parts[1]), int(attempt[1])
    if min(step, increment, attempt_num) < 1 or min(values[:2]) < 0 or values[2] <= 0:
        return None
    return (step, increment, attempt_num), (bool(attempt[2]), *map(int, parts[3:6]), *values)


class LogFile:
    def __init__(self, source, suffix):
        self.source = source
        self.suffix = suffix
        self.counts = Counter()
        self.references = defaultdict(list)
        self.versions = set()
        self.phases = defaultdict(list)
        self.pending_stamp = None
        self.timing_lines = 0
        self.wall = []
        self.standard = False
        self.rows = {}
        self.row_lines = {}
        self.conflicting_rows = set()
        self.last_key = None

    def add(self, category, line_number):
        self.counts[category] += 1
        if len(self.references[category]) < REFERENCE_LIMIT:
            self.references[category].append({
                "file": self.source, "line": line_number, "category": category,
            })
        return category

    def classify(self, line, line_number):
        if self.pending_stamp is not None and line:
            parsed = timestamp(line)
            self.pending_stamp[1] = parsed
            self.pending_stamp = None
            if parsed is not None:
                return self.add("phase_timestamp", line_number)
        if self.timing_lines:
            self.timing_lines -= 1
            wall = WALL.fullmatch(line)
            if wall:
                value = number(wall[1])
                if value is None or value < 0:
                    return self.add("malformed_wallclock", line_number)
                self.wall.append(value)
                return self.add("solver_wallclock", line_number)

        if not line:
            return "blank"
        version = VERSION.fullmatch(line)
        if version:
            self.versions.add(re.sub(r"[ .-]+", " ", version[1].upper()))
            return self.add("version", line_number)
        if self.suffix == ".log":
            job_end = JOB_END.fullmatch(line)
            if job_end:
                return self.add("job_success" if job_end[1].lower() == "completed" else "job_failure", line_number)
            for name, pattern in PHASE_MARKERS.items():
                marker = pattern.fullmatch(line)
                if marker:
                    direction = marker[1].lower()
                    event = [direction, timestamp(marker[2]), line_number]
                    self.phases[name].append(event)
                    if marker[2] is None:
                        self.pending_stamp = event
                    return self.add(f"{name}_{direction}", line_number)
        if ANALYSIS_SUCCESS.fullmatch(line):
            return self.add("analysis_success", line_number)
        if ANALYSIS_FAILURE.fullmatch(line) or SOLVER_FAILURE.match(line):
            return self.add("analysis_failure", line_number)
        if self.suffix == ".log" and TOOLCHAIN.match(line):
            return self.add("toolchain_failure", line_number)
        if CUTBACK.match(line):
            return self.add("cutback_message", line_number)
        if CONVERGENCE_ERROR.fullmatch(line):
            self.add("error", line_number)
            return self.add("convergence_failure", line_number)
        if ERROR.match(line):
            return self.add("error", line_number)
        if WARNING.match(line):
            return self.add("warning", line_number)
        if self.suffix in {".msg", ".dat"} and TIMING_HEADER.fullmatch(line):
            self.timing_lines = 12
            return self.add("timing_header", line_number)
        if self.suffix == ".sta" and STANDARD_HEADER.match(line):
            self.standard = True
            return self.add("standard_header", line_number)
        if self.standard and re.match(r"^\d", line):
            row = standard_row(line)
            if row is None:
                return self.add("malformed_status_row", line_number)
            key, values = row
            if key in self.rows:
                if self.rows[key] == values:
                    return self.add("duplicate_status_row", line_number)
                self.conflicting_rows.add(key)
                return self.add("conflicting_status_row", line_number)
            if self.last_key and key < self.last_key:
                self.add("out_of_order_status_row", line_number)
            self.last_key = key
            self.rows[key] = values
            self.row_lines[key] = line_number
            return self.add("status_row", line_number)
        if PROGRESS.match(line):
            return self.add("progress", line_number)
        return self.add("unclassified", line_number)

    def read(self, path, encoding, raw):
        descriptor = None
        initial = None
        writing_raw = False
        try:
            initial = path.stat()
            if not stat.S_ISREG(initial.st_mode):
                return "not_regular"
            with path.open("rb") as stream:
                descriptor = os.fstat(stream.fileno())
                if (not stat.S_ISREG(descriptor.st_mode)
                        or (initial.st_dev, initial.st_ino) != (descriptor.st_dev, descriptor.st_ino)):
                    return "changed_during_read"
                remaining = descriptor.st_size
                line_number = 0
                while remaining:
                    data = stream.readline(min(remaining, MAX_LINE + 1))
                    if not data:
                        return "changed_during_read"
                    remaining -= len(data)
                    line_number += 1
                    if len(data) > MAX_LINE or not data.endswith(b"\n"):
                        category = "oversized_line" if len(data) > MAX_LINE else "unterminated_line"
                        self.add(category, line_number)
                        self.pending_stamp = None
                        if raw:
                            writing_raw = True
                            raw.write(json.dumps({"file": self.source, "line": line_number,
                                                  "category": category}) + "\n")
                            writing_raw = False
                        while remaining and not data.endswith(b"\n"):
                            data = stream.readline(min(remaining, MAX_LINE + 1))
                            if not data:
                                return "changed_during_read"
                            remaining -= len(data)
                        continue
                    if line_number == 1:
                        data = data.removeprefix(b"\xef\xbb\xbf")
                    try:
                        line = data.decode(encoding).rstrip("\r\n")
                    except UnicodeDecodeError:
                        line = data.decode(encoding, errors="replace").rstrip("\r\n")
                        category = self.add("undecodable_line", line_number)
                        self.pending_stamp = None
                    else:
                        category = self.classify(line.strip(), line_number)
                    if raw and category != "blank":
                        writing_raw = True
                        raw.write(json.dumps({"file": self.source, "line": line_number,
                                              "category": category, "text": line}) + "\n")
                        writing_raw = False
        except FileNotFoundError:
            return "missing" if initial is None else "changed_during_read"
        except OSError:
            # Output failures must propagate, never masquerade as an input error.
            if writing_raw:
                raise
            return "unreadable"
        try:
            final = path.stat()
        except OSError:
            return "changed_during_read"
        if (descriptor.st_size, descriptor.st_mtime_ns, descriptor.st_ino) != (
            final.st_size, final.st_mtime_ns, final.st_ino
        ):
            return "changed_during_read"
        return "read"


def phase_durations(files, notes):
    durations = {}
    for name in PHASES:
        groups = [(file, file.phases[name]) for file in files if file.phases[name]]
        if not groups:
            continue
        if len(groups) == 1 and groups[0][0].state == "read":
            file, events = groups[0]
            if [event[0] for event in events] == ["begin", "end"]:
                (_, begin, left), (_, end, right) = events
                if begin and end and (begin.tzinfo is None) == (end.tzinfo is None):
                    seconds = (end - begin).total_seconds()
                    if seconds >= 0:
                        durations[name] = {
                            "seconds": seconds,
                            "basis": "local_clock" if begin.tzinfo is None else "offset_clock",
                            "evidence": [{"file": file.source, "line": n, "category": f"{name}_{event}"}
                                         for n, event in ((left, "begin"), (right, "end"))],
                        }
                        continue
        notes.append(f"{name}: phase markers or timestamps are incomplete, repeated, or inconsistent.")
    return durations


def status_metrics(files, notes):
    status = [file for file in files if file.standard]
    if len(status) > 1:
        notes.append("Multiple Standard status tables were selected. Increment totals are ambiguous.")
        return None
    if not status or not status[0].rows:
        return None
    file = status[0]
    bad_increments = {key[:2] for key in file.conflicting_rows}
    max_attempts = {}
    for step, increment, attempt in file.rows:
        key = (step, increment)
        max_attempts[key] = max(max_attempts.get(key, 0), attempt)
    bad_increments.update(key[:2] for key, row in file.rows.items()
                          if not row[0] and key[2] != max_attempts[key[:2]])
    malformed = any(file.counts[key] for key in (
        "malformed_status_row", "out_of_order_status_row", "oversized_line",
        "unterminated_line", "undecodable_line",
    ))
    if bad_increments or malformed:
        notes.append("Status rows are inconsistent or incomplete. Increment metrics cover usable rows only.")
    rows = {key: row for key, row in file.rows.items() if key[:2] not in bad_increments}
    if not rows:
        return None
    cutbacks = 0
    missing_attempts = any(
        (step, increment, attempt - 1) not in rows
        for step, increment, attempt in rows if attempt > 1
    )
    if missing_attempts:
        notes.append("Some observed attempts have missing predecessors. Cutback totals cover adjacent usable rows.")
    for (step, increment, attempt), row in rows.items():
        following = rows.get((step, increment, attempt + 1))
        if row[0] and following and following[6] < row[6]:
            cutbacks += 1
    latest = max(rows, key=file.row_lines.get)
    return {
        "source": file.source,
        "last_usable_row": {
            "step": latest[0], "increment": latest[1], "attempt": latest[2],
            "unsuccessful": rows[latest][0], "step_time": rows[latest][5],
            "evidence": {"file": file.source, "line": file.row_lines[latest], "category": "status_row"},
        },
        "attempt_rows": len(rows),
        "completed_increments": sum(not row[0] for row in rows.values()),
        "unsuccessful_attempts": sum(row[0] for row in rows.values()),
        "observed_cutbacks": cutbacks,
        "quality": "partial" if bad_increments or malformed or missing_attempts or file.state != "read" else "observed_rows",
    }


def analyze_logs(paths, encoding, raw=None):
    files = []
    notes = []
    for i, path in enumerate(paths, 1):
        suffix = path.suffix.lower()
        file = LogFile(f"file{i:02d}{suffix}", suffix)
        file.state = file.read(path, encoding, raw)
        files.append(file)
    counts = Counter()
    for file in files:
        counts.update(file.counts)
    success = counts["job_success"] or counts["analysis_success"]
    solver_failure = counts["analysis_failure"] or counts["convergence_failure"]
    job_failure = counts["job_failure"] or counts["toolchain_failure"]
    failure = job_failure or solver_failure
    conflict = ((counts["job_success"] and failure)
                or (counts["analysis_success"] and solver_failure and not job_failure))
    if conflict:
        state, basis = "unknown", "conflicting_termination"
        notes.append("Success and failure markers conflict. Verify that the inputs came from one execution.")
    elif failure:
        state, basis = "failed", "terminal_failure"
        if success:
            notes.append("Analysis success and a terminal failure were both observed. Check job-level records.")
    elif success:
        state, basis = "successful", "job_terminal" if counts["job_success"] else "analysis_terminal"
    elif counts["progress"] or any(file.rows or file.phases for file in files):
        state, basis = "incomplete", "progress_only"
    else:
        state, basis = "unknown", "no_supported_terminal_or_progress_evidence"
    if any(file.state != "read" for file in files):
        notes.append("Some selected diagnostic inputs were missing, unreadable, or changed while being read.")
    if any(counts[category] for category in ("unterminated_line", "undecodable_line", "oversized_line")):
        notes.append("Some diagnostic lines could not be parsed. See the evidence categories for affected lines.")
    if counts["unclassified"]:
        notes.append("Unclassified lines may contain unsupported diagnostics or ordinary output.")
    versions = set().union(*(file.versions for file in files))
    if len(versions) > 1:
        notes.append("Multiple Abaqus release strings were observed.")
    wall = {value for file in files if file.state == "read" for value in file.wall}
    if len(wall) > 1:
        notes.append("Multiple different solver wall-clock summaries were observed.")
    phases = phase_durations(files, notes)
    increments = status_metrics(files, notes)
    return {
        "termination": {"state": state, "basis": basis},
        "abaqus_version": next(iter(versions)) if len(versions) == 1 else None,
        "phase_durations": phases,
        "solver_wallclock_seconds": next(iter(wall)) if len(wall) == 1 else None,
        "increment_statistics": increments,
        "diagnostic_counts": dict(sorted(counts.items())),
        "sources": [{"file": file.source, "state": file.state, "counts": dict(sorted(file.counts.items()))}
                    for file in files],
        "evidence": [ref for file in files for refs in file.references.values() for ref in refs],
        "limitations": notes,
    }
