"""Per-track MIDI note remapping and summary reporting."""

from __future__ import annotations

from dataclasses import dataclass, field

import mido

from .config import NoteTables

# Status buckets for the per-note summary.
CHANGED = "changed"
UNCHANGED = "unchanged"
UNMATCHED = "unmatched"

_NOTE_MESSAGE_TYPES = ("note_on", "note_off")


@dataclass
class RemapSummary:
    """Aggregated counts of how each source note number was handled.

    ``changed`` and ``unchanged`` are keyed by (original_note, final_note).
    ``unmatched`` is keyed by original_note only, since no conversion entry
    existed for it (mapping is not consulted in that case).
    """

    changed: dict[tuple[int, int], int] = field(default_factory=dict)
    unchanged: dict[tuple[int, int], int] = field(default_factory=dict)
    unmatched: dict[int, int] = field(default_factory=dict)
    note_types: dict[int, str] = field(default_factory=dict)

    def record(self, original: int, final: int, status: str) -> None:
        if status == UNMATCHED:
            self.unmatched[original] = self.unmatched.get(original, 0) + 1
        elif status == CHANGED:
            key = (original, final)
            self.changed[key] = self.changed.get(key, 0) + 1
        else:
            key = (original, final)
            self.unchanged[key] = self.unchanged.get(key, 0) + 1

    def total_changed(self) -> int:
        return sum(self.changed.values())

    def total_unchanged(self) -> int:
        return sum(self.unchanged.values())

    def total_unmatched(self) -> int:
        return sum(self.unmatched.values())

    def format_report(self) -> str:
        def label(note: int) -> str:
            name = self.note_types.get(note)
            return f"{note} ({name})" if name else str(note)

        lines: list[str] = []
        lines.append(
            f"Summary: {self.total_changed()} changed, "
            f"{self.total_unchanged()} unchanged, "
            f"{self.total_unmatched()} unmatched"
        )

        if self.changed:
            lines.append("Changed (original -> final: count):")
            for (original, final), count in sorted(self.changed.items()):
                lines.append(f"  {label(original)} -> {label(final)}: {count}")

        if self.unchanged:
            lines.append("Unchanged (note: count):")
            for (original, final), count in sorted(self.unchanged.items()):
                lines.append(f"  {label(original)}: {count}")

        if self.unmatched:
            lines.append("Unmatched (no conversion entry) (note: count):")
            for original, count in sorted(self.unmatched.items()):
                lines.append(f"  {label(original)}: {count}")

        return "\n".join(lines)


def resolve_note(original: int, tables: NoteTables) -> tuple[int, str]:
    """Resolve a single note number through conversion then mapping.

    Returns (final_note, status). Rules (per approved design):
    - No conversion entry for ``original`` -> note stays unchanged,
      status is UNMATCHED (mapping is not consulted).
    - Conversion entry exists -> apply it, then look up the converted
      value in the mapping table; if no mapping entry exists, keep the
      converted value as-is. Status is CHANGED if the final value differs
      from the original, else UNCHANGED.
    """
    if original not in tables.note_conversion and original not in tables.note_mapping:
        return original, UNMATCHED

    converted = tables.note_conversion.get(original, original)
    final = tables.note_mapping.get(converted, converted)
    status = CHANGED if final != original else UNCHANGED
    return final, status


def remap_midi_file(input_path: str, output_path: str, tables: NoteTables) -> RemapSummary:
    """Read a MIDI file, remap note numbers per track, write the result.

    All non-note events (timing/delta times, channel, velocity, control
    changes, program changes, meta/sysex messages, etc.) are preserved
    exactly. Each track is processed independently.
    """
    midi_file = mido.MidiFile(input_path)
    summary = RemapSummary(note_types=tables.note_types)

    for track in midi_file.tracks:
        for msg in track:
            if msg.type in _NOTE_MESSAGE_TYPES and hasattr(msg, "note"):
                final_note, status = resolve_note(msg.note, tables)
                summary.record(msg.note, final_note, status)
                msg.note = final_note

    midi_file.save(output_path)
    return summary
