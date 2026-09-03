"""gp_midi_remap: remap drum note numbers in MIDI files for Guitar Pro imports.

Loads note-conversion and note-mapping tables (with user-overridable JSON
files layered over built-in defaults), applies them per track to note_on /
note_off events, and reports a summary of changed / unchanged / unmatched
notes.
"""

__version__ = "0.1.0"
