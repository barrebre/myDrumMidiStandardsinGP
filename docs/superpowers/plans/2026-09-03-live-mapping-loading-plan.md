# Live Mapping Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load default MIDI note mappings from files next to the executable instead of embedding them, so users can update mappings without rebuilding.

**Architecture:** Add a `_resolve_defaults_dir()` function to detect frozen vs. normal Python execution and locate default JSON files. Replace the current embedded resource loading with external file loading at runtime. All three default files load fresh on each `load_note_tables()` call, with validation errors aggregated and reported together.

**Tech Stack:** Python 3.9+, mido, importlib.resources (pathlib context manager), unittest.mock for testing frozen state simulation.

---

## File Structure

**Modified:**
- `gp_midi_remap/config.py` — Add directory resolution, new external file loader, update `load_note_tables()` to load from resolved directory
- `tests/test_config.py` — Add new tests for live loading, directory resolution, error aggregation
- `README.md` — Update deployment/usage section with guidance on bundling defaults

---

## Task 1: Add Directory Resolution Helper

**Files:**
- Modify: `gp_midi_remap/config.py` (lines 1-50)

- [ ] **Step 1: Add imports for sys and frozen-state detection**

Add to the top of `gp_midi_remap/config.py` after existing imports:

```python
import sys
```

- [ ] **Step 2: Add the `_resolve_defaults_dir()` function**

Insert after the `_DEFAULTS_PACKAGE` definition (around line 12) and before the `ConfigError` class:

```python
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
```

- [ ] **Step 3: Run existing tests to ensure no regressions**

Run: `pytest tests/test_config.py -v`

Expected: All existing tests pass (7-8 tests).

- [ ] **Step 4: Commit**

```bash
git add gp_midi_remap/config.py
git commit -m "Add _resolve_defaults_dir() helper for external defaults loading

- Detect frozen executables via sys.frozen
- Route frozen exes to executable directory
- Route normal Python to package defaults directory
- Provide fallback for edge cases

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Replace Embedded Resource Loading with External File Loading

**Files:**
- Modify: `gp_midi_remap/config.py` (lines 28-31)

- [ ] **Step 1: Add new `_load_external_json()` helper**

Replace the current `_load_default_json()` function. Delete lines 28-30 and add:

```python
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
```

- [ ] **Step 2: Keep the existing `_read_json_file()` but reuse it**

Verify that `_read_json_file()` (lines 33-46) already exists and does the same thing. It will remain unchanged. Both functions now use the same error-accumulation pattern.

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `pytest tests/test_config.py -v`

Expected: All existing tests still pass (the old `_load_default_json()` is no longer called, but we haven't changed the public API yet).

- [ ] **Step 4: Commit**

```bash
git add gp_midi_remap/config.py
git commit -m "Add _load_external_json() for external default file loading

- Replaces embedded _load_default_json()
- Accumulates errors for aggregated reporting
- Handles missing files, parse errors, read errors uniformly

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Update `load_note_tables()` to Load from External Defaults

**Files:**
- Modify: `gp_midi_remap/config.py` (lines 123-138)

- [ ] **Step 1: Replace the default loading logic in `load_note_tables()`**

Replace lines 125-127 (the three `_load_default_json()` calls) with:

```python
    # Resolve the directory where default files are located
    defaults_dir = _resolve_defaults_dir()
    
    # Load and validate each default file; accumulate errors
    conversion = _validate_conversion(
        _load_external_json(defaults_dir / "defaultNoteConversion.json", errors) or {},
        f"{defaults_dir / 'defaultNoteConversion.json'}",
        errors,
    )
    mapping = _validate_mapping(
        _load_external_json(defaults_dir / "defaultNoteMapping.json", errors) or {},
        f"{defaults_dir / 'defaultNoteMapping.json'}",
        errors,
    )
    note_types = _validate_note_types(
        _load_external_json(defaults_dir / "defaultNoteTypes.json", errors) or {},
        f"{defaults_dir / 'defaultNoteTypes.json'}",
        errors,
    )
```

