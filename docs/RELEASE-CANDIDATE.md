# V1.0 release candidate

**Version** 1.0.0rc2

**License** Apache-2.0

**Delivery** Local source repository and clean source ZIP for independent review and an authorized Windows pilot.

## RC2 remediation

RC2 separates audit execution IDs from optional simulation IDs and imports RC1 audit reports. Comparison output labels repeat audits and unknown simulation relationships and distinguishes measurement compatibility from workload, numerical, and physical validation. Generated report filenames are ignored even in custom output directories. The [publication checklist](../SECURITY.md#publication-checklist) requires manual inspection of tracked files, history, and the archive. See the [changelog](../CHANGELOG.md).

## Validation evidence

| Check | Result |
| --- | --- |
| Python unit and CLI integration tests on macOS | 28 passed with Python 3.10.9 and 28 with Python 3.14.7. |
| Python syntax and dependencies | Package and tests compiled. Runtime Python imports are standard-library only. |
| PowerShell syntax | Both scripts parsed without errors using PowerShell 7.2.24's parser on macOS. |
| Synthetic end-to-end CLI | Distinct-identity, repeat-audit, and mixed RC1/RC2 comparisons passed, including an audit imported from the original RC1 ZIP. The baseline recorded 50 seconds, two completed increments, three observed cutbacks, and 20% normalized CPU. The distinct candidate's elapsed delta was −10 seconds and the repeat audit's delta was zero. |
| Security and privacy | All 14 synthetic input hashes matched after end-to-end commands. Audit and comparison tests blocked socket, DNS, and subprocess calls. HTML checks confirmed escaping, a restrictive content security policy, and the absence of active or externally loaded content. |
| Publication inspection | Custom-directory ignore rules and synthetic-example exceptions were exercised. The tracked files, reachable local history, and contents of the source ZIP were inspected for unexpected inputs or generated artifacts. |
| Windows PowerShell 5.1 runtime | **UNVERIFIED.** Run the automated monitor test and workstation checks in the [Windows pilot checklist](WINDOWS-PILOT.md). |
| Real Abaqus format compatibility | **UNVERIFIED.** Use authorized, nonconfidential historical records for the intended Abaqus releases and solvers. |
| Focused independent RC2 review | **UNVERIFIED.** The installed C2C CLI found no running connection, saved conversation, or configured connector for this repository. The RC2 ZIP is ready for independent inspection. |

## Licensing and public-release readiness

The top-level license matches the complete Apache-2.0 text byte for byte. The ZIP distributes only project material, synthetic fixtures and reports, and the license text. Python and Windows PowerShell are supplied by the user's environment. The available history and archive identified no bundled third-party packages or separate redistribution notices. This is an independent project. The Abaqus name identifies the software from Dassault Systèmes. [Apache License text](https://www.apache.org/licenses/LICENSE-2.0.txt)

Copyright ownership and the attribution year could not be established from the repository. Before public release, confirm the holder, authority to publish, and attribution year, and record the approved notice. No copyright owner was inferred from the commit metadata.

**Ready for independent review. Public release remains blocked** pending copyright attribution and release authorization, manual publication inspection, focused RC2 review, and the relevant Windows and Abaqus pilot checks.
