# Abaqus Performance Audit

An offline command-line toolkit for measuring and comparing existing Abaqus runs. It reads selected diagnostic files, optionally combines them with a Windows resource capture, and produces a local audit. A model, input deck, user subroutine, and Abaqus installation are unnecessary for offline analysis.

**Release candidate** 1.0.0rc2 · Apache-2.0 · Windows 10/11 capture target (runtime unverified)

## Install and try the synthetic audit

Extract the source archive or copy the repository to a local, non-synced folder. Run the commands from the repository root with Python 3.10 or later. The toolkit runs from source and requires zero Python packages. On macOS or Linux, substitute `python3` for `py -3`.

```powershell
py -3 -m abaqus_audit --version
New-Item -ItemType Directory -Path reports
py -3 -m abaqus_audit audit --log tests/fixtures/completed.log --log tests/fixtures/completed.sta --log tests/fixtures/diagnostics.msg --log tests/fixtures/preprocessing.dat --monitor tests/fixtures/capture.jsonl --solver standard --requested-cpus 4 --parallel-mode threads --run-id synthetic-baseline --out-dir reports/first
py -3 -m abaqus_audit audit --log tests/fixtures/candidate.log --solver standard --requested-cpus 2 --parallel-mode threads --run-id synthetic-candidate --out-dir reports/second
py -3 -m abaqus_audit compare reports/first/audit.json reports/second/audit.json --out-dir reports/comparison
```

Open `reports/first/audit.html` and `reports/comparison/comparison.html` in a local browser. Inspect the corresponding JSON for full evidence and completeness details. The audit CSV contains anonymized process series and system samples, measured in seconds from capture start. The checked-in [audit](examples/baseline/audit.html) and [comparison](examples/comparison/comparison.html) use the same synthetic records. Every invocation creates a new audit execution ID and timestamp.

## Capture a running job on Windows

In Windows PowerShell 5.1, supply the worker PIDs you have independently identified under your user account. Replace the illustrative PIDs in the example. Set the output root to an existing private local directory outside the checkout and use a fresh capture filename. The monitor supports one to 16 explicit PIDs and a bounded capture duration. Repeat a capture with a documented PID selection and window for later comparison.

```powershell
$auditRoot = "C:/local-audits"
New-Item -ItemType Directory -Path "$auditRoot/captures", "$auditRoot/reports"
.\scripts\Monitor-Abaqus.ps1 -ProcessId 1234,5678 -OutputPath "$auditRoot/captures/run.jsonl" -IntervalSeconds 5 -DurationSeconds 600 -SystemDisk
py -3 -m abaqus_audit audit --log "C:/local-jobs/job.log" --log "C:/local-jobs/job.sta" --monitor "$auditRoot/captures/run.jsonl" --output-file "C:/local-jobs/job.odb" --run-id trial-01 --out-dir "$auditRoot/reports/run"
```

`-SystemDisk` opts into workstation-wide physical disk rates. Select `--output-file` for size metadata only from explicitly selected `.odb`, `.sim`, `.fil`, or `.sel` files. Use `--local-dir "$auditRoot/local-evidence/run"` with an existing private `local-evidence` parent if you need the private alias map and diagnostic lines. For real runs, keep captures, private evidence, and reports under your own access controls in a local, non-synced directory outside the source checkout. Review aggregate reports before external sharing. [Security and publication checklist](SECURITY.md)

The monitor observes processes already running. The capture ends when all selected processes have exited, the duration limit is reached, or you press Ctrl+C. Flushed records remain usable after interruption. A capture window and a process lifetime are separate measurements, and neither represents total job elapsed time.

## Identify the simulation being audited

Use `--run-id` to assign an anonymous identifier such as `trial-01` to a simulation. Reuse that identifier when auditing the same simulation again. Use one to 64 lowercase ASCII letters, digits, hyphens, or underscores, starting with a letter or digit. Choose a pseudonym that reveals no research or personal details. Omit the option when the simulation identity is unknown.

The comparison labels repeated audits of a declared run and flags missing simulation identity. RC1 reports are supported. Their old random IDs identify audit executions and their simulation identity is unknown.

## Interpret the results

- **Observed evidence** includes parsed status, timing and quantities, availability, and references by anonymous filename and line number.
- **Diagnostic hypotheses** follow deterministic rules. Recommendations describe investigations or controlled comparisons.
- **Run comparisons** use the first input as the baseline and show candidate-minus-baseline deltas for comparable measurements. Missing or incomparable measurements retain their status and reason. Configuration differences appear alongside the measurements.

**Measurement comparability does not establish simulation equivalence or scientific validity.** A comparable measurement passes timing, coverage, or other evidence-basis checks for that metric. Verify the workload separately, including mesh, materials, sources, boundary conditions, and incrementation. Assess numerical equivalence using appropriate outputs and tolerances, then assess physical validity against relevant experimental or physical evidence.

## Compatibility and validation

Abaqus/Standard and Abaqus/Explicit use different progress formats. V1 parses a narrow documented-in-this-repository Standard table layout, supported English markers, and qualified timing summaries. Other lines remain visible through counts, aliases, and optional local records. [Abaqus output reference](https://docs.software.vt.edu/abaqusv2026/English/SIMACAEOUTRefMap/simaout-c-output.htm)

Run `py -3 -m unittest discover -s tests -v` or `python3 -m unittest discover -s tests -v`. Live Windows sampling and real Abaqus format compatibility require pilot validation. The synthetic test results establish parser and report behavior on the included fixtures.

- [Evidence rules and formats](docs/FORMAT.md)
- [Windows pilot checklist](docs/WINDOWS-PILOT.md)
- [Security and privacy](SECURITY.md)
- [Contribution guidance](CONTRIBUTING.md)
- [Release candidate status](docs/RELEASE-CANDIDATE.md)
- [Changelog](CHANGELOG.md)

## License

This project is independent of Dassault Systèmes and uses the [Apache License 2.0](LICENSE). The Abaqus name identifies the simulation software it audits. The archive contains project source and synthetic fixtures and reports. Python and Windows PowerShell are supplied by the user's environment. Copyright-holder and attribution metadata must be confirmed before public release.
