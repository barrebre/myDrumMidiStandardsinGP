# Note Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users keep only selected MIDI note numbers (e.g. bass drum 35 and 36) and drop every other note, via an opt-in `--note-filter` JSON file.

**Architecture:** A new optional `keep_notes: set[int] | None` field on the existing `NoteTables` dataclass carries the filter. `config.py` validates and loads the user's filter file; `transform.py` rebuilds each MIDI track, removing non-kept note messages and rolling their delta times into the next surviving message so timing is preserved; `RemapSummary` gains a `dropped` counter and report section. `cli.py` exposes `--note-filter`.

**Tech Stack:** Python 3.9+, `mido` for MIDI I/O, `pytest` for tests.

**Spec:** `docs/superpowers/specs/2026-09-27-note-filter-design.md`

**Environment:** There is no `python` on PATH in this environment and no
interpreter-level `mido`/`pytest`. Task 0 creates a virtualenv at `.venv/`
(already in `.gitignore`). **Every command in this plan uses
`.venv/bin/python`** — do not substitute a bare `python`.

---

### Task 0: Set up the development environment

- [ ] **Step 1: Create the virtualenv and install dependencies**

```bash
python3 -m venv .venv
.venv/bin/pip install -e . -r requirements-dev.txt
```

- [ ] **Step 2: Establish the baseline test result**

Run: `.venv/bin/python -m pytest -q`

Expected: `37 passed`.

If instead you see `1 failed, 36 passed` with
`test_cli_end_to_end_default_output` asserting `"38 (snare) -> 40: 2"`, the
stale-assertion fix in Task 0a has not been applied — apply it before
continuing, so later tasks have a green baseline to compare against.

- [ ] **Step 3: Do not commit the virtualenv**

Run: `git status --short`

Expected: no output. `.venv/` is already listed in `.gitignore`.

---

### Task 0a: Fix the stale pre-existing test assertion

`tests/test_cli.py::test_cli_end_to_end_default_output` fails on `main` today.
Commit `9ce9f64 "Fix doubled note counts in remap summary"` changed the summary
to count each note once (on `note_on` with velocity > 0) rather than once per
`note_on`/`note_off` pair, but this test's assertions and comment were not
updated. It is unrelated to the note-filter feature, but a red baseline makes it
impossible to tell whether later tasks broke anything, so fix it first and commit
it separately.

**Files:**
- Modify: `tests/test_cli.py:58-63`

- [ ] **Step 1: Update the stale assertions**

In `tests/test_cli.py`, inside `test_cli_end_to_end_default_output`, replace:

```python
    # Both note_on and note_off carry the note number, so each source note
    # produces two remapped events.
    assert "38 (snare) -> 40: 2" in out
    assert "51 (ride): 2" in out
```

with:

```python
    # Each source note is counted once, on its note_on, not once per
    # note_on/note_off event pair.
    assert "38 (snare) -> 40: 1" in out
    assert "51 (ride): 1" in out
```

- [ ] **Step 2: Run the suite to verify it is green**

Run: `.venv/bin/python -m pytest -q`

