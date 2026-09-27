# Note Filter Design

Keep only selected MIDI note numbers and drop the rest.

## Motivation

A drum MIDI file often carries the full kit, but a user may want a single
voice — for example, only the bass drum (notes 35 and 36) — so the Guitar Pro
import contains nothing else. Today every note survives; the tool can only
rewrite note numbers, not remove notes.

## Scope

- Add an opt-in `--note-filter` CLI option pointing at a user JSON file.
- Drop every `note_on`/`note_off` whose **original** note number is not listed.
- Report dropped notes in the summary.

Not in scope: a built-in default filter file, named presets (e.g. "bass"),
filtering by track or channel, or filtering on post-mapping note numbers.

## File Format

```json
{
  "keepNotes": [35, 36]
}
```

`keepNotes` is required and must be a non-empty array of integers in the MIDI
range 0–127. An empty array is a config error because it would delete every
note in the file. Duplicate entries are allowed and collapse into a set.

## CLI

New option:

```
--note-filter PATH   Path to a user JSON file listing the note numbers to
                     keep. Every other note is dropped. When omitted, no
                     filtering is performed.
```

Omitting the flag preserves current behavior exactly. The filter file is
user-supplied only — it is never merged with a built-in default, unlike
`--note-conversion` and `--note-mapping`.

## Config Layer

`NoteTables` gains `keep_notes: set[int] | None`. `None` means "no filtering".

`_validate_note_filter(data, source, errors)` validates the structure and
appends to the shared `errors` list, so filter problems are reported together
with conversion and mapping problems in a single `ConfigError`.

Validation errors:

| Condition | Message |
|---|---|
| Top level is not an object with `keepNotes` | `expected an object with a keepNotes array` |
| `keepNotes` is not a list | `keepNotes: expected an array` |
| `keepNotes` is empty | `keepNotes: must list at least one note number` |
| Entry is not an integer | `keepNotes: entry <x> is not an integer note number` |
| Entry out of 0–127 | `keepNotes: note <n> is out of MIDI note range (0-127)` |

`load_note_tables` takes a new `note_filter_path: Path | None = None`
parameter and reads the file with the existing `_read_json_file` helper.

## Transform Layer

Filtering is applied per track, before conversion and mapping, and matches the
note number as it appears in the input file.

For each track, rebuild the message list:

- A `note_on`/`note_off` whose note is not in `keep_notes` is removed, and its
  delta time is added to the next surviving message. This keeps every
  remaining event at its original absolute position.
- All other messages — meta events, tempo, time signature, program change,
  control change, sysex — are always kept.
- Surviving note messages then pass through the existing `resolve_note`
  conversion/mapping path unchanged.

Tracks that end up with no note messages are still written out, preserving the
file's track structure.

## Summary Reporting

`RemapSummary` gains `dropped: dict[int, int]`, keyed by original note number.
A drop is counted only for `note_on` messages with velocity greater than zero,
matching how changed/unchanged/unmatched notes are already counted, so a held
note is not double counted.

The header line becomes:

```
Summary: 12 changed, 3 unchanged, 0 unmatched, 47 dropped
```

The `dropped` count is omitted from the header when nothing was dropped, so
existing output is unchanged when the feature is unused. When notes were
dropped, a section is appended:

```
Dropped (filtered out) (note: count):
  38 (Snare): 24
  42 (Hi-Hat Closed): 23
```

Note names come from the existing `note_types` table, using the same `label`
helper as the other sections.

## Testing

**Config** — valid filter file; missing `keepNotes`; empty `keepNotes`;
non-integer entry; out-of-range note; filter errors aggregated with
conversion/mapping errors.

**Transform** — filtered notes removed from output; surviving notes keep their
original absolute timing when preceding notes are dropped; meta and non-note
events preserved; dropped counts recorded per note; no filtering when
`keep_notes` is `None`; note_off for a dropped note is removed too.

**CLI** — end-to-end run with `--note-filter` produces a file containing only
the kept notes and prints the dropped section; invalid filter file exits with
the config error code.

## Documentation

README gains a "Filtering notes" section describing the flag, the file format,
and the bass-drum-only example.