- [ ] **Step 2: Verify the rest of `load_note_tables()` unchanged**

Lines 128-138 (user file handling and error raising) remain unchanged. The precedence is now:
  1. Defaults (from external directory)
  2. User files (from CLI args)
  3. Both trigger errors if missing/invalid

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/test_config.py::test_defaults_only_load_empty_tables -v`

Expected: FAIL because defaults are now loaded from external files, which don't exist in the test environment.

This is expected—we'll handle it in Task 4 (test setup).

- [ ] **Step 4: Commit**

```bash
git add gp_midi_remap/config.py
git commit -m "Update load_note_tables() to load defaults from external directory

- Call _resolve_defaults_dir() to locate default files
- Load each default file fresh on every call (no caching)
- Aggregate validation errors from all defaults together
- Maintain user-file override precedence

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Add Test Fixture for Default File Mocking

**Files:**
- Modify: `tests/test_config.py` (add at top after imports)

- [ ] **Step 1: Add imports**

Add to the top of `tests/test_config.py` after existing imports:

```python
import sys
```

- [ ] **Step 2: Add pytest fixture to create temporary default files**

Add this after the existing `write_json()` helper (around line 12):

```python
@pytest.fixture
def temp_defaults_dir(tmp_path):
    """Create temporary default JSON files in a temp directory.
    
    Returns the directory path. Files are populated with the current defaults.
    """
    defaults = {
        "defaultNoteConversion.json": {"notes": [{"originalNote": 80, "replacementNote": 97}, {"originalNote": 42, "replacementNote": 46}]},
        "defaultNoteMapping.json": {"lines": [{"noteNumbers": [36, 35]}, {"noteNumbers": [38]}, {"noteNumbers": [45, 43]}, {"noteNumbers": [48, 47]}, {"noteNumbers": [46, 51, 53]}, {"noteNumbers": [49, 57, 97]}]},
        "defaultNoteTypes.json": {"notes": {"36": "kick", "38": "snare", "42": "closed hi-hat", "46": "open hi-hat", "49": "high crash", "51": "ride", "52": "china", "53": "ride bell", "57": "low crash", "97": "crash pinch"}},
    }
    for filename, data in defaults.items():
        write_json(tmp_path / filename, data)
    return tmp_path
```

- [ ] **Step 3: Add fixture to mock frozen executable state**

Add this fixture right after `temp_defaults_dir`:

```python
@pytest.fixture
def mock_frozen_executable(tmp_path, monkeypatch):
    """Mock sys.frozen to simulate PyInstaller frozen executable.
    
    Yields a tuple (mock_sys, defaults_dir) where you can set sys.executable.
    """
    defaults = {
        "defaultNoteConversion.json": {"notes": [{"originalNote": 80, "replacementNote": 97}]},
        "defaultNoteMapping.json": {"lines": [{"noteNumbers": [36]}]},
        "defaultNoteTypes.json": {"notes": {"36": "kick"}},
    }
    for filename, data in defaults.items():
        write_json(tmp_path / filename, data)
    
    fake_exe = tmp_path / "my_app"
    fake_exe.write_text("fake executable")
    
    monkeypatch.setattr(sys, 'frozen', True)
    monkeypatch.setattr(sys, 'executable', str(fake_exe))
    return tmp_path
```

- [ ] **Step 4: Update `test_defaults_only_load_empty_tables()` to use the fixture**

Replace the existing test (lines 15-19) with:

```python
def test_defaults_only_load_empty_tables(temp_defaults_dir, monkeypatch):
    """Defaults load from external directory, not embedded."""
    # Mock _resolve_defaults_dir to return our temp directory
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    tables = load_note_tables()
    assert tables.note_conversion == {80: 97, 42: 46}
    assert 36 in tables.note_mapping
    assert tables.note_types[36] == "kick"
```

- [ ] **Step 5: Run the updated test**

Run: `pytest tests/test_config.py::test_defaults_only_load_empty_tables -v`

Expected: PASS

