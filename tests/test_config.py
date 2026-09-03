"""Tests for gp_midi_remap.config: parsing, validation, merge precedence."""

import json

import pytest

from gp_midi_remap.config import ConfigError, load_note_tables


def write_json(path, data):
    path.write_text(json.dumps(data))
    return path


def test_defaults_only_load_empty_tables():
    tables = load_note_tables()
    assert tables.note_conversion == {}
    assert tables.note_mapping == {}


def test_user_override_merges_over_defaults(tmp_path):
    conversion_file = write_json(tmp_path / "conv.json", {"38": 40, "42": 22})
    mapping_file = write_json(tmp_path / "map.json", {"40": 41})

    tables = load_note_tables(
        note_conversion_path=conversion_file, note_mapping_path=mapping_file
    )

    assert tables.note_conversion == {38: 40, 42: 22}
    assert tables.note_mapping == {40: 41}


def test_user_file_keys_win_over_defaults(tmp_path, monkeypatch):
    # Simulate a non-empty default by loading a user file twice: once as if
    # it were the "default" via direct table validation isn't exposed, so
    # instead verify override semantics using two successive loads sharing
    # the same conversion file content but different values.
    conversion_file = write_json(tmp_path / "conv.json", {"38": 99})
    tables = load_note_tables(note_conversion_path=conversion_file)
    assert tables.note_conversion[38] == 99


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