Expected: `37 passed`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: correct stale note count assertions in CLI test"
```

---

### Task 1: Add `keep_notes` field to `NoteTables`

The `NoteTables` dataclass is constructed positionally in `config.load_note_tables`
(`NoteTables(conversion, mapping, note_types)`) and with keyword arguments throughout
`tests/test_transform.py`. Adding the new field last with a default of `None` keeps
both call styles working. `None` means "no filtering"; a set means "keep only these".

**Files:**
- Modify: `gp_midi_remap/config.py` (the `NoteTables` dataclass, around line 47)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_note_tables_keep_notes_defaults_to_none():
    from gp_midi_remap.config import NoteTables

    tables = NoteTables()
    assert tables.keep_notes is None


def test_note_tables_keep_notes_can_be_set():
    from gp_midi_remap.config import NoteTables

    tables = NoteTables(keep_notes={35, 36})
    assert tables.keep_notes == {35, 36}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_note_tables_keep_notes_defaults_to_none -v`

Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument` on the
second test, and `AttributeError: 'NoteTables' object has no attribute 'keep_notes'`
on the first.

- [ ] **Step 3: Write minimal implementation**

In `gp_midi_remap/config.py`, replace the `NoteTables` dataclass:

```python
@dataclass
class NoteTables:
    note_conversion: dict[int, int] = field(default_factory=dict)
    note_mapping: dict[int, int] = field(default_factory=dict)
    note_types: dict[int, str] = field(default_factory=dict)
    keep_notes: set[int] | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`

Expected: PASS, including all pre-existing config tests.

- [ ] **Step 5: Commit**

```bash
git add gp_midi_remap/config.py tests/test_config.py
git commit -m "feat: add keep_notes field to NoteTables"
```

---

### Task 2: Validate the note filter file

`_validate_note_filter` follows the same shape as the existing `_validate_note_types`:
it takes the parsed JSON, a `source` string used in error messages, and the shared
`errors` list, and returns the parsed result. It never raises — callers aggregate
errors and raise a single `ConfigError`.

An empty `keepNotes` array is rejected because keeping nothing would silently delete
every note in the file.

**Files:**
- Modify: `gp_midi_remap/config.py` (add function after `_validate_note_types`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_validate_note_filter_accepts_valid_file():
    from gp_midi_remap.config import _validate_note_filter

    errors = []
    result = _validate_note_filter({"keepNotes": [35, 36]}, "filter.json", errors)
    assert result == {35, 36}
    assert errors == []


def test_validate_note_filter_deduplicates():
    from gp_midi_remap.config import _validate_note_filter

    errors = []
    result = _validate_note_filter({"keepNotes": [36, 36, 35]}, "filter.json", errors)
    assert result == {35, 36}
    assert errors == []


def test_validate_note_filter_requires_keep_notes_key():
    from gp_midi_remap.config import _validate_note_filter

    errors = []
    result = _validate_note_filter({"notes": [35]}, "filter.json", errors)
    assert result == set()
    assert any("keepNotes array" in e for e in errors)


def test_validate_note_filter_rejects_non_list():
    from gp_midi_remap.config import _validate_note_filter

    errors = []
    result = _validate_note_filter({"keepNotes": 35}, "filter.json", errors)
    assert result == set()
    assert any("expected an array" in e for e in errors)


def test_validate_note_filter_rejects_empty_list():
    from gp_midi_remap.config import _validate_note_filter

    errors = []
    result = _validate_note_filter({"keepNotes": []}, "filter.json", errors)
    assert result == set()
    assert any("at least one note number" in e for e in errors)


def test_validate_note_filter_rejects_non_integer_entry():
    from gp_midi_remap.config import _validate_note_filter

    errors = []
    result = _validate_note_filter({"keepNotes": [35, "snare"]}, "filter.json", errors)
    assert result == {35}
    assert any("not an integer note number" in e for e in errors)


def test_validate_note_filter_rejects_boolean_entry():
    from gp_midi_remap.config import _validate_note_filter

    errors = []
    result = _validate_note_filter({"keepNotes": [True]}, "filter.json", errors)
    assert result == set()
    assert any("not an integer note number" in e for e in errors)


def test_validate_note_filter_rejects_out_of_range():
    from gp_midi_remap.config import _validate_note_filter

    errors = []
    result = _validate_note_filter({"keepNotes": [35, 200]}, "filter.json", errors)
    assert result == {35}
    assert any("out of MIDI note range" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -k note_filter -v`

Expected: FAIL with `ImportError: cannot import name '_validate_note_filter'`.

- [ ] **Step 3: Write minimal implementation**

In `gp_midi_remap/config.py`, add after `_validate_note_types`:

```python
def _validate_note_filter(data: object, source: str, errors: list[str]) -> set[int]:
    """Validate a user note-filter file into a set of note numbers to keep.

    Expected shape: ``{"keepNotes": [35, 36]}``. An empty list is rejected
    because keeping no notes would delete every note in the file.
    """
    if not isinstance(data, dict) or "keepNotes" not in data:
        errors.append(f"{source}: expected an object with a keepNotes array")
        return set()
    entries = data["keepNotes"]
    if not isinstance(entries, list):
        errors.append(f"{source}.keepNotes: expected an array")
        return set()
    if not entries:
        errors.append(f"{source}.keepNotes: must list at least one note number")
        return set()
    result: set[int] = set()
    for entry in entries:
        if not isinstance(entry, int) or isinstance(entry, bool):
            errors.append(f"{source}.keepNotes: entry {entry!r} is not an integer note number")
            continue
        if not MIDI_NOTE_MIN <= entry <= MIDI_NOTE_MAX:
            errors.append(f"{source}.keepNotes: note {entry} is out of MIDI note range (0-127)")
            continue
        result.add(entry)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gp_midi_remap/config.py tests/test_config.py
git commit -m "feat: validate note filter file format"
```

---

### Task 3: Load the filter file in `load_note_tables`

`load_note_tables` gains a third optional path parameter. The filter is user-supplied
only — no default file is read, so when the path is `None` the resulting `keep_notes`
stays `None` and behavior is unchanged. Filter errors join the same aggregated
`ConfigError` as conversion and mapping errors.

