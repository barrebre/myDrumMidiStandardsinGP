"""Tests for gp_midi_remap.transform: note resolution, per-track remap, summary."""

import mido

from gp_midi_remap.config import NoteTables
from gp_midi_remap.transform import (
    CHANGED,
    UNCHANGED,
    UNMATCHED,
    RemapSummary,
    remap_midi_file,
    resolve_note,
)


def test_resolve_note_no_conversion_entry_is_unmatched():
    tables = NoteTables(note_conversion={}, note_mapping={})
    final, status = resolve_note(38, tables)
    assert final == 38
    assert status == UNMATCHED


def test_resolve_note_in_mapping_without_conversion_is_unchanged():
    tables = NoteTables(note_conversion={}, note_mapping={38: 38})
    final, status = resolve_note(38, tables)
    assert (final, status) == (38, UNCHANGED)


def test_resolve_note_conversion_only():
    tables = NoteTables(note_conversion={38: 40}, note_mapping={})
    final, status = resolve_note(38, tables)
    assert final == 40
    assert status == CHANGED


def test_resolve_note_conversion_then_mapping():
    tables = NoteTables(note_conversion={38: 40}, note_mapping={40: 41})
    final, status = resolve_note(38, tables)
    assert final == 41
    assert status == CHANGED


def test_resolve_note_conversion_results_in_same_note_is_unchanged():
    tables = NoteTables(note_conversion={38: 38}, note_mapping={})
    final, status = resolve_note(38, tables)
    assert final == 38
    assert status == UNCHANGED


def test_resolve_note_mapping_reverts_to_original_is_unchanged():
    tables = NoteTables(note_conversion={38: 40}, note_mapping={40: 38})
    final, status = resolve_note(38, tables)
    assert final == 38
    assert status == UNCHANGED


def test_summary_report_counts():
    summary = RemapSummary()
    summary.record(38, 40, CHANGED)
    summary.record(38, 40, CHANGED)
    summary.record(36, 36, UNCHANGED)
    summary.record(51, 51, UNMATCHED)

    assert summary.total_changed() == 2
    assert summary.total_unchanged() == 1
    assert summary.total_unmatched() == 1
    report = summary.format_report()
    assert "2 changed, 1 unchanged, 1 unmatched" in report
    assert "38 -> 40: 2" in report


def test_summary_report_includes_note_names():
    summary = RemapSummary(note_types={38: "snare", 40: "tom"})
    summary.record(38, 40, CHANGED)
    assert "38 (snare) -> 40 (tom): 1" in summary.format_report()


def build_multi_track_midi(path):
    midi_file = mido.MidiFile(type=1)

    track1 = mido.MidiTrack()
    track1.append(mido.MetaMessage("track_name", name="Drums A", time=0))
    track1.append(mido.Message("note_on", channel=9, note=38, velocity=100, time=0))
    track1.append(mido.Message("note_off", channel=9, note=38, velocity=0, time=20))
    track1.append(mido.Message("control_change", channel=9, control=7, value=100, time=0))
    midi_file.tracks.append(track1)

    track2 = mido.MidiTrack()
    track2.append(mido.MetaMessage("track_name", name="Drums B", time=0))
    track2.append(mido.Message("note_on", channel=9, note=38, velocity=90, time=5))
    track2.append(mido.Message("note_off", channel=9, note=38, velocity=0, time=15))
    midi_file.tracks.append(track2)

    midi_file.save(path)
    return midi_file


def test_remap_preserves_track_structure_and_non_note_data(tmp_path):
    input_path = tmp_path / "in.mid"
    output_path = tmp_path / "out.mid"
    build_multi_track_midi(input_path)

    tables = NoteTables(note_conversion={38: 40}, note_mapping={})
    summary = remap_midi_file(str(input_path), str(output_path), tables)

    result = mido.MidiFile(str(output_path))
    assert len(result.tracks) == 2

    # Track 1: note remapped, non-note messages (meta, control_change) intact.
    # mido appends an end_of_track meta message automatically when saving.
    t1_types = [m.type for m in result.tracks[0]]
    assert t1_types == [
        "track_name",
        "note_on",
        "note_off",
        "control_change",
        "end_of_track",
    ]
    assert result.tracks[0][1].note == 40
    assert result.tracks[0][1].channel == 9
    assert result.tracks[0][1].velocity == 100
    assert result.tracks[0][1].time == 0
    assert result.tracks[0][2].time == 20
    assert result.tracks[0][3].control == 7

    # Track 2: independently remapped, timing preserved.
    assert result.tracks[1][1].note == 40
    assert result.tracks[1][1].time == 5
    assert result.tracks[1][2].time == 15

    # note_on + note_off remapped in each of the 2 tracks.
    assert summary.total_changed() == 4


def test_remap_leaves_notes_unchanged_when_no_config(tmp_path):
    input_path = tmp_path / "in.mid"
    output_path = tmp_path / "out.mid"
    build_multi_track_midi(input_path)

    tables = NoteTables(note_conversion={}, note_mapping={})
    summary = remap_midi_file(str(input_path), str(output_path), tables)

    result = mido.MidiFile(str(output_path))
    notes = [m.note for m in result.tracks[0] if m.type == "note_on"]
    assert notes == [38]
    # note_on + note_off for track 1's note, plus track 2's note_on + note_off.
    assert summary.total_unmatched() == 4
