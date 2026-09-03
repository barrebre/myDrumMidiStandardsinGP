# gp-midi-remap

Remap MIDI drum note numbers so imports land on the tracks/lines you expect
in Guitar Pro, using `mido`. Channels, tracks, timing, and velocity are left
untouched — only `note_on`/`note_off` note numbers are rewritten.

## How it works

Each note number is checked against the configured Guitar Pro lines and, when
present, goes through two lookup tables, applied in order:

1. **`defaultNoteConversion`** — converts an original note number to a
   replacement note number (e.g. GP renders note 38 somewhere you don't
   like, so it's converted to a different note first).
2. **`defaultNoteMapping`** — takes the (converted) note number and maps it
   to whatever note number actually lands on the expected line in Guitar
   Pro.

Notes listed in `defaultNoteMapping` are matched even when no conversion is
needed. Notes absent from both tables are left unchanged and counted as
**unmatched**. `defaultNoteTypes` supplies names in the summary when known.
The file's tracks are each processed independently, so multi-track MIDI files
keep their track structure intact.

Built-in defaults live in `gp_midi_remap/defaults/`. Conversion files use the
`notes` array format, mapping files use the `lines`/`noteNumbers` format, and
note types use the `notes` object format.
You can also supply your own override files on the command line; entries in
your file take precedence over the defaults, and any default entries your
file doesn't mention are still applied.

## Install

```bash
pip install -e .
# or, without installing:
pip install -r requirements.txt
```

## Usage

```bash
gp-midi-remap song.mid
# writes song_converted.mid next to song.mid

gp-midi-remap song.mid -o out.mid
gp-midi-remap song.mid --note-conversion my_conversion.json --note-mapping my_mapping.json
gp-midi-remap song.mid --force   # overwrite an existing output file
```

Without installing the package, you can also run it as a module:

```bash
python -m gp_midi_remap song.mid
```

### JSON override file format

Both `--note-conversion` and `--note-mapping` files use the same shape: a
JSON object whose keys and values are MIDI note numbers (0-127).

```json
{
  "38": 40,
  "42": 22
}
```

### Output

On success, the tool prints the output path and a summary:

```
Wrote song_converted.mid
Summary: 12 changed, 4 unchanged, 3 unmatched
Changed (original -> final: count):
  38 -> 40: 8
  42 -> 22: 4
Unchanged (note: count):
  36: 4
Unmatched (no conversion entry) (note: count):
  51: 3
```

### Exit codes

| Code | Meaning |
| ---- | ------- |
| 0    | Success |
| 2    | Config/argument validation error (bad JSON, out-of-range note, etc.) — all detected problems are reported together |
| 3    | Input/output/MIDI processing error (missing file, existing output without `--force`, unreadable MIDI, etc.) |

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```