**Files:**
- Modify: `gp_midi_remap/config.py` (the `load_note_tables` function at the end of the file)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_load_note_tables_without_filter_leaves_keep_notes_none(
    temp_defaults_dir, monkeypatch
):
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    tables = load_note_tables()
    assert tables.keep_notes is None


def test_load_note_tables_with_filter(temp_defaults_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    filter_path = write_json(tmp_path / "filter.json", {"keepNotes": [35, 36]})
    tables = load_note_tables(note_filter_path=filter_path)
    assert tables.keep_notes == {35, 36}


def test_load_note_tables_filter_missing_file_raises(
    temp_defaults_dir, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables(note_filter_path=tmp_path / "nope.json")
    assert any("file not found" in e for e in exc_info.value.errors)


def test_load_note_tables_filter_errors_aggregate_with_conversion_errors(
    temp_defaults_dir, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "gp_midi_remap.config._resolve_defaults_dir",
        lambda: temp_defaults_dir,
    )
    bad_conv = write_json(tmp_path / "conv.json", {"38": "forty"})
    bad_filter = write_json(tmp_path / "filter.json", {"keepNotes": []})
    with pytest.raises(ConfigError) as exc_info:
        load_note_tables(note_conversion_path=bad_conv, note_filter_path=bad_filter)
    errors = exc_info.value.errors
    assert any("must be an integer" in e for e in errors)
    assert any("at least one note number" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -k "load_note_tables_with_filter or load_note_tables_without_filter or filter_missing_file or filter_errors_aggregate" -v`

Expected: FAIL with `TypeError: load_note_tables() got an unexpected keyword argument 'note_filter_path'`.

- [ ] **Step 3: Write minimal implementation**

In `gp_midi_remap/config.py`, change the `load_note_tables` signature:

```python
def load_note_tables(
    note_conversion_path: Path | None = None,
    note_mapping_path: Path | None = None,
    note_filter_path: Path | None = None,
) -> NoteTables:
```

Then, immediately before the `if errors:` block at the end of the function, add:

```python
    keep_notes: set[int] | None = None
    if note_filter_path is not None:
        raw = _read_json_file(note_filter_path, errors)
        if raw is not None:
            keep_notes = _validate_note_filter(raw, str(note_filter_path), errors)
```

And change the final return statement from
`return NoteTables(conversion, mapping, note_types)` to:

```python
    return NoteTables(conversion, mapping, note_types, keep_notes)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gp_midi_remap/config.py tests/test_config.py
git commit -m "feat: load note filter file in load_note_tables"
```

---

### Task 4: Track dropped notes in `RemapSummary`

`RemapSummary.record` handles the changed/unchanged/unmatched buckets. Dropped notes
never reach `record` (they are removed before resolution), so they get a dedicated
`record_dropped` method. The header line only mentions drops when there are any, so
existing output is byte-identical when the feature is unused.

**Files:**
- Modify: `gp_midi_remap/transform.py` (the `RemapSummary` dataclass, lines 20-79)
- Test: `tests/test_transform.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_transform.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_transform.py -k dropped -v`

Expected: FAIL with `AttributeError: 'RemapSummary' object has no attribute 'dropped'`.

- [ ] **Step 3: Write minimal implementation**

In `gp_midi_remap/transform.py`, add a field to `RemapSummary` after `unmatched`:

```python
    dropped: dict[int, int] = field(default_factory=dict)
```

Add a method after `record`:

```python
    def record_dropped(self, original: int) -> None:
        self.dropped[original] = self.dropped.get(original, 0) + 1
```

Add a total after `total_unmatched`:

```python
    def total_dropped(self) -> int:
        return sum(self.dropped.values())
```

In `format_report`, replace the header block:

```python
        header = (
            f"Summary: {self.total_changed()} changed, "
            f"{self.total_unchanged()} unchanged, "
            f"{self.total_unmatched()} unmatched"
        )
        if self.dropped:
            header += f", {self.total_dropped()} dropped"
        lines.append(header)
```

And append a new section after the existing `if self.unmatched:` block, before the
final `return`:

```python
        if self.dropped:
            lines.append("Dropped (filtered out) (note: count):")
            for original, count in sorted(self.dropped.items()):
                lines.append(f"  {label(original)}: {count}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_transform.py -v`

Expected: PASS, including pre-existing summary tests.

- [ ] **Step 5: Commit**

```bash
git add gp_midi_remap/transform.py tests/test_transform.py
git commit -m "feat: report dropped notes in remap summary"
```

---

### Task 5: Filter notes out of tracks during remap

This is the core behavior. MIDI messages carry a delta time — the number of ticks
since the previous message in the track. Removing a message therefore shifts every
later message earlier unless its delta time is carried forward. The implementation
accumulates the delta time of each dropped message and adds it to the next message
that survives, so all surviving events land at their original absolute tick.

Filtering matches the note number **as it appears in the input file**, before
conversion and mapping. Only `note_on` and `note_off` messages are ever dropped;
meta events, tempo, time signature, program change, control change, and sysex are
always preserved. A dropped note is counted only on `note_on` with velocity above
zero, matching how the other buckets are counted, so a held note is not counted twice.

**Files:**
- Modify: `gp_midi_remap/transform.py` (the `remap_midi_file` function at the end of the file)
- Test: `tests/test_transform.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_transform.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_transform.py -k "with_filter" -v`

Expected: FAIL — the filter tests fail because notes are not dropped (e.g.
`assert [36, 38, 42] == [36]`). The `test_remap_without_filter_keeps_all_notes`
test should already pass.

- [ ] **Step 3: Write minimal implementation**

In `gp_midi_remap/transform.py`, replace the body of `remap_midi_file` with:

```python
def remap_midi_file(input_path: str, output_path: str, tables: NoteTables) -> RemapSummary:
    """Read a MIDI file, remap note numbers per track, write the result.

    All non-note events (timing/delta times, channel, velocity, control
    changes, program changes, meta/sysex messages, etc.) are preserved
    exactly. Each track is processed independently. Only note starts are
    counted in the summary so a held note is not reported twice as both a
    note_on and note_off event.

    When ``tables.keep_notes`` is set, note messages whose original note
    number is not listed are removed. A removed message's delta time is
    carried forward onto the next surviving message so every remaining
    event stays at its original absolute position.
    """
    midi_file = mido.MidiFile(input_path)
    summary = RemapSummary(note_types=tables.note_types)
    keep_notes = tables.keep_notes

    for track in midi_file.tracks:
        kept = []
        carried_time = 0
        for msg in track:
            is_note = msg.type in _NOTE_MESSAGE_TYPES and hasattr(msg, "note")
            if is_note and keep_notes is not None and msg.note not in keep_notes:
                if msg.type == "note_on" and getattr(msg, "velocity", 0) > 0:
                    summary.record_dropped(msg.note)
                carried_time += msg.time
                continue
            if carried_time:
                msg.time += carried_time
                carried_time = 0
            if is_note:
                original_note = msg.note
                final_note, status = resolve_note(original_note, tables)
                if msg.type == "note_on" and getattr(msg, "velocity", 0) > 0:
                    summary.record(original_note, final_note, status)
                msg.note = final_note
            kept.append(msg)
        track[:] = kept

    midi_file.save(output_path)
    return summary
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_transform.py -v`

Expected: PASS, including all pre-existing transform tests.

- [ ] **Step 5: Run the full suite to check nothing regressed**

Run: `.venv/bin/python -m pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gp_midi_remap/transform.py tests/test_transform.py
git commit -m "feat: drop filtered-out notes while preserving timing"
```

---

### Task 6: Expose `--note-filter` on the CLI

**Files:**
- Modify: `gp_midi_remap/cli.py` (`build_parser` and the `load_note_tables` call in `main`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_cli_with_note_filter_keeps_only_listed_notes(tmp_path, capsys):
    input_path = tmp_path / "song.mid"
    make_test_midi(input_path, [36, 38, 35, 51])

    note_filter = tmp_path / "filter.json"
    note_filter.write_text(json.dumps({"keepNotes": [35, 36]}))

    exit_code = main([str(input_path), "--note-filter", str(note_filter)])

    assert exit_code == 0
    output_path = tmp_path / "song_converted.mid"
    result_midi = mido.MidiFile(str(output_path))
    notes = [m.note for m in result_midi.tracks[0] if m.type == "note_on"]
    assert notes == [36, 35]

    out = capsys.readouterr().out
    assert "dropped" in out
    assert "Dropped (filtered out) (note: count):" in out


def test_cli_without_note_filter_reports_no_drops(tmp_path, capsys):
    input_path = tmp_path / "song.mid"
    make_test_midi(input_path, [36, 38])

    exit_code = main([str(input_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dropped" not in out


def test_cli_invalid_note_filter_exit_code(tmp_path):
    input_path = tmp_path / "song.mid"
    make_test_midi(input_path, [36])
    bad_filter = tmp_path / "filter.json"
    bad_filter.write_text(json.dumps({"keepNotes": []}))

    exit_code = main([str(input_path), "--note-filter", str(bad_filter)])
    assert exit_code == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k note_filter -v`

Expected: FAIL with `SystemExit: 2` from argparse — `unrecognized arguments: --note-filter`.

- [ ] **Step 3: Write minimal implementation**

In `gp_midi_remap/cli.py`, add to `build_parser` after the `--note-mapping` argument:

```python
    parser.add_argument(
        "--note-filter",
        type=Path,
        default=None,
        help=(
            "Path to a user JSON file listing the note numbers to keep, in "
            "the form {\"keepNotes\": [35, 36]}. Every other note is removed "
            "from the output. Matched against the note numbers in the input "
            "file, before conversion and mapping. When omitted, no notes "
            "are filtered out."
        ),
    )
```

In `main`, change the `load_note_tables` call to:

```python
        tables = load_note_tables(
            note_conversion_path=args.note_conversion,
            note_mapping_path=args.note_mapping,
            note_filter_path=args.note_filter,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`

Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gp_midi_remap/cli.py tests/test_cli.py
git commit -m "feat: add --note-filter CLI option"
```

---

### Task 7: Document the feature in the README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the documentation section**

In `README.md`, add a new section after the "How it works" section and before
"## Install":

~~~markdown
## Keeping only certain notes

By default every note in the file is written to the output. To keep only
specific notes and drop the rest, pass a filter file with `--note-filter`:

```json
{
  "keepNotes": [35, 36]
}
```

```bash
gp-midi-remap song.mid --note-filter bassDrumOnly.json
```

This keeps only the bass drum notes (35 and 36) and removes every other note
from the output. Timing is preserved — the notes that remain stay exactly
where they were.

Notes are matched against the numbers as they appear in the **input** file,
before any conversion or mapping is applied. Kept notes still go through the
normal conversion and mapping tables. Non-note events such as tempo, time
signature, and track names are never removed, and the file's track structure
is preserved even if a track ends up with no notes.

`keepNotes` must list at least one note number, each in the MIDI range 0-127.
There is no built-in default filter — when `--note-filter` is omitted, no
notes are dropped.

Dropped notes appear in the summary report:

```
Summary: 0 changed, 2 unchanged, 0 unmatched, 47 dropped
Dropped (filtered out) (note: count):
  38 (snare): 24
  42 (closed hi-hat): 23
```
~~~

- [ ] **Step 2: Verify the rendered file reads correctly**

Run: `sed -n '1,80p' README.md`

Expected: the new section appears between "How it works" and "## Install",
with correctly balanced code fences.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document --note-filter option"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest -v`

Expected: all tests PASS, no errors or warnings introduced by this work.

- [ ] **Step 2: Manual end-to-end check**

```bash
.venv/bin/python - <<'PY'
import mido
f = mido.MidiFile()
t = mido.MidiTrack()
f.tracks.append(t)
for note in (36, 38, 42, 35, 38):
    t.append(mido.Message("note_on", note=note, velocity=64, time=0))
    t.append(mido.Message("note_off", note=note, velocity=0, time=120))
f.save("/tmp/gpfilter_demo.mid")
PY
echo '{"keepNotes": [35, 36]}' > /tmp/gpfilter_bass.json
.venv/bin/python -m gp_midi_remap /tmp/gpfilter_demo.mid -o /tmp/gpfilter_out.mid --force --note-filter /tmp/gpfilter_bass.json
.venv/bin/python -c "import mido; print([m.note for m in mido.MidiFile('/tmp/gpfilter_out.mid').tracks[0] if m.type=='note_on'])"
```

Expected: the summary reports 3 dropped notes (38 twice, 42 once), and the final
line prints `[36, 35]`.

- [ ] **Step 2b: Verify unfiltered behavior is unchanged**

```bash
.venv/bin/python -m gp_midi_remap /tmp/gpfilter_demo.mid -o /tmp/gpfilter_all.mid --force
.venv/bin/python -c "import mido; print([m.note for m in mido.MidiFile('/tmp/gpfilter_all.mid').tracks[0] if m.type=='note_on'])"
```

Expected: all five notes present, and the summary line contains no "dropped".

- [ ] **Step 3: Clean up temporary files**

```bash
rm -f /tmp/gpfilter_demo.mid /tmp/gpfilter_out.mid /tmp/gpfilter_all.mid /tmp/gpfilter_bass.json
```

- [ ] **Step 4: Confirm the working tree is clean**

Run: `git status --short`

Expected: no output — everything committed.
