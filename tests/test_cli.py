"""Tests for CLI helpers: default output filename derivation and end-to-end flow."""

import json
import subprocess
import sys
from pathlib import Path

import mido
import pytest

from gp_midi_remap.cli import default_output_path, main


def test_default_output_path_with_extension():
    assert default_output_path(Path("song.mid")) == Path("song_converted.mid")


def test_default_output_path_with_nested_dirs():
    assert default_output_path(Path("/a/b/song.mid")) == Path(
        "/a/b/song_converted.mid"
    )


def test_default_output_path_no_extension():
    assert default_output_path(Path("song")) == Path("song_converted")


def test_default_output_path_multiple_dots():
    assert default_output_path(Path("song.v1.mid")) == Path(
        "song.v1_converted.mid"
    )


def make_test_midi(path, notes):
    midi_file = mido.MidiFile()
    track = mido.MidiTrack()
    midi_file.tracks.append(track)
    for note in notes:
        track.append(mido.Message("note_on", note=note, velocity=64, time=0))
        track.append(mido.Message("note_off", note=note, velocity=0, time=10))
    midi_file.save(path)


def test_cli_end_to_end_default_output(tmp_path, capsys):
    input_path = tmp_path / "song.mid"
    make_test_midi(input_path, [38, 51])

    conv = tmp_path / "conv.json"
    conv.write_text(json.dumps({"38": 40}))

    exit_code = main([str(input_path), "--note-conversion", str(conv)])

    assert exit_code == 0
    output_path = tmp_path / "song_converted.mid"
    assert output_path.exists()

    out = capsys.readouterr().out
    assert "song_converted.mid" in out
    # Both note_on and note_off carry the note number, so each source note
    # produces two remapped events.
    assert "38 (snare) -> 40: 2" in out
    assert "51 (ride): 2" in out

    result_midi = mido.MidiFile(str(output_path))
    notes = [m.note for m in result_midi.tracks[0] if m.type == "note_on"]
    assert notes == [40, 51]


def test_cli_refuses_overwrite_without_force(tmp_path):
    input_path = tmp_path / "song.mid"
    make_test_midi(input_path, [36])
    output_path = tmp_path / "song_converted.mid"
    output_path.write_text("existing")

    exit_code = main([str(input_path)])
    assert exit_code == 3
    assert output_path.read_text() == "existing"


def test_cli_force_overwrites(tmp_path):
    input_path = tmp_path / "song.mid"
    make_test_midi(input_path, [36])
    output_path = tmp_path / "song_converted.mid"
    output_path.write_text("existing")

    exit_code = main([str(input_path), "--force"])
    assert exit_code == 0
    assert mido.MidiFile(str(output_path))


def test_cli_missing_input_file(tmp_path):
    exit_code = main([str(tmp_path / "missing.mid")])
    assert exit_code == 3


def test_cli_config_error_exit_code(tmp_path):
    input_path = tmp_path / "song.mid"
    make_test_midi(input_path, [36])
    bad_conv = tmp_path / "bad.json"
    bad_conv.write_text("not json")

    exit_code = main([str(input_path), "--note-conversion", str(bad_conv)])
    assert exit_code == 2
