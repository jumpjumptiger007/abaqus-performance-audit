# V1.0 release candidate

**Version** 1.0.0rc1

**License** Apache-2.0

**Delivery** Local source repository and source archive for an authorized pilot.

## Implemented

- Read-only analysis of explicitly selected `.log`, `.sta`, `.msg`, and `.dat` files with evidence locators and nullable quantities.
- Windows PowerShell capture for selected PIDs with monotonic timing, working set, CPU, local CIM counters, and exit handling.
- Deterministic findings and local aggregate JSON, HTML, and CSV reports. Optional private evidence has its own output directory.
- Baseline comparisons with evidence-basis and availability checks, configuration differences, and separate scientific validation requirements.
- Synthetic fixtures and sample reports, Windows validation steps, contribution guidance, and privacy documentation.

## Validation evidence

| Check | Result |
| --- | --- |
| Python unit and CLI integration tests on macOS | 23 passed with Python 3.10.9 and 23 passed with Python 3.14.7. |
| Python syntax compilation | Passed for the package and tests. |
| PowerShell syntax | Both scripts parsed without errors using PowerShell 7.2.24's parser on macOS. |
| Synthetic end-to-end CLI | Audit, comparison, and example regeneration verified. Baseline recorded 50 seconds, two completed increments, three observed cutbacks, and 20% normalized CPU. Candidate job elapsed delta was −10 seconds. |
| Security and privacy | Local checks verified source preservation, fresh-output enforcement, sanitized aggregate output, log markup escaping, no socket, DNS or subprocess calls during audit, and size-only access to selected simulation outputs. |
| Windows PowerShell 5.1 runtime | UNVERIFIED. Run the automated monitor test and workstation checks in the [Windows pilot checklist](WINDOWS-PILOT.md). |
| Real Abaqus format compatibility | UNVERIFIED. Use authorized, nonconfidential historical records for each relevant release and solver. |
| C2C architecture and independent implementation review | UNVERIFIED. C2C was installed but the workspace had no running connection, saved ChatGPT conversation, or configured connector. The existing-connection check required first-time setup. Local implementation and validation proceeded under the handoff fallback. |

## Remaining release blockers

1. Record the Windows PowerShell 5.1 pilot results, including counter permissions, process exit, Ctrl+C, and representative sampling cadence.
2. Verify the parser against nonconfidential records covering the intended Abaqus releases and solver modes.
3. Bind an authorized C2C workspace and obtain the independent review before public release. Review module scope, timestamp/status assumptions, process identity and counter attribution, file handling, incomplete data, scientific interpretation, and release documentation.
4. Obtain publication approval before creating a remote or releasing the archive publicly.
