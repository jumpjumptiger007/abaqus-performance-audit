# Abaqus Performance Audit 1.0.0rc2

**Apache-2.0 · Local pre-publication candidate**

## Compatibility and required pilot

**UNVERIFIED — Windows PowerShell 5.1 runtime behavior has not been tested on the target Windows system.**

**UNVERIFIED — Compatibility with real Abaqus diagnostic files, solver versions, and research workloads has not been established.**

**REQUIRED — An authorized Windows pilot must test process monitoring, process exit, interruption, performance counters, and selected real Abaqus diagnostic records before production use.**

Use the [Windows pilot checklist](WINDOWS-PILOT.md). The portable Python tests and earlier PowerShell syntax checks cover source and synthetic behavior. Use authorized, nonconfidential records representative of the target solver versions and workloads when checking real diagnostic files.

## Pre-publication evidence

- The project handoff records that the RC2 application source passed independent review. This audit updates release documentation and packaging. The application source, scripts, fixtures, and example reports are identical to the reviewed RC2 candidate.
- All 28 existing Python tests passed on macOS with Python 3.10.6 and 3.14.7. The test suite also passed from a fresh extraction of the final source ZIP. It covers synthetic diagnostic parsing, audit identity, RC1 import, comparisons, and report safety.
- The review covered the current index and working tree, every reachable commit and local branch, and the four unreachable draft blobs in the local object database. There were no remote or tag references and no staged, untracked, or ignored files after the release documentation commit.
- Historical blobs and ZIP contents were screened for private paths, personal identifiers, credential and certificate signatures, and unexpected file types. Review found only the intended project files, 14 synthetic fixtures, and eight generated synthetic examples. The unreachable drafts are excluded from the archive. The archive passed integrity checks and matched the selected Git tree byte for byte. [Publication security checklist](../SECURITY.md#publication-checklist)

## Licensing

The complete root `LICENSE` is unchanged from the initial commit and matches the canonical Apache-2.0 text. The project and distribution documentation identify Apache-2.0 consistently. The project is independent of Dassault Systèmes. Local review found no bundled proprietary Abaqus code, third-party packages, or additional redistribution notices. Python and Windows PowerShell are supplied by the user's environment. [Canonical Apache-2.0 license](https://www.apache.org/licenses/LICENSE-2.0.txt)

## Publication decision

**BLOCKED pending attribution and authorization.** The repository has no reliable record establishing the copyright holder, attribution year, or authority to distribute the project publicly. Git author metadata identifies commits and does not establish ownership. Confirm the holder's full legal name, the applicable attribution year or range, and the authority to publish under Apache-2.0. Then record the approved notice and reverify the exact release commit and ZIP.

Explicit approval is required to create the public GitHub repository, push the intended branch or tag, and publish the pre-release or its ZIP. The authorized Windows pilot is required before production use. [Draft GitHub description and pre-release notes](GITHUB-PRE-RELEASE.md)
