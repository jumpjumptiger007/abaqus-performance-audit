# Security and privacy

## Inputs and execution

The audit CLI reads explicitly named regular text files and a versioned monitoring capture. Selected simulation outputs are inspected for file size only. The CLI never executes text from diagnostic files or reports. The PowerShell script samples only supplied PIDs and local operating-system counters. It does not launch or terminate Abaqus, discover related processes, or install a service. Routine use requires access to the files and selected processes under the operator's account.

No runtime component sends data over the network, requires a service, or gathers credentials. On Windows, the CLI and monitor reject network-drive and UNC paths, symbolic links or junctions, and unsupported device paths. Use an operator-controlled workspace on a local, non-synced volume. On portable hosts, a network-mounted volume can look like a local directory to the CLI. The framework cannot control synchronization or backup performed by other software. Use stable input and output directories under your control.

Outputs go into fresh directories or, for raw monitoring, a new file. The tool does not overwrite existing inputs or results. A failed write can leave a partial output directory. Check for a complete, readable JSON report before using a result and choose a new directory to rerun.

## Data separation

Aggregate reports omit original filenames, absolute paths, log text, PIDs, process names, and free-form configuration strings. Release, timing, workload structure, memory, output size, and any supplied simulation pseudonym can still be sensitive. A human must review any aggregate before sharing it.

A raw capture contains actual process names, PIDs, dates, and individual readings. `--local-dir` creates a separate private copy of bounded diagnostic text and a path map. These files can contain sensitive research data and remain subject to the input files' handling requirements. Choose private parent directories with suitable filesystem permissions. The tool does not encrypt files or manage retention and access controls. Keep both raw artifacts out of repository history.

HTML reports escape interpolated content and use a restrictive Content Security Policy. Reports carry no scripts, external assets, external requests, or executable log content. Aggregate CSV cells contain fixed headings, aliases, status words, and numeric values. The optional diagnostic-line export is structured JSON Lines for local examination as data.

## Publication checklist

Keep real audit output, raw captures, and private evidence in an access-controlled, non-synced directory outside the repository. Use `tests/fixtures/` and the checked-in paths under `examples/` for synthetic material. The repository ignores the CLI's standard generated filenames even in custom output directories. Renamed artifacts, force-added files, and already tracked files can still enter or remain in Git history.

Manual inspection is required for the exact commit, references, and archive intended for publication:

1. Review `git status --short --ignored --untracked-files=all`, `git diff --cached`, and `git ls-files`. Check for private paths or identifiers, credentials, certificates, research files, captures, and generated reports. Confirm the provenance of each fixture and example. Ignore rules leave already tracked files and earlier copies in history.
2. Enumerate branches, tags, and other references with `git for-each-ref`. Review the intended history with `git log --all --name-status` and inspect historical blobs. Use `git fsck --full --strict --no-reflogs` to check object integrity and identify unreachable objects. Keep the local `.git` directory and its unreachable content out of the source ZIP.
3. Verify the ZIP independently of ignore rules. List every entry and compare its contents against the intended committed tree. Check that the archive carries the full license and only intended source, documentation, and synthetic artifacts.
4. Record any finding by path or object ID and issue type. Keep sensitive contents out of the audit notes. Obtain approval before deleting files or rewriting history. Repeat these checks after any correction.
5. Confirm the approved copyright notice and explicit authorization for the intended public repository, references, and pre-release before creating, pushing, or publishing anything.

Automated checks can identify known signatures and unexpected files. Manual review is still required to assess private context and redistribution rights.

## Reporting a vulnerability

Use the repository maintainer's private reporting channel when the project is published. If a private channel is unavailable, contact the maintainer before sending details. Use minimal synthetic reproductions and omit private logs, captures, paths, and model data.
