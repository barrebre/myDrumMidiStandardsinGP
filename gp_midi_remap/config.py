"""Config loading, validation, and merge-precedence logic."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

MIDI_NOTE_MIN = 0
MIDI_NOTE_MAX = 127
_DEFAULTS_PACKAGE = "gp_midi_remap.defaults"


def _resolve_defaults_dir() -> Path:
    """Resolve the directory containing default JSON files.
    
    For frozen executables (PyInstaller, cx_Freeze), use the executable's parent directory.
    For normal Python invocations, use the package's defaults directory.
    
    Returns:
        Path to the directory containing defaultNoteConversion.json,
        defaultNoteMapping.json, and defaultNoteTypes.json.
    """
    # Check if running as a frozen executable
    if getattr(sys, 'frozen', False):
        # Frozen: executable is at sys.executable, defaults beside it
        return Path(sys.executable).parent
    
    # Normal Python: use package defaults directory
    # resources.files() returns a Traversable; convert to Path
    try:
        return Path(resources.files(_DEFAULTS_PACKAGE))
    except (TypeError, AttributeError):
        # Fallback: construct path relative to this module
        return Path(__file__).parent / "defaults"


class ConfigError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass
class NoteTables:
    note_conversion: dict[int, int] = field(default_factory=dict)
    note_mapping: dict[int, int] = field(default_factory=dict)
    note_types: dict[int, str] = field(default_factory=dict)


def _load_external_json(path: Path, errors: list[str]) -> object | None:
    """Load JSON from an external file, accumulating errors.
    
    Used for both default and user-provided JSON files. Returns the parsed
    object on success, None on failure. All errors (missing file, read error,
    JSON parse error) are appended to the errors list for aggregated reporting.
    """
    if not path.exists():
        errors.append(f"{path}: file not found")
        return None
    if not path.is_file():
        errors.append(f"{path}: not a file")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"{path}: could not read file ({exc})")
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})")
    return None


def _read_json_file(path: Path, errors: list[str]) -> object | None:
    if not path.exists():
        errors.append(f"{path}: file not found")
        return None
    if not path.is_file():
        errors.append(f"{path}: not a file")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"{path}: could not read file ({exc})")
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})")
    return None


def _validate_note_table(data: object, source: str, errors: list[str]) -> dict[int, int]:
    result: dict[int, int] = {}
    if not isinstance(data, dict):
        errors.append(f"{source}: expected a JSON object mapping note numbers to note numbers, got {type(data).__name__}")
        return result
    for raw_key, raw_value in data.items():
        try:
            key = int(raw_key)
        except (TypeError, ValueError):
            errors.append(f"{source}: key {raw_key!r} is not an integer note number")
            continue
        if not isinstance(raw_value, int) or isinstance(raw_value, bool):
            errors.append(f"{source}: value for note {raw_key!r} must be an integer, got {raw_value!r}")
            continue
        if not MIDI_NOTE_MIN <= key <= MIDI_NOTE_MAX or not MIDI_NOTE_MIN <= raw_value <= MIDI_NOTE_MAX:
            errors.append(f"{source}: note mapping {key}->{raw_value} is out of MIDI note range (0-127)")
            continue
        result[key] = raw_value
    return result


def _validate_conversion(data: object, source: str, errors: list[str]) -> dict[int, int]:
    if not isinstance(data, dict) or "notes" not in data:
        return _validate_note_table(data, source, errors)
    entries = data["notes"]
    if not isinstance(entries, list):
        errors.append(f"{source}.notes: expected an array")
        return {}
    result: dict[int, int] = {}
    for entry in entries:
        if not isinstance(entry, dict) or "originalNote" not in entry or "replacementNote" not in entry:
            errors.append(f"{source}.notes: each entry needs originalNote and replacementNote")
            continue
        result.update(_validate_note_table({entry["originalNote"]: entry["replacementNote"]}, source, errors))
    return result


def _validate_mapping(data: object, source: str, errors: list[str]) -> dict[int, int]:
    if not isinstance(data, dict) or "lines" not in data:
        return _validate_note_table(data, source, errors)
    lines = data["lines"]
    if not isinstance(lines, list):
        errors.append(f"{source}.lines: expected an array")
        return {}
    result: dict[int, int] = {}
    for line in lines:
        if not isinstance(line, dict) or not isinstance(line.get("noteNumbers"), list):
            errors.append(f"{source}.lines: each entry needs a noteNumbers array")
            continue
        for note in line["noteNumbers"]:
            result.update(_validate_note_table({note: note}, source, errors))
    return result


def _validate_note_types(data: object, source: str, errors: list[str]) -> dict[int, str]:
    if not isinstance(data, dict) or not isinstance(data.get("notes"), dict):
        errors.append(f"{source}: expected an object with a notes object")
        return {}
    result: dict[int, str] = {}
    for raw_key, value in data["notes"].items():
        try:
            key = int(raw_key)
        except (TypeError, ValueError):
            errors.append(f"{source}: key {raw_key!r} is not an integer note number")
            continue
        if not MIDI_NOTE_MIN <= key <= MIDI_NOTE_MAX:
            errors.append(f"{source}: key {raw_key!r} is out of MIDI note range (0-127)")
        elif not isinstance(value, str):
            errors.append(f"{source}: value for note {raw_key!r} must be a string")
        else:
            result[key] = value
    return result


def load_note_tables(note_conversion_path: Path | None = None, note_mapping_path: Path | None = None) -> NoteTables:
    errors: list[str] = []
    conversion = _validate_conversion(_load_default_json("defaultNoteConversion.json"), "built-in defaultNoteConversion", errors)
    mapping = _validate_mapping(_load_default_json("defaultNoteMapping.json"), "built-in defaultNoteMapping", errors)
    note_types = _validate_note_types(_load_default_json("defaultNoteTypes.json"), "built-in defaultNoteTypes", errors)
    if note_conversion_path is not None:
        raw = _read_json_file(note_conversion_path, errors)
        if raw is not None:
            conversion.update(_validate_conversion(raw, str(note_conversion_path), errors))
    if note_mapping_path is not None:
        raw = _read_json_file(note_mapping_path, errors)
        if raw is not None:
            mapping.update(_validate_mapping(raw, str(note_mapping_path), errors))
    if errors:
        raise ConfigError(errors)
    return NoteTables(conversion, mapping, note_types)