- [ ] **Step 6: Run all config tests**

Run: `pytest tests/test_config.py -v`

Expected: All tests pass except those with user-file tests that need fixtures (will fix those next).

- [ ] **Step 7: Commit**

```bash
git add tests/test_config.py
git commit -m "Add fixtures for temp default files and frozen executable mocking

- temp_defaults_dir: creates standard test defaults
- mock_frozen_executable: simulates PyInstaller frozen state
- Update test_defaults_only_load_empty_tables to mock directory resolution

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Update Existing Tests to Use Fixture

**Files:**
- Modify: `tests/test_config.py` (lines 22-31)

- [ ] **Step 1: Update `test_current_wrapped_user_files_are_supported()` to mock defaults**

Replace lines 22-32 with:

```python
def test_current_wrapped_user_files_are_supported(temp_defaults_dir, tmp_path, monkeypatch):
    """User-provided wrapped format files merge over defaults."""
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    conversion_file = write_json(
        tmp_path / "conv.json",
        {"notes": [{"originalNote": 80, "replacementNote": 97}]},
    )
    mapping_file = write_json(tmp_path / "map.json", {"lines": [{"noteNumbers": [36, 35]}]})
    tables = load_note_tables(conversion_file, mapping_file)
    assert tables.note_conversion[80] == 97
    assert tables.note_mapping[36] == 36
    assert tables.note_mapping[35] == 35
```

- [ ] **Step 2: Update `test_user_override_merges_over_defaults()`**

Replace lines 34-45 with:

```python
def test_user_override_merges_over_defaults(temp_defaults_dir, tmp_path, monkeypatch):
    """User files override defaults (merge precedence)."""
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    conversion_file = write_json(tmp_path / "conv.json", {"38": 40, "42": 22})
    mapping_file = write_json(tmp_path / "map.json", {"40": 41})

    tables = load_note_tables(
        note_conversion_path=conversion_file, note_mapping_path=mapping_file
    )

    assert tables.note_conversion[38] == 40
    assert tables.note_conversion[42] == 22  # User value wins
    assert tables.note_mapping[40] == 41
```

- [ ] **Step 3: Update `test_user_file_keys_win_over_defaults()`**

Replace lines 47-54 with:

```python
def test_user_file_keys_win_over_defaults(temp_defaults_dir, tmp_path, monkeypatch):
    """User file values win over defaults for the same key."""
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    conversion_file = write_json(tmp_path / "conv.json", {"38": 99})
    tables = load_note_tables(note_conversion_path=conversion_file)
    assert tables.note_conversion[38] == 99  # User wins, not default
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_config.py -v -k "override or wrapped"`

Expected: All three updated tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_config.py
git commit -m "Update merge/override tests to mock external defaults

- Add monkeypatch fixture to all tests that depend on defaults
- Maintain test semantics (user wins over defaults)
- All tests now use temp_defaults_dir fixture

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Add New Test for Live Reloading

**Files:**
- Modify: `tests/test_config.py` (add after existing tests, around line 124)

- [ ] **Step 1: Write test for live defaults reload**

Add after `test_boolean_value_rejected()`:

```python
def test_defaults_are_reloaded_on_each_call(temp_defaults_dir, monkeypatch):
    """Each load_note_tables() call reads defaults fresh from disk."""
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    
    # First load
    tables1 = load_note_tables()
    assert tables1.note_conversion[80] == 97
    
    # Modify the default file on disk
    modified_defaults = {
        "notes": [{"originalNote": 80, "replacementNote": 100}]  # Changed 97 -> 100
    }
    write_json(temp_defaults_dir / "defaultNoteConversion.json", modified_defaults)
    
    # Second load should see the updated file
    tables2 = load_note_tables()
    assert tables2.note_conversion[80] == 100
