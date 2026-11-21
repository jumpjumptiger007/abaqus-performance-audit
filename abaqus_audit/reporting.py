"""Render offline aggregate reports without executable content."""
import csv
import html
import json
from contextlib import contextmanager

from .analysis import MEASURES
from .monitor import CSV_FIELDS

STYLE = """
:root { color-scheme: light; font: 16px/1.54 system-ui, sans-serif; color: #17242d; }
body { max-width: 76rem; margin: 2.5rem auto; padding: 0 1rem; }
header { border-bottom: 3px solid #22615c; padding-bottom: 1rem; }
h1 { line-height: 1.15; font-size: 2rem; }
h2 { margin-top: 1.9rem; }
h3 { margin-top: 1.45rem; }
.comparison-scope { margin-top: 1.25rem; padding: .5rem 1rem; border-left: 4px solid #22615c; background: #eef5f4; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; margin-bottom: 1rem; }
caption { font-weight: 650; text-align: left; margin-bottom: .3rem; }
td, th { padding: .45rem .65rem; border-bottom: 1px solid #cad7d9; text-align: left;
    overflow-wrap: anywhere; vertical-align: top; }
thead { background: #e6efee; }
tbody th { font-weight: 550; }
ul { padding-left: 1.4rem; }
li { margin: .3rem 0; }
"""


def display(value):
    if value is None:
        return "Unavailable"
    if isinstance(value, float):
        return format(value, ".6g")
    return str(value)


def escaped(value):
    return html.escape(display(value), quote=True)


def label(key):
    return MEASURES.get(key, (key.replace("_", " ").capitalize(),))[0]


def table(caption, headers, rows):
    heading = "".join(f'<th scope="col">{escaped(header)}</th>' for header in headers)
    lines = []
    for first, *rest in rows:
        cells = "".join(f"<td>{escaped(value)}</td>" for value in rest)
        lines.append(f'<tr><th scope="row">{escaped(first)}</th>{cells}</tr>')
    return (f'<div class="table-wrap"><table><caption>{escaped(caption)}</caption>'
            f"<thead><tr>{heading}</tr></thead><tbody>{''.join(lines)}</tbody></table></div>")


def listing(items):
    return "<ul>" + "".join(f"<li>{escaped(item)}</li>" for item in items) + "</ul>"


def _capture_rows(monitor):
    fields = {
        "capture_state": "Capture state",
        "selected_process_count": "Selected processes",
        "logical_processors": "Logical processors reported to the monitor",
        "interval_requested_seconds": "Requested sample interval in seconds",
        "sample_ticks": "Sample ticks",
        "last_sample_elapsed_seconds": "Elapsed seconds at last sample",
    }
    return [(title, monitor.get(key)) for key, title in fields.items()]


def _audit_body(report):
    termination = report["termination"]
    summary = [
        ("Audit execution ID", report["audit_id"]),
        ("Declared simulation run ID", report["run_id"]),
        ("Termination", f'{termination["state"]} ({termination["basis"].replace("_", " ")})'),
        ("Abaqus release", report["abaqus_version"]),
        *((label(key), value) for key, value in report["configuration"].items()),
    ]
    observations = [(label(key), item["value"], item["unit"], item["basis"].replace("_", " "))
                    for key, item in report["observations"].items()]
    content = [
        table("Run information", ("Field", "Value"), summary),
        "<h2>Observed evidence</h2>",
        table("Measured and parsed values", ("Measurement", "Value", "Unit", "Basis"), observations)
        if observations else "<p>No supported numeric measurements were available.</p>",
    ]
    completeness = report["data_completeness"]
    monitor = completeness["monitoring"]
    content.extend([
        "<h2>Data completeness</h2>",
        table("Diagnostic inputs", ("Alias", "Read status", "Unclassified lines"),
              ((item["file"], item["state"], item["counts"].get("unclassified", 0))
               for item in completeness["diagnostic_files"]))
        if completeness["diagnostic_files"] else "<p>No diagnostic inputs selected.</p>",
        table("Monitoring capture", ("Field", "Value"), _capture_rows(monitor)),
    ])
    if monitor.get("processes"):
        content.append(table("Selected process lifetimes", ("Alias", "Exit observed", "Last observed age (s)", "Lifetime (s)"),
                             ((item["process"], item["exit_observed"], item.get("last_observed_age_seconds"),
                               item.get("lifetime_seconds")) for item in monitor["processes"])))
        content.append(table(
            "Observed process transfers across adjacent samples",
            ("Alias", "Read bytes", "Write bytes"),
            ((item["process"], item.get("observed_read_transfer_bytes"),
              item.get("observed_write_transfer_bytes")) for item in monitor["processes"]),
        ))
    if completeness["selected_output_files"]:
        content.append(table("Selected output files", ("Alias", "Type", "Bytes"),
                             ((item["file"], item["kind"], item["bytes"])
                              for item in completeness["selected_output_files"])))
    increments = report["increment_statistics"]
    if increments:
        latest = increments["last_usable_row"]
        content.append(table("Last usable Standard status row", ("Field", "Value"), (
            ("Step", latest["step"]), ("Increment", latest["increment"]), ("Attempt", latest["attempt"]),
            ("Unsuccessful attempt", latest["unsuccessful"]), ("Simulated step time", latest["step_time"]),
            ("Source line", f'{increments["source"]}, line {latest["evidence"]["line"]}'),
        )))
    evidence = report["evidence"]
    if evidence:
        content.extend([
            "<h2>Diagnostic references</h2>",
            table("Recognized and unclassified records", ("Category", "Line count"),
                  ((key.replace("_", " "), value) for key, value in report["diagnostic_counts"].items())),
            table("Representative line references", ("File alias", "Line", "Category"),
                  ((item["file"], item["line"], item["category"].replace("_", " ")) for item in evidence)),
        ])
    content.append("<h2>Diagnostic hypotheses and next investigations</h2>")
    findings = report["diagnostic_hypotheses"]
    if not findings:
        content.append("<p>No diagnostic rule was triggered by the available evidence.</p>")
    for finding in findings:
        content.append(
            f'<h3>{escaped(", ".join(label(key) for key in finding["evidence"]))}</h3>'
            f'<p>{escaped(finding["hypothesis"])}</p>'
            f'<p><strong>Suggested investigation</strong> {escaped(finding["recommendation"])}</p>'
        )
    return "".join(content)


