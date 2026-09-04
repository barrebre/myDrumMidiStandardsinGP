"""Tests for gp_midi_remap.config: parsing, validation, merge precedence."""

import json
import sys

import pytest

from gp_midi_remap.config import ConfigError, load_note_tables


def write_json(path, data):
    path.write_text(json.dumps(data))
    return path


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


def test_user_file_keys_win_over_defaults(temp_defaults_dir, tmp_path, monkeypatch):
    """User file values win over defaults for the same key."""
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    conversion_file = write_json(tmp_path / "conv.json", {"38": 99})
    tables = load_note_tables(note_conversion_path=conversion_file)
    assert tables.note_conversion[38] == 99  # User wins, not default


def test_invalid_json_reports_error(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json")

    with pytest.raises(ConfigError) as exc_info:
        load_note_tables(note_conversion_path=bad_file)

    assert any("invalid JSON" in e for e in exc_info.value.errors)


def test_missing_file_reports_error(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables(note_conversion_path=missing)
    assert any("file not found" in e for e in exc_info.value.errors)


def test_non_object_json_reports_error(tmp_path):
    bad_file = write_json(tmp_path / "bad.json", [1, 2, 3])
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables(note_conversion_path=bad_file)
    assert any("expected a JSON object" in e for e in exc_info.value.errors)


def test_non_integer_key_reports_error(tmp_path):
    bad_file = write_json(tmp_path / "bad.json", {"kick": 40})
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables(note_conversion_path=bad_file)
    assert any("not an integer note number" in e for e in exc_info.value.errors)


def test_non_integer_value_reports_error(tmp_path):
    bad_file = write_json(tmp_path / "bad.json", {"38": "forty"})
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables(note_conversion_path=bad_file)
    assert any("must be an integer" in e for e in exc_info.value.errors)


def test_out_of_range_key_reports_error(tmp_path):
    bad_file = write_json(tmp_path / "bad.json", {"200": 40})
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables(note_conversion_path=bad_file)
    assert any("out of MIDI note range" in e for e in exc_info.value.errors)


def test_out_of_range_value_reports_error(tmp_path):
    bad_file = write_json(tmp_path / "bad.json", {"38": 200})
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables(note_conversion_path=bad_file)
    assert any("out of MIDI note range" in e for e in exc_info.value.errors)


def test_multiple_errors_reported_together(tmp_path):
    bad_file = write_json(
        tmp_path / "bad.json", {"kick": 40, "38": "forty", "200": 1, "1": 200}
    )
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables(note_conversion_path=bad_file)
    # All four distinct problems should be reported, not just the first.
    assert len(exc_info.value.errors) == 4


def test_boolean_value_rejected(tmp_path):
    # bool is a subclass of int in Python; make sure it's rejected explicitly.
    bad_file = write_json(tmp_path / "bad.json", {"38": True})
    with pytest.raises(ConfigError):
        load_note_tables(note_conversion_path=bad_file)


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
    # Check that at least the file-not-found errors are present
    file_not_found_errors = [e for e in exc_info.value.errors if "file not found" in e]
    assert len(file_not_found_errors) == 3
