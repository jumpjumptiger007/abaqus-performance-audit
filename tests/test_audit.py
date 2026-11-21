import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from abaqus_audit.__main__ import main
from abaqus_audit.analysis import audit
from abaqus_audit.logs import MAX_LINE, analyze_logs
from abaqus_audit.monitor import analyze_monitor
from abaqus_audit.reporting import render_html

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def logs(*names):
    return analyze_logs([FIXTURES / name for name in names], "utf-8")


class ParserTests(unittest.TestCase):
    def test_job_success_and_phase_clocks(self):
        result = logs("completed.log", "completed.sta")
        self.assertEqual(result["termination"], {"state": "successful", "basis": "job_terminal"})
        self.assertEqual(result["abaqus_version"], "2025 HF2")
        self.assertEqual(result["phase_durations"]["job"]["seconds"], 50)
        self.assertEqual(result["phase_durations"]["preprocessing"]["seconds"], 5)
        self.assertEqual(result["phase_durations"]["preprocessing"]["basis"], "local_clock")
        self.assertEqual(result["phase_durations"]["standard"]["seconds"], 40)
        increments = result["increment_statistics"]
        self.assertEqual(increments["attempt_rows"], 5)
        self.assertEqual(increments["completed_increments"], 2)
        self.assertEqual(increments["observed_cutbacks"], 3)
        self.assertEqual(increments["last_usable_row"]["increment"], 2)

    def test_solver_failure_and_missing_timestamp(self):
        result = logs("solver-failure.log")
        self.assertEqual(result["termination"]["state"], "failed")
        self.assertEqual(result["diagnostic_counts"]["analysis_failure"], 1)
        self.assertNotIn("standard", result["phase_durations"])
        self.assertTrue(any("timestamps" in note for note in result["limitations"]))

    def test_specific_convergence_failure_without_wrapper_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "convergence.msg"
            path.write_text("***ERROR: TOO MANY ATTEMPTS MADE FOR THIS INCREMENT\n")
            result = analyze_logs([path], "utf-8")
        self.assertEqual(result["termination"]["state"], "failed")
        self.assertEqual(result["diagnostic_counts"]["convergence_failure"], 1)
        self.assertEqual(result["diagnostic_counts"]["error"], 1)

    def test_compilation_and_linking_failure(self):
        result = logs("toolchain-failure.log")
        self.assertEqual(result["termination"]["state"], "failed")
        self.assertEqual(result["diagnostic_counts"]["toolchain_failure"], 2)

    def test_warning_and_unknown_do_not_prove_termination(self):
        result = logs("diagnostics.msg", "preprocessing.dat")
        self.assertEqual(result["termination"]["state"], "unknown")
        self.assertEqual(result["diagnostic_counts"]["warning"], 2)
        self.assertEqual(result["solver_wallclock_seconds"], 40)
        self.assertIn({"file": "file01.msg", "line": 2, "category": "unclassified"}, result["evidence"])

    def test_missing_and_incomplete_inputs(self):
        result = logs("missing.dat", "truncated.log")
        self.assertEqual(result["termination"]["state"], "incomplete")
        self.assertEqual(result["sources"][0]["state"], "missing")
        self.assertEqual(result["diagnostic_counts"]["unterminated_line"], 1)
        self.assertNotIn("analysis_success", result["diagnostic_counts"])
        self.assertEqual(logs("missing.msg")["termination"]["state"], "unknown")

    def test_repeat_conflict_order_and_malformed_status(self):
        result = logs("inconsistent.sta")
        for category in ("duplicate_status_row", "conflicting_status_row",
                         "out_of_order_status_row", "malformed_status_row"):
            self.assertEqual(result["diagnostic_counts"][category], 1)
        self.assertEqual(result["increment_statistics"]["completed_increments"], 2)
        self.assertEqual(result["increment_statistics"]["observed_cutbacks"], 0)
        self.assertEqual(result["increment_statistics"]["quality"], "partial")

    def test_conflicting_terminal_markers_and_release_strings(self):
        result = logs("completed.log", "solver-failure.log", "candidate.log")
        self.assertEqual(result["termination"]["basis"], "conflicting_termination")
        self.assertIsNone(result["abaqus_version"])
        self.assertNotIn("job", result["phase_durations"])

    def test_nonstandard_numeric_table_is_not_standard_stats(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "explicit.sta"
            path.write_text("STEP    INCREMENT    STABLE TIME\n1 1 1 0 5 5 0.0 0.0 0.2\n")
            result = analyze_logs([path], "utf-8")
        self.assertIsNone(result["increment_statistics"])
        self.assertEqual(result["diagnostic_counts"]["unclassified"], 2)

    def test_oversized_and_bad_encoding_keep_line_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.msg"
            path.write_bytes(b"A" * (2 * MAX_LINE) + b"\n\xff\n***WARNING: Example\n")
            result = analyze_logs([path], "utf-8")
        self.assertEqual(result["diagnostic_counts"]["oversized_line"], 1)
        self.assertEqual(result["diagnostic_counts"]["undecodable_line"], 1)
        self.assertIn({"file": "file01.msg", "line": 3, "category": "warning"}, result["evidence"])

    def test_invalid_wall_and_ambiguous_or_reversed_phase_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            msg = Path(directory) / "case.msg"
            log = Path(directory) / "case.log"
            msg.write_text("JOB TIME SUMMARY\nWALLCLOCK TIME (SEC) = 1e999\n")
            log.write_text("Begin Analysis Job: 2025-01-01T00:00:01Z\n"
                           "End Analysis Job: 2025-01-01T00:00:00Z\n"
                           "Begin Abaqus/Standard Analysis: 2025-01-01T00:00:01Z\n"
                           "End Abaqus/Standard Analysis: 2025-01-01T00:00:02\n")
            result = analyze_logs([msg, log], "utf-8")
        self.assertIsNone(result["solver_wallclock_seconds"])
        self.assertEqual(result["diagnostic_counts"]["malformed_wallclock"], 1)
        self.assertEqual(result["phase_durations"], {})


class MonitorTests(unittest.TestCase):
    def test_normalized_cpu_and_scoped_metrics(self):
        result, rows = analyze_monitor(FIXTURES / "capture.jsonl")
        self.assertEqual(result["selected_process_count"], 2)
        self.assertEqual(result["monitoring_duration_seconds"], 45)
        self.assertEqual(result["mean_cpu_normalized_percent"], 20)
        self.assertEqual(result["full_set_cpu_duration_seconds"], 40)
        self.assertEqual(result["peak_sampled_working_set_sum_bytes"], 400_000_000)
        self.assertEqual(result["minimum_system_available_memory_fraction"], 0.08)
        self.assertEqual(result["peak_system_disk_write_bytes_per_second"], 8000)
        self.assertEqual(result["processes"][0]["observed_read_transfer_bytes"], 8000)
        self.assertIsNone(rows[0]["cpu_normalized_percent"])
        self.assertEqual(rows[2]["cpu_normalized_percent"], 10)
        self.assertEqual(rows[2]["process"], "process01")

    def test_interruption_and_truncated_record(self):
        finished, _ = analyze_monitor(FIXTURES / "interrupted.jsonl")
        truncated, rows = analyze_monitor(FIXTURES / "interrupted-tail.jsonl")
        self.assertEqual(finished["capture_state"], "interrupted")
        self.assertEqual(finished["monitoring_duration_seconds"], 7)
        self.assertEqual(truncated["capture_state"], "no_end_record")
        self.assertTrue(truncated["measurement_issues"])
        self.assertIsNone(truncated["monitoring_duration_seconds"])
        self.assertEqual(len(rows), 4)

    def test_multi_process_exit_does_not_extend_full_set_cpu(self):
        result, rows = analyze_monitor(FIXTURES / "process-exit.jsonl")
        self.assertEqual(result["capture_state"], "processes_exited")
        self.assertEqual(result["full_set_cpu_duration_seconds"], 5)
        self.assertEqual([item["lifetime_seconds"] for item in result["processes"]], [9, 14])
        self.assertEqual(rows[-1]["process"], "process02")
        self.assertEqual(rows[-1]["process_state"], "exited")

    def test_missing_invalid_counters_are_gaps(self):
        result, rows = analyze_monitor(FIXTURES / "missing-counters.jsonl")
        self.assertIsNone(result["mean_cpu_normalized_percent"])
        self.assertIsNone(result["minimum_system_available_memory_bytes"])
        self.assertIsNone(result["peak_system_disk_read_bytes_per_second"])
        self.assertTrue(all(row["cpu_seconds"] is None for row in rows))

    def test_malformed_record_breaks_deltas_and_pid_reuse_is_rejected(self):
        source = [json.loads(line) for line in (FIXTURES / "process-exit.jsonl").read_text().splitlines()]
        records = [source[0], source[1], {}, source[2], source[3], *source[-2:]]
        reused = {**source[2], "elapsed_seconds": 18}
        records.insert(-1, reused)
        records[-1]["elapsed_seconds"] = 20
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reused.jsonl"
            path.write_text("".join(json.dumps(record) + "\n" for record in records))
            result, _ = analyze_monitor(path)
        self.assertIsNone(result["mean_cpu_normalized_percent"])
        self.assertEqual(result["measurement_issues"]["invalid_records"], 2)


class CliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()

    def command(self, *args, expected=0):
        with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main([str(arg) for arg in args]), expected)

    def test_offline_audit_protects_originals_and_omits_identifiers(self):
        log = self.root / "SYNTHETIC_PRIVATE_FILENAME.msg"
        log.write_bytes((FIXTURES / "diagnostics.msg").read_bytes())
        original = log.read_bytes()
        out, raw = self.root / "reports", self.root / "local-evidence"
        with patch("socket.socket", side_effect=AssertionError("network socket")), \
                patch("socket.getaddrinfo", side_effect=AssertionError("DNS lookup")), \
                patch("subprocess.Popen", side_effect=AssertionError("process launch")):
            self.command("audit", "--log", log, "--monitor", FIXTURES / "capture.jsonl",
                         "--out-dir", out, "--local-dir", raw, "--solver", "standard")
            other = self.root / "other"
            self.command("audit", "--log", log, "--out-dir", other)
            comparison = self.root / "comparison"
            self.command("compare", out / "audit.json", other / "audit.json", "--out-dir", comparison)
        self.assertEqual(log.read_bytes(), original)
        for path in (*out.iterdir(), *comparison.iterdir()):
            content = path.read_text(encoding="utf-8")
            for secret in (str(self.root), "SYNTHETIC_PRIVATE_FILENAME", "SYNTHETIC_PROCESS_A", "example.invalid", "<script>"):
                self.assertNotIn(secret, content)
        evidence = (raw / "diagnostic-lines.jsonl").read_text(encoding="utf-8")
        self.assertIn("unknown diagnostic", evidence)
        self.assertIn(str(log), json.loads((raw / "input-map.json").read_text())["diagnostics"].values())
        with (out / "timeseries.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 18)
        self.assertEqual(rows[0]["process"], "process01")
        report = json.loads((out / "audit.json").read_text())
        self.assertTrue(report["diagnostic_hypotheses"])
        self.assertNotIn("job_elapsed_seconds", report["observations"])
        self.command("audit", "--log", log, "--out-dir", out, expected=2)

    def test_html_escapes_values_even_if_custom_data_reaches_renderer(self):
        report, _ = audit([], None, [], "utf-8", {})
        report["configuration"]["solver"] = '<script>alert("test")</script>&'
        content = render_html(report)
        self.assertIn("&lt;script&gt;alert(&quot;test&quot;)&lt;/script&gt;&amp;", content)
        self.assertNotIn("<script>", content)
        self.assertIn("default-src 'none'", content)

    def test_repeat_audit_preserves_declared_run_and_assigns_distinct_audit_ids(self):
        first, second = self.root / "first", self.root / "second"
        for destination in (first, second):
            self.command("audit", "--log", FIXTURES / "completed.log", "--run-id", "trial_01-a",
                         "--out-dir", destination)
        inputs = [path / "audit.json" for path in (first, second)]
        baseline, candidate = [json.loads(path.read_text()) for path in inputs]
        for report in (baseline, candidate):
            self.assertEqual(report["schema_version"], 2)
            self.assertEqual(report["tool_version"], "1.0.0rc2")
            self.assertEqual(report["run_id"], "trial_01-a")
            self.assertEqual(UUID(report["audit_id"]).version, 4)
        self.assertNotEqual(baseline["audit_id"], candidate["audit_id"])
        self.assertEqual(baseline["observations"], candidate["observations"])
        audit_html = inputs[0].with_suffix(".html").read_text(encoding="utf-8")
        for text in ("Audit execution ID", "Declared simulation run ID", baseline["audit_id"], "trial_01-a"):
            self.assertIn(text, audit_html)

        out = self.root / "comparison"
        self.command("compare", *inputs, "--out-dir", out)
        result = json.loads((out / "comparison.json").read_text())
        entry = result["comparisons"][0]
        self.assertEqual(result["baseline_audit_id"], baseline["audit_id"])
        self.assertEqual(entry["candidate_audit_id"], candidate["audit_id"])
        self.assertEqual(result["baseline_run_id"], entry["candidate_run_id"])
        self.assertEqual(entry["run_relationship"], "same_declared_run")
        self.assertIn("Repeat audit of the same declared simulation run",
                      (out / "comparison.html").read_text(encoding="utf-8"))

        copy = self.root / "duplicate.json"
        copy.write_bytes(inputs[0].read_bytes())
        rejected = self.root / "rejected"
        self.command("compare", inputs[0], copy, "--out-dir", rejected, expected=2)
        self.assertFalse(rejected.exists())

    def test_identical_unnamed_audits_have_unknown_simulation_relationship(self):
        inputs = []
        for name in ("first", "second"):
            dest = self.root / name
            self.command("audit", "--log", FIXTURES / "completed.log", "--out-dir", dest)
            inputs.append(dest / "audit.json")
        baseline, candidate = [json.loads(path.read_text()) for path in inputs]
        self.assertIsNone(baseline["run_id"])
        self.assertIsNone(candidate["run_id"])
        self.assertNotEqual(baseline["audit_id"], candidate["audit_id"])
        self.assertEqual(baseline["observations"], candidate["observations"])
        out = self.root / "comparison"
        self.command("compare", *inputs, "--out-dir", out)
        result = json.loads((out / "comparison.json").read_text())
        self.assertEqual(result["comparisons"][0]["run_relationship"], "unknown")
        self.assertIn("Independence is unverified", (out / "comparison.html").read_text(encoding="utf-8"))

    def test_cli_rejects_malformed_or_unsafe_declared_run_ids_before_writing(self):
        destination = self.root / "report"
        for identifier in ("", "_first", "-first", "A", "é", "a" * 65, "a b", "a/b",
                           "a\\b", "a.b", "<script>", "a\n"):
            with self.subTest(identifier=identifier):
                self.command("audit", "--log", FIXTURES / "completed.log", "--run-id=" + identifier,
                             "--out-dir", destination, expected=2)
                self.assertFalse(destination.exists())
        self.command("audit", "--log", FIXTURES / "completed.log", "--run-id", "a" * 64,
                     "--out-dir", destination)

    def test_import_rejects_missing_malformed_or_unsafe_identities_and_schemas(self):
        current, _ = audit([], None, [], "utf-8", {}, run_id="anon-01")
        baseline = self.root / "baseline.json"
        baseline.write_text(json.dumps(current))
        candidate = self.root / "candidate.json"
        output = self.root / "comparison"
        for name, value in (("audit_id", None), ("audit_id", "<script>"), ("audit_id", 1),
                            ("run_id", {"custom": "text"}), ("run_id", "a/secret"),
                            ("schema_version", 99), ("schema_version", True)):
            with self.subTest(name=name, value=value):
                candidate.write_text(json.dumps({**current, "audit_id": str(uuid4()), name: value}))
                self.command("compare", baseline, candidate, "--out-dir", output, expected=2)
                self.assertFalse(output.exists())
        for name in ("audit_id", "run_id"):
            with self.subTest(missing=name):
                data = {**current, "audit_id": str(uuid4())}
                del data[name]
                candidate.write_text(json.dumps(data))
                self.command("compare", baseline, candidate, "--out-dir", output, expected=2)
                self.assertFalse(output.exists())
        candidate.write_text(json.dumps({"kind": "audit", "schema_version": 1, "run_id": "not-a-legacy-uuid"}))
        self.command("compare", baseline, candidate, "--out-dir", output, expected=2)

    def test_legacy_uuid_is_an_audit_id_and_preserves_unknown_simulation_identity(self):
        first = self.root / "legacy-first.json"
        second = self.root / "legacy-second.json"
        for destination, fixture in ((first, "completed.log"), (second, "candidate.log")):
            report, _ = audit([FIXTURES / fixture], None, [], "utf-8", {})
            report.update(schema_version=1, tool_version="1.0.0rc1", run_id=report.pop("audit_id"))
            destination.write_text(json.dumps(report))
        current = self.root / "current"
        self.command("audit", "--log", FIXTURES / "candidate.log", "--run-id", "anon-02", "--out-dir", current)
        out = self.root / "comparison"
        self.command("compare", first, second, current / "audit.json", "--out-dir", out)
        result = json.loads((out / "comparison.json").read_text())
        self.assertEqual(result["baseline_audit_id"], json.loads(first.read_text())["run_id"])
        self.assertIsNone(result["baseline_run_id"])
        legacy_candidate, current_candidate = result["comparisons"]
        self.assertEqual(legacy_candidate["candidate_audit_id"], json.loads(second.read_text())["run_id"])
        self.assertIsNone(legacy_candidate["candidate_run_id"])
        self.assertEqual(current_candidate["candidate_run_id"], "anon-02")
        self.assertEqual([item["run_relationship"] for item in result["comparisons"]], ["unknown", "unknown"])
        elapsed = next(item for item in legacy_candidate["measurements"] if item["metric"] == "job_elapsed_seconds")
        self.assertEqual(elapsed["delta"], -10)

    def test_comparison_of_three_runs_with_incomplete_and_different_config(self):
        directories = [self.root / value for value in ("first", "second", "third")]
        self.command("audit", "--log", FIXTURES / "completed.log", "--log", FIXTURES / "completed.sta",
                     "--requested-cpus", 8, "--run-id", "synthetic-baseline", "--out-dir", directories[0])
        self.command("audit", "--log", FIXTURES / "candidate.log", "--requested-cpus", 4,
                     "--run-id", "synthetic-candidate", "--out-dir", directories[1])
        self.command("audit", "--log", FIXTURES / "inconsistent.sta", "--out-dir", directories[2])
        out = self.root / "comparison"
        self.command("compare", *(path / "audit.json" for path in directories), "--out-dir", out)
        result = json.loads((out / "comparison.json").read_text())
        second, third = result["comparisons"]
        self.assertEqual(result["baseline_run_id"], "synthetic-baseline")
        self.assertEqual(second["candidate_run_id"], "synthetic-candidate")
        self.assertEqual(second["run_relationship"], "different_declared_runs")
        self.assertEqual(third["run_relationship"], "unknown")
        measurement = {item["metric"]: item for item in second["measurements"]}
        self.assertEqual(measurement["job_elapsed_seconds"]["delta"], -10)
        self.assertEqual(measurement["job_elapsed_seconds"]["percent_change"], -20)
        self.assertEqual(measurement["completed_increments"]["state"], "missing")
        comparison = {item["metric"]: item for item in third["measurements"]}
        self.assertEqual(comparison["completed_increments"]["state"], "incomparable")
        self.assertTrue(any(item["field"] == "requested_cpus" and item["state"] == "different"
                            for item in second["configuration"]))
        html = (out / "comparison.html").read_text(encoding="utf-8")
        self.assertIn("Numerical equivalence and physical validation require separate checks", html)
        self.assertEqual(set(result["interpretation"]), {
            "summary", "measurement_compatibility", "workload_equivalence", "numerical_equivalence", "physical_validation",
        })
        warning = "Measurement comparability does not establish simulation equivalence or scientific validity."
        self.assertEqual(result["interpretation"]["summary"], warning)
        self.assertLess(html.index(warning), html.index("<caption>Measurements"))
        self.assertIn("Measurement status", html)

    def test_comparison_requires_adequate_monitor_coverage(self):
        reports = []
        for index, capture in enumerate(("capture.jsonl", "capture.jsonl", "interrupted.jsonl")):
            destination = self.root / f"audit-{index}"
            self.command("audit", "--monitor", FIXTURES / capture, "--out-dir", destination)
            reports.append(destination / "audit.json")
        destination = self.root / "comparison"
        self.command("compare", *reports, "--out-dir", destination)
        comparisons = json.loads((destination / "comparison.json").read_text())["comparisons"]
        same, interrupted = (
            {item["metric"]: item for item in comparison["measurements"]} for comparison in comparisons
        )
        self.assertEqual(same["mean_cpu_normalized_percent"]["delta"], 0)
        self.assertEqual(same["peak_sampled_working_set_sum_bytes"]["state"], "comparable")
        self.assertEqual(interrupted["monitoring_duration_seconds"]["state"], "incomparable")
        self.assertEqual(interrupted["mean_cpu_normalized_percent"]["state"], "incomparable")

    def test_comparison_sanitizes_untrusted_schema_fields(self):
        one, two = self.root / "first", self.root / "second"
        for path in (one, two):
            self.command("audit", "--log", FIXTURES / "completed.log", "--out-dir", path)
        source = two / "audit.json"
        data = json.loads(source.read_text())
        marker = "<script>alert(123)</script>"
        data["configuration"] = {"solver": marker}
        data["termination"]["state"] = marker
        data["observations"]["job_elapsed_seconds"]["basis"] = [marker]
        source.write_text(json.dumps(data))
        self.command("compare", one / "audit.json", source, "--out-dir", self.root / "comparison")
        sanitized = (self.root / "comparison" / "comparison.json").read_text()
        self.assertNotIn(marker, sanitized)
        self.assertIn('"state": "missing"', sanitized)

    def test_output_stat_only_and_size_hypothesis(self):
        path = self.root / "simulation.odb"
        with patch("abaqus_audit.analysis.require_regular"), patch.object(Path, "stat") as stat_call, \
                patch.object(Path, "open", side_effect=AssertionError("opened output file")):
            stat_call.return_value.st_size = 2**30
            report, series = audit([], None, [path], "utf-8", {})
        self.assertEqual(report["observations"]["output_size_bytes"]["value"], 2**30)
        self.assertEqual(report["diagnostic_hypotheses"][0]["evidence"], ["output_size_bytes"])
        self.assertEqual(series, [])

    def test_rejects_unsafe_or_invalid_output_and_unsupported_inputs(self):
        destination = self.root / "result"
        self.command("audit", "--log", FIXTURES / "completed.log", "--out-dir", destination,
                     "--local-dir", destination / "local", expected=2)
        self.command("audit", "--log", self.root / "synthetic.inp", "--out-dir", destination, expected=2)
        self.assertFalse(destination.exists())
        link = self.root / "symlink.log"
        try:
            link.symlink_to(FIXTURES / "completed.log")
        except (NotImplementedError, OSError):
            self.skipTest("Symlink creation requires additional privileges on this host")
        self.command("audit", "--log", link, "--out-dir", destination, expected=2)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