def _comparison_body(report):
    scope = report["interpretation"]
    relationship_text = {
        "same_declared_run": "Repeat audit of the same declared simulation run. Use differences to check audit reproducibility.",
        "different_declared_runs": "The operator supplied different simulation run IDs.",
        "unknown": "Simulation identity is unknown for one or both audits. Independence is unverified.",
    }
    content = [
        '<aside class="comparison-scope" aria-label="How to interpret this comparison">'
        f'<p><strong>{escaped(scope["summary"])}</strong></p>'
        + listing(f"{label(key)}. {value}" for key, value in scope.items() if key != "summary")
        + "</aside>",
        "<h2>Baseline audit</h2>",
        f'<p><strong>Audit execution ID</strong> {escaped(report["baseline_audit_id"])}<br>'
        f'<strong>Declared simulation run ID</strong> {escaped(report["baseline_run_id"])}<br>'
        f'<strong>Termination</strong> {escaped(report["baseline_termination"])}</p>',
    ]
    for comparison in report["comparisons"]:
        relationship = relationship_text[comparison["run_relationship"]]
        content.append(
            "<h2>Candidate audit</h2>"
            f'<p><strong>Audit execution ID</strong> {escaped(comparison["candidate_audit_id"])}<br>'
            f'<strong>Declared simulation run ID</strong> {escaped(comparison["candidate_run_id"])}<br>'
            f'<strong>Termination</strong> {escaped(comparison["candidate_termination"])}</p>'
            f'<p><strong>{escaped(relationship)}</strong></p>'
        )
        content.append(table(
            "Measurements", ("Metric", "Unit", "Baseline", "Candidate", "Delta", "Change (%)", "Measurement status"),
            ((label(item["metric"]), item["unit"], item["baseline_value"], item["candidate_value"],
              item["delta"], item["percent_change"],
              f'{item["state"].capitalize()} — {item["issue"]}' if "issue" in item else "Comparable")
             for item in comparison["measurements"]),
        ))
        content.append(table("Configuration", ("Field", "Baseline", "Candidate", "Status"),
                             ((label(item["field"]), item["baseline"], item["candidate"], item["state"])
                              for item in comparison["configuration"])))
    return "".join(content)


def render_html(report):
    is_audit = report["kind"] == "audit"
    title = "Abaqus performance audit" if is_audit else "Abaqus audit comparison"
    body = _audit_body(report) if is_audit else _comparison_body(report)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{title}</title>
<style>{STYLE}</style>
</head>
<body>
<header>
<h1>{title}</h1>
<div>Tool version {escaped(report["tool_version"])} · {escaped(report["audit_timestamp_utc"])}</div>
</header>
<main>
{body}
<h2>Measurement and sharing limitations</h2>
{listing(report["measurement_limitations"])}
<p>Review the report and its measurements before external sharing.</p>
</main>
</body>
</html>
"""


def _json_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


@contextmanager
def timeseries_writer(path):
    with (path / "timeseries.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        yield writer.writerow


def write_reports(path, report):
    stem = report["kind"]
    with (path / f"{stem}.html").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(render_html(report))
    _json_new(path / f"{stem}.json", report)


def write_input_map(directory, log_paths, monitor_path, output_paths):
    records = {
        "diagnostics": {f"file{i:02d}{path.suffix.lower()}": str(path)
                        for i, path in enumerate(log_paths, 1)},
        "monitoring": str(monitor_path) if monitor_path else None,
        "outputs": {f"output{i:02d}{path.suffix.lower()}": str(path)
                    for i, path in enumerate(output_paths, 1)},
    }
    _json_new(directory / "input-map.json", records)
