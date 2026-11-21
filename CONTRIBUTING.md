# Contributing

Use Python 3.10 or later and the standard library. Run `python3 -m unittest discover -s tests -v` from the repository root. On Windows, also exercise the PowerShell test and checklist for monitoring changes.

Add small synthetic fixtures for each new format, missing-data path, and marker precedence change. Explain the source and supported release range of parser assumptions. Review report output for inadvertent inclusion of raw text, identifiers, or new external dependencies. Keep comparisons conservative when the measurement scope changes.

Contributions can include original synthetic data and code you are entitled to license under Apache-2.0. Leave proprietary Abaqus files, documentation, models, university data, raw captures, and credentials out of the repository and issue tracker.

Keep real reports, captures, and local evidence outside the repository. Review the [publication checklist](SECURITY.md#publication-checklist) before preparing a shareable archive or Git history.
