"""Offline command-line entry point."""
import argparse
import sys
from contextlib import nullcontext

from . import __version__
from .analysis import CONFIG_FIELDS, OUTPUT_SUFFIXES, audit, validate_run_id
from .comparison import compare
from .logs import SUFFIXES
from .paths import local_path, prepare_directories
from .reporting import timeseries_writer, write_input_map, write_reports


def cpu_count(value):
    try:
        count = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Expected a CPU count between 1 and 65536") from None
    if not 1 <= count <= 65536:
        raise argparse.ArgumentTypeError("Expected a CPU count between 1 and 65536")
    return count


def parser():
    root = argparse.ArgumentParser(description="Audit selected local Abaqus and monitoring records.")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("audit", help="create aggregate reports for one run")
    inspect.add_argument("--log", action="append", default=[], metavar="FILE",
                         help="select a .log, .sta, .msg, or .dat file (repeatable)")
    inspect.add_argument("--monitor", metavar="FILE", help="select a raw monitor .jsonl file")
    inspect.add_argument("--output-file", action="append", default=[], metavar="FILE",
                         help="read the size only of a selected .odb, .sim, .fil, or .sel file (repeatable)")
    inspect.add_argument("--out-dir", required=True, metavar="NEW_DIR", help="new aggregate report directory")
    inspect.add_argument("--local-dir", metavar="NEW_DIR", help="new private directory for raw text and input aliases")
    inspect.add_argument("--encoding", choices=("utf-8", "cp1252"), default="utf-8",
                         help="diagnostic text encoding (default: utf-8)")
    for key, choices in CONFIG_FIELDS.items():
        inspect.add_argument("--" + key.replace("_", "-"), choices=choices, help="operator-supplied configuration")
    inspect.add_argument("--run-id", metavar="ID", help="stable anonymous ID for the simulation run")
    inspect.add_argument("--requested-cpus", type=cpu_count, help="operator-supplied requested solver CPU count")
    comparison = commands.add_parser("compare", help="compare audits to the first supplied report")
    comparison.add_argument("reports", nargs="+", metavar="AUDIT_JSON")
    comparison.add_argument("--out-dir", required=True, metavar="NEW_DIR")
    return root


def _select(values, suffixes):
    paths = [local_path(value) for value in values]
    if any(path.suffix.lower() not in suffixes for path in paths):
        raise ValueError("One or more selected inputs have an unsupported extension")
    if len(set(paths)) != len(paths):
        raise ValueError("Supply each selected input path once")
    return paths


def _audit_command(args, destination):
    run_id = validate_run_id(args.run_id)
    logs = _select(args.log, SUFFIXES)
    outputs = _select(args.output_file, OUTPUT_SUFFIXES)
    monitor = _select([args.monitor], {".jsonl"})[0] if args.monitor else None
    if not (logs or outputs or monitor):
        raise ValueError("Select at least one diagnostic, output, or monitoring file")
    local = local_path(args.local_dir) if args.local_dir else None
    config = {key: getattr(args, key) for key in (*CONFIG_FIELDS, "requested_cpus") if getattr(args, key) is not None}
    prepare_directories(destination, local)
    if local is not None:
        write_input_map(local, logs, monitor, outputs)
    raw_context = ((local / "diagnostic-lines.jsonl").open("x", encoding="utf-8", newline="\n")
                   if local is not None else nullcontext())
    with raw_context as raw, timeseries_writer(destination) as emit:
        report, _ = audit(logs, monitor, outputs, args.encoding, config, raw, emit, run_id=run_id)
    write_reports(destination, report)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        destination = local_path(args.out_dir)
        if args.command == "audit":
            _audit_command(args, destination)
        else:
            report = compare(_select(args.reports, {".json"}))
            prepare_directories(destination, None)
            write_reports(destination, report)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except FileExistsError:
        print("Error: an output path already exists.", file=sys.stderr)
        return 2
    except OSError:
        print("Error: a selected file is unreadable or an output could not be created.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Any partial output is local.", file=sys.stderr)
        return 130
    print("Local reports written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