```

- [ ] **Step 2: Run the new test**

Run: `pytest tests/test_config.py::test_defaults_are_reloaded_on_each_call -v`

Expected: PASS (proves no caching across calls).

- [ ] **Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "Add test for live defaults reloading

- Verify defaults are re-read from disk on each load_note_tables() call
- Modify defaults file and verify changes are observed immediately
- No caching of defaults across invocations

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: Add Test for Missing Default Files

**Files:**
- Modify: `tests/test_config.py` (add after previous new test)

- [ ] **Step 1: Write test for missing default file**

Add after `test_defaults_are_reloaded_on_each_call()`:

```python
def test_missing_default_file_raises_config_error(tmp_path, monkeypatch):
    """Missing default files raise ConfigError with file-not-found message."""
    # Create an empty temp dir (no default files)
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: empty_dir,
    )
    
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables()
    
    # Should report all three missing files
    errors_text = "\n".join(exc_info.value.errors)
    assert "defaultNoteConversion.json" in errors_text
    assert "defaultNoteMapping.json" in errors_text
    assert "defaultNoteTypes.json" in errors_text
    assert all("file not found" in e for e in exc_info.value.errors)
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_config.py::test_missing_default_file_raises_config_error -v`

Expected: PASS (all three files are required and their absence triggers errors).

- [ ] **Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "Add test for missing default files

- Verify ConfigError raised when defaults directory lacks required files
- Check that all three missing files are reported together
- Aggregated error reporting works for defaults

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: Add Test for Invalid Default JSON

**Files:**
- Modify: `tests/test_config.py` (add after previous test)

- [ ] **Step 1: Write test for invalid default JSON**

Add after `test_missing_default_file_raises_config_error()`:

```python
def test_invalid_default_json_raises_config_error(temp_defaults_dir, monkeypatch):
    """Invalid JSON in a default file raises ConfigError with parse error."""
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    
    # Corrupt one default file
    (temp_defaults_dir / "defaultNoteConversion.json").write_text("{not valid json")
    
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables()
    
    # Should report JSON parse error
    errors_text = "\n".join(exc_info.value.errors)
    assert "defaultNoteConversion.json" in errors_text
    assert "invalid JSON" in errors_text
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_config.py::test_invalid_default_json_raises_config_error -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "Add test for invalid default JSON

- Verify ConfigError raised when default file has syntax error
- Check that the error message identifies the file and problem
- Consistent error reporting for defaults and user files

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 9: Add Test for Frozen Executable Directory Resolution

**Files:**
- Modify: `tests/test_config.py` (add after previous test)

- [ ] **Step 1: Write test for frozen executable path**

Add after `test_invalid_default_json_raises_config_error()`:

```python
def test_resolve_defaults_dir_frozen_uses_executable_dir(mock_frozen_executable, monkeypatch):
    """When frozen, _resolve_defaults_dir() returns executable's parent directory."""
    from gp_midi_remap.config import _resolve_defaults_dir
    
    result = _resolve_defaults_dir()
    
    # Should be the parent of sys.executable (the executable's directory)
    assert result == mock_frozen_executable
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_config.py::test_resolve_defaults_dir_frozen_uses_executable_dir -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "Add test for frozen executable defaults resolution

- Verify _resolve_defaults_dir() returns executable directory when frozen
- Simulate PyInstaller frozen state via sys.frozen mock
- Executable directory contains bundled default JSON files

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 10: Add Test for Normal Python Defaults Resolution

**Files:**
- Modify: `tests/test_config.py` (add after previous test)

- [ ] **Step 1: Write test for normal Python path**

Add after `test_resolve_defaults_dir_frozen_uses_executable_dir()`:

```python
def test_resolve_defaults_dir_normal_uses_package_dir(monkeypatch):
    """When not frozen, _resolve_defaults_dir() returns package defaults directory."""
    from gp_midi_remap.config import _resolve_defaults_dir
    
    # Ensure sys.frozen is False (or not set)
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    
    result = _resolve_defaults_dir()
    
    # Should point to gp_midi_remap/defaults
    assert result.exists()
    assert result.name == "defaults"
    assert (result / "defaultNoteConversion.json").exists()
    assert (result / "defaultNoteMapping.json").exists()
    assert (result / "defaultNoteTypes.json").exists()
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_config.py::test_resolve_defaults_dir_normal_uses_package_dir -v`

Expected: PASS (because the defaults directory exists in the source tree).

- [ ] **Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "Add test for normal Python defaults resolution

- Verify _resolve_defaults_dir() returns package defaults for normal invocation
- Check that all three default files exist in the resolved directory
- Works for both source tree and installed package

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 11: Run Full Test Suite

**Files:**
- No changes

- [ ] **Step 1: Run all config tests**

Run: `pytest tests/test_config.py -v`

Expected: All 16+ tests pass.

- [ ] **Step 2: Run all tests (including CLI and transform)**

Run: `pytest tests/ -v`

Expected: All tests pass. CLI tests should still work because they use the mock defaults fixture or provide their own files.

- [ ] **Step 3: No commit needed**

Tests are already committed per task.

---

## Task 12: Update README with Deployment Guidance

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update "Install" section**

Find the "## Install" section (around line 32) and add a note about bundling defaults:

```markdown
## Install

