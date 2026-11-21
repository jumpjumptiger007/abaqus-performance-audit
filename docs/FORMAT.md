# Evidence rules and report formats

## Diagnostic input

Select one execution's English-language diagnostic files. The CLI supports LF and CRLF text with UTF-8, including a UTF-8 BOM, or CP1252. It reads up to each file's opening size. A changed file, undecodable line, line over 64 KiB, or final unterminated line is identified as a limitation. Re-audit stable copies after completion when collecting final results. An unfinished record can resemble a complete marker, so the parser ignores final lines without a newline.

| Evidence | Supported in V1 |
| --- | --- |
| Termination | Recognized job-level completed or aborted markers, solver terminal phrases, selected convergence errors, and explicit toolchain failures. A warning or generic error alone does not determine termination. Recognized progress without terminal evidence is incomplete. Conflicting terminal evidence can produce an unknown state. |
| Release | A supported Abaqus release banner with a four-digit year and optional HF or FD number. Conflicting releases yield an unavailable value. |
| Progress | Recognized phase or progress markers and the last usable Standard status row. The indicated step time is simulation time. |
| Phase wall duration | A single matching begin/end pair in a stable `.log` for compiling, linking, input preprocessing, Standard analysis, or Explicit analysis. Accepted clocks are ISO-like date/time with an optional UTC offset and supported US month/day timestamp forms. Timestamps may be attached to the marker or on the next nonblank line. Offset-aware timestamps and timezone-free timestamps have separate bases. Clock changes can skew timezone-free estimates. |
| Job elapsed | A single matching pair of timestamped `Begin Analysis Job` and `End Analysis Job` wrapper records. If unavailable, check separately labeled solver phase or timing summary measurements. Capture duration is a separate metric. |
| Solver wall time | A `WALLCLOCK TIME (SEC)` or `(SECONDS)` value near a recognized job time summary in a stable `.msg` or `.dat`. Conflicting values yield an unavailable value. |
| Standard increments | A `.sta` table with `STEP INC ATT SEVERE EQUIL TOTAL` followed by numeric attempt rows. Identical rows are deduplicated. Conflicting rows invalidate their increments. Counts cover usable observed rows and need not cover an entire analysis. Explicit heartbeat tables have different semantics and are outside V1's numeric status parser. |
| Cutbacks | An unsuccessful attempt marked with `U` followed by the next numeric attempt of the same step and increment with a smaller increment size. Explicit matching cutback message occurrences are reported separately. Counts may overlap and are not added together. |

The parser uses a limited set of English text signatures. Fixtures are synthetic and do not certify any particular release, locale, solver configuration, restart mode, or user output format. Release documentation describes the role of each output file. [Abaqus output reference](https://docs.software.vt.edu/abaqusv2026/English/SIMACAEOUTRefMap/simaout-c-output.htm), [Convergence diagnostics](https://docs.software.vt.edu/abaqusv2025/English/TsoUserMap/tso-c-usr-sizing-NonLin-Summary.htm)

Every unclassified nonblank line contributes to a per-file count. By default, the first five references in each per-file category preserve anonymous filename, line number, and category. An optional separate local directory contains the original path mapping and bounded text for individual lines. Oversized or unterminated records are represented by their locators.

## Monitoring input and CSV

The monitor writes UTF-8 JSON Lines with schema version 1. A start record describes the supplied process identities, configured sampling interval, and logical processors visible to the monitor. Samples include a UTC timestamp and monotonic elapsed seconds, process readings, and any available system observations. A terminal record can describe duration limit, all-process exit, or interruption. A missing terminal record leaves overall capture duration unavailable. The reader recovers complete sample lines from incomplete captures.

- **Process CPU** is accumulated user plus privileged CPU time in seconds. The normalized percentage is 100 × CPU-seconds delta ÷ elapsed-seconds delta ÷ logical processors reported to the monitor. Capacity is the logical CPU count exposed to the PowerShell host by its runtime. Affinity, processor groups or quotas can make this different from capacity available to the solver. The full-set summary weights valid intervals by duration and requires both adjacent readings for every selected process. The first sample alone provides no utilization.
- **Working set** is resident process memory in bytes. Peak working-set sum uses full-set sampling ticks and can count shared pages more than once. It does not measure committed bytes.
- **System memory** uses Windows free/available physical memory and the visible physical total, converted from KiB to bytes. The minimum is a sampled workstation indicator. [Windows operating system counters](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-operatingsystem)
- **Process transfer counts** are cumulative Windows read/write transfer bytes for the explicitly selected PIDs. They can include traffic through sources other than physical disk. The audit totals valid adjacent deltas per process. Missing readings split the observed intervals. [Windows process counters](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-process)
- **Optional disk throughput** uses local formatted physical-disk `_Total` read/write bytes per second. It represents the workstation. Rates can be unavailable or stale depending on the provider. Output sizes are snapshots of selected file lengths.
- **Process lifetime** is exit time minus start time when the exit and both timestamps can be observed. Live or interrupted processes can have a last observed age with unknown lifetime. The monitor keeps a handle to each selected process while observing it and stops sampling it after exit.
- **Cadence** defaults to five seconds and accepts one to 300 seconds, with at most 16 explicit PIDs. Capture duration defaults to one hour and accepts one second to 24 hours. Each sampling tick issues up to three local CIM queries with a short provider timeout request. Provider latency can add drift and extend the time needed to finish an in-flight tick. Actual sample intervals drive the calculations.

The aggregate CSV has one row per anonymous process per tick. Elapsed time is relative to capture start. Each row repeats the same system readings for that tick, so deduplicate by elapsed time for workstation time series. Null values are blank. The full UTC timestamps and original process names stay in the raw capture. CPU percentages, status, and bytes can be plotted directly from the CSV.

## Diagnoses and run comparison

| Trigger | Interpretation |
| --- | --- |
| Mean normalized CPU at or below 20% over at least 30 seconds and 80% of the capture or observed window | Investigate worker coverage, waiting, or serial phases. |
| Minimum valid system available memory below 10% of visible physical memory | Check paging and other workstation activity. |
| At least three observed cutbacks or three recognized cutback message occurrences | Check referenced increments and convergence evidence. |
| Selected output files total at least 1 GiB | Investigate whether writes contribute to elapsed time with a controlled output-frequency comparison. |
| Terminal failure evidence | Check whether early termination reduced the work performed. |

The fixed thresholds prioritize investigation. They do not establish root causes. The JSON separates evidence values, hypothesized explanations, recommendations, and measurement limitations.

Comparison reads schema-version-1 `audit.json` files up to 16 MiB each. Anonymous run IDs must differ. The comparison rejects incompatible bases, reports missing values, flags partial status and capture evidence, checks monitor scope and coverage, and shows operator-supplied configuration differences. Workloads and physics still need review. Sampled memory and disk peaks use comparable coverage only when the required counter observations are present. Reported changes are candidate minus baseline. Percent change is unavailable with a zero baseline.

## Future read-only extraction

A future release-specific adapter can run independently under the matching Abaqus Python environment. It could use `odbAccess.openOdb(path, readOnly=True)` for an explicitly selected ODB, close the handle, and export release, adapter version, typed metrics, unit, evidence scope, and completeness as locally written neutral records. Keep the adapter and proprietary runtime outside the core package. A future core reader would validate an independently versioned schema before using its metrics. V1 performs only size inspection on selected ODB files. [Abaqus job diagnostics reference](https://docs.software.vt.edu/abaqusv2026/English/SIMACAECAERefMap/simacae-c-outoverview.htm)
