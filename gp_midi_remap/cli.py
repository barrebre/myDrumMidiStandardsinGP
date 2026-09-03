"""Command-line interface for gp-midi-remap."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_note_tables
from .transform import remap_midi_file

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
EXIT_PROCESSING_ERROR = 3


def default_output_path(input_path: Path) -> Path:
    """Derive the default output path: append ``_converted`` before the extension.

    ``song.mid`` -> ``song_converted.mid``. Files with no extension get the
    suffix appended directly (``song`` -> ``song_converted``).
    """
    if input_path.suffix:
        return input_path.with_name(f"{input_path.stem}_converted{input_path.suffix}")
    return input_path.with_name(f"{input_path.name}_converted")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gp-midi-remap",
        description=(
            "Remap MIDI drum note numbers so imports land on the tracks/lines "
            "you expect in Guitar Pro, using layered default + user-provided "
            "note-conversion and note-mapping tables."
        ),
    )
    parser.add_argument("input", type=Path, help="Path to the input MIDI file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "Output MIDI file path. Defaults to the input filename with "
            "'_converted' appended before the extension."
        ),
    )
    parser.add_argument(
        "--note-conversion",
        type=Path,
        default=None,
        help=(
            "Path to a user JSON file mapping original note numbers to "
            "replacement note numbers. Merged on top of the built-in "
            "defaults (user entries win)."
        ),
    )
    parser.add_argument(
        "--note-mapping",
        type=Path,
        default=None,
        help=(
            "Path to a user JSON file mapping (converted) note numbers to "
            "the note number that lands on the expected Guitar Pro line. "
            "Merged on top of the built-in defaults (user entries win)."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return EXIT_PROCESSING_ERROR

    output_path = args.output if args.output is not None else default_output_path(
        args.input
    )

    if output_path.exists() and not args.force:
        print(
            f"error: output file already exists: {output_path} "
            "(use --force to overwrite)",
            file=sys.stderr,
        )
        return EXIT_PROCESSING_ERROR

    try:
        tables = load_note_tables(
            note_conversion_path=args.note_conversion,
            note_mapping_path=args.note_mapping,
        )
    except ConfigError as exc:
        print("Config validation failed:", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    try:
        summary = remap_midi_file(str(args.input), str(output_path), tables)
    except (OSError, ValueError, EOFError) as exc:
        print(f"error: failed to process MIDI file: {exc}", file=sys.stderr)
        return EXIT_PROCESSING_ERROR

    print(f"Wrote {output_path}")
    print(summary.format_report())
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
