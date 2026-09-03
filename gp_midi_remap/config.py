"""Config loading, validation, and merge-precedence logic.

Two note-number tables are used:

* ``note_conversion`` -- maps an original MIDI note number to a replacement
  note number (e.g. GP renders note 38 in a spot the user dislikes, so it's
  converted to another note number first).
* ``note_mapping`` -- maps a (possibly already-converted) note number to the
  note number that lands on the expected line/position in Guitar Pro.

Both tables are simple ``{note: note}`` JSON objects with integer keys
(as strings, since JSON object keys are always strings) and integer values,
each in the valid MIDI note range 0-127.

Resolution order: built-in defaults are loaded first, then an optional
user-supplied file is merged on top (user keys win on conflict, but do not
remove default keys that the user's file doesn't mention).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

MIDI_NOTE_MIN = 0
MIDI_NOTE_MAX = 127

_DEFAULTS_PACKAGE = "gp_midi_remap.defaults"
_DEFAULT_NOTE_CONVERSION_FILE = "defaultNoteConversion.json"
_DEFAULT_NOTE_MAPPING_FILE = "defaultNoteMapping.json"


class ConfigError(Exception):
    """Raised when one or more config files fail validation.

    Carries every detected problem (not just the first) so users can fix
    everything in one edit cycle.
    """

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "\n".join(self.errors)


@dataclass
class NoteTables:
    """Fully resolved, validated note-number lookup tables."""

    note_conversion: dict[int, int] = field(default_factory=dict)
    note_mapping: dict[int, int] = field(default_factory=dict)


def _load_default_json(filename: str) -> dict:
    with resources.files(_DEFAULTS_PACKAGE).joinpath(filename).open(
        "r", encoding="utf-8"
    ) as fh:
        return json.load(fh)


def _read_json_file(path: Path, errors: list[str]) -> dict | None:
    if not path.exists():
        errors.append(f"{path}: file not found")
        return None
    if not path.is_file():
        errors.append(f"{path}: not a file")
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path}: could not read file ({exc})")
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})")
        return None
    return data


def _validate_note_table(
    data: object, source: str, errors: list[str]
) -> dict[int, int]:
    """Validate a raw parsed JSON object as a note->note table.

    Collects every problem found rather than stopping at the first one.
    Returns the successfully-parsed entries; invalid entries are skipped.
    """
    result: dict[int, int] = {}

    if not isinstance(data, dict):
        errors.append(
            f"{source}: expected a JSON object mapping note numbers to note "
            f"numbers, got {type(data).__name__}"
        )
        return result

    for raw_key, raw_value in data.items():
        try:
            key = int(raw_key)
        except (TypeError, ValueError):
            errors.append(f"{source}: key {raw_key!r} is not an integer note number")
            continue

        if not isinstance(raw_value, int) or isinstance(raw_value, bool):
            errors.append(
                f"{source}: value for note {raw_key!r} must be an integer, "
                f"got {raw_value!r}"
            )
            continue

        if not (MIDI_NOTE_MIN <= key <= MIDI_NOTE_MAX):
            errors.append(
                f"{source}: key {raw_key!r} is out of MIDI note range "
                f"({MIDI_NOTE_MIN}-{MIDI_NOTE_MAX})"
            )
            continue

        if not (MIDI_NOTE_MIN <= raw_value <= MIDI_NOTE_MAX):
            errors.append(
                f"{source}: value {raw_value!r} for note {key} is out of MIDI "
                f"note range ({MIDI_NOTE_MIN}-{MIDI_NOTE_MAX})"
            )
            continue

        result[key] = raw_value

    return result


def load_note_tables(
    note_conversion_path: Path | None = None,
    note_mapping_path: Path | None = None,
) -> NoteTables:
    """Load and validate note tables, merging user overrides over defaults.

    Raises ConfigError (with every problem found) if any file is invalid.
    """
    errors: list[str] = []

    default_conversion_raw = _load_default_json(_DEFAULT_NOTE_CONVERSION_FILE)
    default_mapping_raw = _load_default_json(_DEFAULT_NOTE_MAPPING_FILE)

    conversion = _validate_note_table(
        default_conversion_raw, "built-in defaultNoteConversion", errors
    )
    mapping = _validate_note_table(
        default_mapping_raw, "built-in defaultNoteMapping", errors
    )

    if note_conversion_path is not None:
        raw = _read_json_file(note_conversion_path, errors)
        if raw is not None:
            conversion.update(
                _validate_note_table(raw, str(note_conversion_path), errors)
            )

    if note_mapping_path is not None:
        raw = _read_json_file(note_mapping_path, errors)
        if raw is not None:
            mapping.update(
                _validate_note_table(raw, str(note_mapping_path), errors)
            )

    if errors:
        raise ConfigError(errors)

    return NoteTables(note_conversion=conversion, note_mapping=mapping)
