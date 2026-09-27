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


def test_summary_dropped_defaults_empty():
    summary = RemapSummary()
    assert summary.dropped == {}
    assert summary.total_dropped() == 0


def test_summary_record_dropped_counts_per_note():
    summary = RemapSummary()
    summary.record_dropped(38)
    summary.record_dropped(38)
    summary.record_dropped(42)
    assert summary.dropped == {38: 2, 42: 1}
    assert summary.total_dropped() == 3


def test_summary_report_omits_dropped_when_none():
    summary = RemapSummary()
    summary.record(38, 40, CHANGED)
    report = summary.format_report()
    assert "dropped" not in report
    assert report.splitlines()[0] == (
        "Summary: 1 changed, 0 unchanged, 0 unmatched"
    )


def test_summary_report_includes_dropped_section():
    summary = RemapSummary(note_types={38: "snare"})
    summary.record(36, 36, UNCHANGED)
    summary.record_dropped(38)
    summary.record_dropped(38)
    report = summary.format_report()
    assert report.splitlines()[0] == (
        "Summary: 0 changed, 1 unchanged, 0 unmatched, 2 dropped"
    )
    assert "Dropped (filtered out) (note: count):" in report
    assert "  38 (snare): 2" in report


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

    # Count note starts, not the paired note_off events; otherwise each note is
    # reported twice.
    assert summary.total_changed() == 2


def test_remap_leaves_notes_unchanged_when_no_config(tmp_path):
    input_path = tmp_path / "in.mid"
    output_path = tmp_path / "out.mid"
    build_multi_track_midi(input_path)

    tables = NoteTables(note_conversion={}, note_mapping={})
    summary = remap_midi_file(str(input_path), str(output_path), tables)

    result = mido.MidiFile(str(output_path))
    notes = [m.note for m in result.tracks[0] if m.type == "note_on"]
    assert notes == [38]
    # Count note starts once per note event, not both note_on and note_off.
    assert summary.total_unmatched() == 2


def write_midi(path, events):
    """Build a one-track MIDI file from (note, delta_ticks) pairs.

    Each pair produces a note_on at the given delta and a note_off 10 ticks later.
    """
    midi_file = mido.MidiFile()
    track = mido.MidiTrack()
    midi_file.tracks.append(track)
    for note, delta in events:
        track.append(mido.Message("note_on", note=note, velocity=64, time=delta))
        track.append(mido.Message("note_off", note=note, velocity=0, time=10))
    midi_file.save(str(path))
    return path


def test_remap_without_filter_keeps_all_notes(tmp_path):
    src = write_midi(tmp_path / "in.mid", [(36, 0), (38, 0), (42, 0)])
    out = tmp_path / "out.mid"
    tables = NoteTables(note_conversion={}, note_mapping={36: 36, 38: 38, 42: 42})

    summary = remap_midi_file(str(src), str(out), tables)

    notes = [m.note for m in mido.MidiFile(str(out)).tracks[0] if m.type == "note_on"]
    assert notes == [36, 38, 42]
    assert summary.total_dropped() == 0


def test_remap_with_filter_drops_unlisted_notes(tmp_path):
    src = write_midi(tmp_path / "in.mid", [(36, 0), (38, 0), (35, 0), (42, 0)])
    out = tmp_path / "out.mid"
    tables = NoteTables(
        note_conversion={}, note_mapping={36: 36, 35: 35}, keep_notes={35, 36}
    )

    summary = remap_midi_file(str(src), str(out), tables)

    result = mido.MidiFile(str(out)).tracks[0]
    notes = [m.note for m in result if m.type in ("note_on", "note_off")]
    assert notes == [36, 36, 35, 35]
    assert summary.dropped == {38: 1, 42: 1}


def test_remap_with_filter_preserves_timing_of_survivors(tmp_path):
    # Absolute note_on ticks: 36 at 0, 38 at 10 (0 + note_off 10),
    # 36 at 40 (10 + off 10 + 20). Dropping the 38 must leave the second
    # 36 at absolute tick 40.
    src = write_midi(tmp_path / "in.mid", [(36, 0), (38, 0), (36, 20)])
    out = tmp_path / "out.mid"
    tables = NoteTables(note_conversion={}, note_mapping={36: 36}, keep_notes={36})

    remap_midi_file(str(src), str(out), tables)

    absolute = 0
    on_ticks = []
    for msg in mido.MidiFile(str(out)).tracks[0]:
        absolute += msg.time
        if msg.type == "note_on":
            on_ticks.append(absolute)
    assert on_ticks == [0, 40]


def test_remap_with_filter_preserves_non_note_events(tmp_path):
    midi_file = mido.MidiFile()
    track = mido.MidiTrack()
    midi_file.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Drums", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    track.append(mido.Message("program_change", program=1, time=0))
    track.append(mido.Message("note_on", note=38, velocity=64, time=0))
    track.append(mido.Message("note_off", note=38, velocity=0, time=10))
    track.append(mido.Message("note_on", note=36, velocity=64, time=0))
    track.append(mido.Message("note_off", note=36, velocity=0, time=10))
    src = tmp_path / "in.mid"
    midi_file.save(str(src))
    out = tmp_path / "out.mid"
    tables = NoteTables(note_conversion={}, note_mapping={36: 36}, keep_notes={36})

    remap_midi_file(str(src), str(out), tables)

    types = [m.type for m in mido.MidiFile(str(out)).tracks[0]]
    assert "track_name" in types
    assert "set_tempo" in types
    assert "program_change" in types
    assert types.count("note_on") == 1


def test_remap_with_filter_applies_mapping_to_kept_notes(tmp_path):
    src = write_midi(tmp_path / "in.mid", [(50, 0), (38, 0)])
    out = tmp_path / "out.mid"
    tables = NoteTables(
        note_conversion={50: 97}, note_mapping={97: 97}, keep_notes={50}
    )

    summary = remap_midi_file(str(src), str(out), tables)

    notes = [m.note for m in mido.MidiFile(str(out)).tracks[0] if m.type == "note_on"]
    assert notes == [97]
    assert summary.total_changed() == 1
    assert summary.dropped == {38: 1}


def test_remap_with_filter_counts_each_note_once_not_per_event(tmp_path):
    src = write_midi(tmp_path / "in.mid", [(38, 0), (38, 0)])
    out = tmp_path / "out.mid"
    tables = NoteTables(note_conversion={}, note_mapping={36: 36}, keep_notes={36})

    summary = remap_midi_file(str(src), str(out), tables)

    # Two note_on events dropped, their note_off events dropped silently.
    assert summary.dropped == {38: 2}


def test_remap_with_filter_keeps_empty_track_structure(tmp_path):
    midi_file = mido.MidiFile()
    first = mido.MidiTrack()
    first.append(mido.Message("note_on", note=36, velocity=64, time=0))
    first.append(mido.Message("note_off", note=36, velocity=0, time=10))
    second = mido.MidiTrack()
    second.append(mido.Message("note_on", note=38, velocity=64, time=0))
    second.append(mido.Message("note_off", note=38, velocity=0, time=10))
    midi_file.tracks.append(first)
    midi_file.tracks.append(second)
    src = tmp_path / "in.mid"
    midi_file.save(str(src))
    out = tmp_path / "out.mid"
    tables = NoteTables(note_conversion={}, note_mapping={36: 36}, keep_notes={36})

    remap_midi_file(str(src), str(out), tables)

    result = mido.MidiFile(str(out))
    assert len(result.tracks) == 2
    assert [m.note for m in result.tracks[0] if m.type == "note_on"] == [36]
    assert [m for m in result.tracks[1] if m.type == "note_on"] == []
