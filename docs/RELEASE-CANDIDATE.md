# Abaqus Performance Audit 1.0.0rc2

**Apache-2.0 · Local pre-publication candidate**

## Compatibility and required pilot

**UNVERIFIED — Windows PowerShell 5.1 runtime behavior has not yet been validated on the target Windows workstation.**

**UNVERIFIED — Compatibility with real Abaqus diagnostic files, solver versions, and research workloads has not yet been established.**

**REQUIRED — An authorized Windows pilot must be completed before production use.**

The pilot must check process monitoring, performance counter availability, process exit, Ctrl+C interruption, and real Abaqus diagnostic format compatibility using representative, authorized nonconfidential records.

Use the [Windows pilot checklist](WINDOWS-PILOT.md). The portable Python tests and earlier PowerShell syntax checks cover source and synthetic behavior. Use authorized, nonconfidential records representative of the target solver versions and workloads when checking real diagnostic files.

## Pre-publication evidence

- The project handoff records that the RC2 application source passed independent review. Final release preparation adds the approved public attribution and updates release documentation and packaging. The application source, scripts, fixtures, and example reports are identical to the reviewed RC2 candidate.
- All 28 existing Python tests passed on macOS with Python 3.10.6 and 3.14.7. The test suite also passed from a fresh extraction of the final source ZIP. It covers synthetic diagnostic parsing, audit identity, RC1 import, comparisons, and report safety.
- The review covered the current index and working tree, every reachable commit and local branch, and the four unreachable draft blobs in the local object database. The local release tag selects the final release commit. The working tree and index are clean.
- Historical blobs and ZIP contents were screened for private paths, personal identifiers, credential and certificate signatures, and unexpected file types. Review found only the intended project files, 14 synthetic fixtures, and eight generated synthetic examples. The unreachable drafts are excluded from the archive. The archive passed integrity checks and matched the selected Git tree byte for byte. [Publication security checklist](../SECURITY.md#publication-checklist)

## Licensing

**Copyright 2026 Yiqiang Adrian Liu**

The complete root `LICENSE` is unchanged from the initial commit and matches the canonical Apache-2.0 text. The project and distribution documentation identify Apache-2.0 consistently. The project is independent of Dassault Systèmes. Local review found no bundled proprietary Abaqus code, third-party packages, or separate third-party redistribution notices. Python and Windows PowerShell are supplied by the user's environment. [Canonical Apache-2.0 license](https://www.apache.org/licenses/LICENSE-2.0.txt)

## Publication decision

**READY FOR AUTHORIZATION.** The project uses the approved public attribution recorded in [NOTICE](../NOTICE). The local release commit and ZIP are prepared for explicit approval of the public GitHub repository, the intended branch and tag, and the pre-release with its ZIP. Production use requires the authorized Windows pilot. [Draft GitHub description and pre-release notes](GITHUB-PRE-RELEASE.md)
