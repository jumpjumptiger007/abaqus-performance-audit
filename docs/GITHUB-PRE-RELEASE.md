# GitHub pre-release draft

## Repository description

Offline audit and comparison toolkit for Abaqus diagnostics and Windows process metrics. Independent and Apache-2.0.

## Release title and tag

**Title** Abaqus Performance Audit 1.0.0rc2

**Proposed tag** `v1.0.0rc2`

**Release type** Pre-release

## Release notes

Abaqus Performance Audit reads selected diagnostic files and Windows process captures and produces local JSON, CSV, and HTML reports. This independent project is separate from Dassault Systèmes. The Python CLI uses the standard library and runs offline.

**UNVERIFIED — Windows PowerShell 5.1 runtime behavior has not been tested on the target Windows system.**

**UNVERIFIED — Compatibility with real Abaqus diagnostic files, solver versions, and research workloads has not been established.**

**REQUIRED — An authorized Windows pilot must test process monitoring, process exit, interruption, performance counters, and selected real Abaqus diagnostic records before production use.**

### Changes in RC2

- Separate the audit execution UUID from the optional simulation run ID. Comparisons label repeat audits and unknown simulation relationships. RC1 audit JSON remains supported for comparison.
- Distinguish measurement compatibility from workload equivalence, numerical equivalence, and physical validation.
- Ignore standard generated report filenames in custom output directories and document manual publication checks.

The source archive contains synthetic fixtures and example reports. All 28 existing Python tests passed on macOS. Start with the README's synthetic audit and use the Windows pilot checklist for target-system validation. See the changelog for the RC1-to-RC2 changes.