```bash
pip install -e .
# or, without installing:
pip install -r requirements.txt
```

### Bundling with Frozen Executables

If you build a frozen executable (PyInstaller, cx_Freeze), bundle the three default JSON files with it:

- `defaultNoteConversion.json`
- `defaultNoteMapping.json`
- `defaultNoteTypes.json`

Place these files in the same directory as the executable. For PyInstaller, use:

```bash
pyinstaller --add-data "gp_midi_remap/defaults:." myapp.py
```

The executable will load defaults from its directory at runtime, allowing users to patch mappings without rebuilding.
```

- [ ] **Step 2: Update "Usage" section to mention default updates**

Find "## Usage" (around line 40) and add a paragraph before the JSON format section:

```markdown
### Updating Default Mappings

To change the default note-conversion or note-mapping tables without rebuilding the executable:

1. Locate the default files next to the executable (or in `gp_midi_remap/defaults/` for pip installs).
2. Edit `defaultNoteConversion.json` or `defaultNoteMapping.json` directly.
3. Run the tool again—it will load the updated defaults automatically.

No rebuild or re-installation needed.
```

- [ ] **Step 3: View the edited README to verify**

Run: `head -100 README.md`

Verify both sections are clear and consistent.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add deployment guidance for live defaults

- Document bundling defaults with frozen executables
- Explain how to patch mappings without rebuilding
- Add section on updating defaults at runtime

Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 13: Verify No Breaking Changes

**Files:**
- No changes

- [ ] **Step 1: Run CLI end-to-end test**

Run: `pytest tests/test_cli.py::test_cli_end_to_end_default_output -v`

Expected: PASS (user files still override defaults; precedence unchanged).

- [ ] **Step 2: Test with custom defaults via CLI flags**

Run: `pytest tests/test_cli.py::test_cli_refuses_overwrite_without_force -v`

Expected: PASS (CLI flag behavior unchanged).

- [ ] **Step 3: Check exit codes**

Run: `pytest tests/test_cli.py -v -k "exit_code"`

Expected: All exit code tests pass (2 for config error, 3 for processing error).

- [ ] **Step 4: No commit needed**

All tests already committed.

---

## Summary

The plan implements live default loading by:

1. ✅ Adding `_resolve_defaults_dir()` to detect frozen vs. normal Python execution
2. ✅ Replacing `_load_default_json()` with `_load_external_json()` for consistent error handling
3. ✅ Updating `load_note_tables()` to load fresh from external files on each call
4. ✅ Adding comprehensive tests for resolution, reloading, error aggregation, and frozen states
5. ✅ Updating README with deployment guidance

**Precedence:** CLI flags > external defaults > (no embedded defaults)

**Error handling:** All validation errors aggregated, `ConfigError` raised on any problem, CLI exits with code 2.

**Caching:** None—defaults re-read on every `load_note_tables()` call.

**Backward compatibility:** `--note-conversion` and `--note-mapping` flags unchanged; JSON schemas unchanged; exit codes unchanged.
