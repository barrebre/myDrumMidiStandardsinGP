# Live Mapping Loading Design

**Date:** 2026-09-03  
**Goal:** Remove dependency on rebuilding the executable when default MIDI note mappings are updated.

## Problem

Currently, default note-conversion and note-mapping tables are embedded in the package via `importlib.resources` and frozen into the executable by build tools. Any change to `defaultNoteConversion.json`, `defaultNoteMapping.json`, or `defaultNoteTypes.json` requires rebuilding and redistributing the executable. Users cannot patch mappings without rebuilding.

## Solution

Load default JSON files from the executable's directory at runtime, making them live configuration. The executable becomes a thin runner; mappings are separate deployment artifacts.

## Architecture

### 1. File Resolution

**Default files location:**
- For normal Python: `gp_midi_remap/defaults/` (package directory in source tree or installed package)
- For frozen executable: same directory as the running executable

Rationale: When the CLI is installed as a package (`pip install`), defaults live next to the code. When built as an executable (PyInstaller, etc.), the executable and its default files are bundled together, and the executable directory becomes the natural place to find them.

**Resolution algorithm** (in `config.py`):

```python
def _resolve_defaults_dir() -> Path:
    """Find the directory containing default JSON files.
    
    For frozen executables, use the executable's directory.
    For normal Python, use the package's defaults directory.
    """
    # Check if running as a frozen executable
    if getattr(sys, 'frozen', False):
        executable_dir = Path(sys.executable).parent
        return executable_dir
    
    # Normal Python: use package defaults directory
    return resources.files(_DEFAULTS_PACKAGE).joinpath('').as_file()
```

Once this directory is known, `config.py` will load the three files from it:
- `defaultNoteConversion.json`
- `defaultNoteMapping.json`
- `defaultNoteTypes.json`

### 2. Loading Behavior

Replace the current `_load_default_json()` call in `load_note_tables()` to:
1. Resolve the defaults directory
2. Read each required default file (fresh load on every call, no caching)
3. Validate each file with the existing validators (`_validate_conversion`, `_validate_mapping`, `_validate_note_types`)
4. Merge errors from all three files
5. Add errors to the shared `errors` list so they report together with user-file errors in the same `ConfigError`

If any default file is missing, unreadable, or invalid, `load_note_tables()` will raise `ConfigError` with all problems aggregated, and the CLI will exit with code 2 (same as user-file validation failures).

### 3. Merge Precedence

Order (highest precedence first):
1. CLI-specified file paths (`--note-conversion`, `--note-mapping`)
2. External default files (from executable directory or package)
3. *(Removed: embedded defaults)*

The `.update()` pattern remains unchanged; later calls overwrite earlier keys.

### 4. API Changes

`load_note_tables()` signature remains unchanged:

```python
def load_note_tables(note_conversion_path: Path | None = None, note_mapping_path: Path | None = None) -> NoteTables:
```

Internals change: no longer calls `_load_default_json()` with hardcoded filenames; instead calls `_load_external_json()` pointed at the resolved defaults directory.

`_load_external_json()` is a new helper: reads JSON from a file, returns None + error on failure.

### 5. Error Handling

All validation is aggregated and reported by `ConfigError`, matching the existing pattern:

```python
try:
    tables = load_note_tables()
except ConfigError as exc:
    print("Config validation failed:", file=sys.stderr)
    for error in exc.errors:
        print(f"  - {error}", file=sys.stderr)
    sys.exit(EXIT_CONFIG_ERROR)  # Code 2
```

Example error output:
```
Config validation failed:
  - gp_midi_remap/defaults/defaultNoteConversion.json: file not found
  - user-conversion.json: invalid JSON (Expecting value at line 3, column 5)
```

### 6. Testing

**New test cases:**
1. Load defaults from package directory (normal Python invocation)
2. Load defaults from executable directory (simulated frozen state)
3. Defaults are re-read on each `load_note_tables()` call (no caching)
4. Missing default file raises `ConfigError` with file-not-found message
5. Invalid default JSON raises `ConfigError` with parse error
6. Default file validation errors aggregate with user-file errors
7. CLI overrides still win over defaults (merge precedence test)
8. External defaults work with wrapped format (notes/lines arrays) and flat format

**Existing tests:** remain unchanged; they don't depend on how defaults are sourced.

## Deployment

When distributing:
1. **For pip-installable package:** include `gp_midi_remap/defaults/` JSON files in the package (via `pyproject.toml` `package-data`). ✓ Already done.
2. **For frozen executable (PyInstaller, cx_Freeze, etc.):** bundle the three JSON files in the same directory as the executable binary. Build tools (PyInstaller's `--add-data`) should copy them.
3. **For source tree usage:** defaults are in `gp_midi_remap/defaults/` as today.

Users may replace any of the three files beside the executable to patch mappings without rebuilding.

## Backward Compatibility

- `--note-conversion` and `--note-mapping` flags remain unchanged
- JSON schemas (flat, wrapped `notes`/`lines` formats) remain unchanged
- CLI exit codes unchanged
- Summary reporting unchanged
- The only user-visible change: updating default mappings no longer requires rebuilding the executable

## Testing Boundary

- Unit tests for `config.py` validate file loading, resolution, and error aggregation
- CLI integration tests validate end-to-end flow and exit codes
- No changes to transform or MIDI processing logic
