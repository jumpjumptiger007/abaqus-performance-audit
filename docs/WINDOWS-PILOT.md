# Windows pilot checklist

**Status** UNVERIFIED on Windows 10/11. Run as a regular user using Windows PowerShell 5.1 and Python 3.10 or later. Follow your workstation's script execution policy. Use synthetic records, a private local working directory, and your own disposable processes for this checklist.

## Portable audit and monitor checks

1. From the repository root, run `py -3 -m unittest discover -s tests -v` and the synthetic audit in the README. Check that it reports 50 seconds of job elapsed time, two usable completed increments, three observed cutbacks, and 20% normalized CPU for the selected process set. Run the comparison and check that job elapsed changes by −10 seconds and the candidate's missing monitor and status metrics are marked missing.
2. Run `powershell.exe -NoProfile -File .\tests\Test-Monitor.ps1`. It starts a temporary Windows PowerShell child that exits on its own, verifies the capture's exit record, simulates unavailable CIM providers, and checks that a pre-existing capture cannot be overwritten.
3. In a local PowerShell console, start the monitor with two known disposable PIDs under your account. Let one exit and confirm it is recorded once, the other remains sampled, and no additional PID appears. Use low- and high-CPU spans in a controlled test and compare the direction of the normalized CPU trend with your workstation's process measurements.
4. Start a longer capture and press Ctrl+C after at least two sample ticks. Confirm the file stays readable and that the monitored processes remain unaffected. A clean cancellation may write an `interrupted` end record. A console close or abrupt stop may leave only flushed samples. Audit both forms and verify the capture state and nullable duration.
5. Enable `-SystemDisk`. Verify that physical disk rates are labeled system-wide. If disk or CIM access is unavailable, confirm null values and limitations. Confirm working set and system available memory use bytes, and that displayed system totals are plausible for the workstation.
6. Repeat an audit with networking disconnected. Open the generated HTML locally and confirm that the expected tables and styles are present. Confirm output paths that already exist cannot be overwritten. Check that UNC and mapped network drive destinations are rejected. Do not write testing artifacts to a real share.
7. Record OS build, PowerShell and Python versions, permissions, capture cadence, any counter gaps, and the result of each check. Repeat any monitoring checks on a different Windows version before claiming support for that environment.

## Abaqus compatibility pilot

After separate authorization, check supported patterns using a nonconfidential run history from each Abaqus release and solver mode you intend to use. Start with known success, known failure, and active/incomplete captures. Compare phase durations and status totals line by line against the original diagnostic files. Record unsupported markers and compare the selected worker set and timing windows. No Abaqus job needs to be started for retrospective format validation.

For performance comparisons, document the configuration and control the workload and capture windows. Check numerical equivalence and physical validity separately before treating a timing difference as an improvement.
