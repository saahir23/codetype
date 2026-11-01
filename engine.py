"""Typing-session logic for codetype. No UI code lives here, so it can be tested on its own."""
import math
import time
from collections import Counter
from dataclasses import dataclass

from models import Section

# AUTO: indentation skipped for you. ASSIST: filled by the autocomplete button; it is
# tracked separately and never counts towards wpm or accuracy.
PENDING, CORRECT, WRONG, AUTO, ASSIST = "pending", "correct", "wrong", "auto", "assist"
TAB_WIDTH = 4
IDLE_CAP = 5.0  # seconds; longer pauses aren't charged to a block's time


@dataclass
class Results:
    wpm: float
    raw: float
    accuracy: float
    elapsed: float
    correct_chars: int
    wrong_chars: int
    keystrokes: int
    errors: int
    missed: Counter
    series: list          # (second, wpm, raw wpm, errors in that second)
    sections: list        # per-block stats dicts
    assist_uses: int      # autocomplete presses (separate from the typing stats)
    assist_chars: int     # characters filled by autocomplete


class TypingSession:
    """Tracks what the user has typed against the target code.

    Every accepted keystroke is stored as a "step" (the list of positions it
    filled), so backspace can undo an Enter together with its auto-indent.
    """

    def __init__(self, code: str, sections: list[Section], auto_indent: bool = True):
        self.target = code
        self.sections = sections
        self.auto_indent = auto_indent
        self.state = [PENDING] * len(code)
        self.pos = 0
        self.steps: list[list[int]] = []

        self.start_time = None
        self.end_time = None
        self.last_key_time = None
        self.keystrokes = 0
        self.correct_keystrokes = 0
        self.missed = Counter()  # expected character -> times it was mistyped
        self.events = []         # (seconds since start, was_correct)
        self.assist_uses = 0
        self.paused_at = None

        self.line_of_pos = []
        line = 1
        for ch in code:
            self.line_of_pos.append(line)
            if ch == "\n":
                line += 1
        self.line_count = line
        self.section_of_line = self._map_lines()
        self.section_end_pos = {}
        for p, ln in enumerate(self.line_of_pos):
            sec = self.section_of_line[ln]
            if sec is not None:
                self.section_end_pos[sec] = p

        n = len(sections)
        self.sec_time = [0.0] * n
        self.sec_keys = [0] * n
        self.sec_errors = [0] * n

        if auto_indent:
            self._skip_indent()

    # ---- mapping helpers -------------------------------------------------

    def _map_lines(self):
        """Map each line number to a section index; uncovered lines join the previous block."""
        mapping = [None] * (self.line_count + 1)
        for i, s in enumerate(self.sections):
            for ln in range(max(1, s.start_line), min(self.line_count, s.end_line) + 1):
                if mapping[ln] is None:
                    mapping[ln] = i
        first = next((m for m in mapping[1:] if m is not None), None)
        last = first
        for ln in range(1, self.line_count + 1):
            if mapping[ln] is None:
                mapping[ln] = last
            else:
                last = mapping[ln]
        return mapping

    def _clamped(self, pos=None):
        pos = self.pos if pos is None else pos
        return min(pos, len(self.target) - 1)

    def section_at(self, pos=None):
        if not self.target:
            return None
        return self.section_of_line[self.line_of_pos[self._clamped(pos)]]

    def current_line(self):
        return self.line_of_pos[self._clamped()] if self.target else 1

    def section_done(self, index):
        end = self.section_end_pos.get(index)
        return end is not None and (self.pos > end or self.finished)

    # ---- typing ----------------------------------------------------------

    @property
    def finished(self):
        return self.end_time is not None

    def _skip_indent(self):
        skipped = []
        while self.pos < len(self.target) and self.target[self.pos] == " ":
            self.state[self.pos] = AUTO
            skipped.append(self.pos)
            self.pos += 1
        return skipped

    def _record(self, ok):
        now = time.monotonic()
        if self.start_time is None:
            self.start_time = now
            self.last_key_time = now
        sec = self.section_at()
        if sec is not None:
            self.sec_time[sec] += min(now - self.last_key_time, IDLE_CAP)
            self.sec_keys[sec] += 1
            if not ok:
                self.sec_errors[sec] += 1
        self.last_key_time = now
        self.keystrokes += 1
        if ok:
            self.correct_keystrokes += 1
        self.events.append((now - self.start_time, ok))

    def _check_done(self):
        if self.pos >= len(self.target):
            self.end_time = time.monotonic()

    def type_char(self, ch):
        """Handle one typed character. Returns (changed positions, accepted)."""
        if self.finished or self.pos >= len(self.target):
            return [], False
        expected = self.target[self.pos]

        # Line breaks must match exactly: Enter mid-line, or a letter at the end of a
        # line, counts as a mistake but doesn't move the caret.
        if expected == "\n" or ch == "\n":
            if ch != expected:
                self._record(False)
                self.missed[expected] += 1
                return [], False
            self._record(True)
            step = [self.pos]
            self.state[self.pos] = CORRECT
            self.pos += 1
            if self.auto_indent:
                step += self._skip_indent()
            self.steps.append(step)
            self._check_done()
            return step, True

        ok = ch == expected
        self._record(ok)
        if not ok:
            self.missed[expected] += 1
        self.state[self.pos] = CORRECT if ok else WRONG
        step = [self.pos]
        self.pos += 1
        self.steps.append(step)
        self._check_done()
        return step, True

    def tab(self):
        """Tab fills spaces up to the next indent stop (handy with auto-indent off)."""
        if self.finished or self.pos >= len(self.target):
            return [], False
        if self.target[self.pos] != " ":
            return self.type_char("\t")
        col = self.pos - (self.target.rfind("\n", 0, self.pos) + 1)
        remaining = TAB_WIDTH - col % TAB_WIDTH
        self._record(True)
        step = []
        while remaining and self.pos < len(self.target) and self.target[self.pos] == " ":
            self.state[self.pos] = AUTO
            step.append(self.pos)
            self.pos += 1
            remaining -= 1
        self.steps.append(step)
        self._check_done()
        return step, True

    def autocomplete_line(self):
        """Fill the rest of the current line (or the next one, if this one is done).

        Filled characters are marked ASSIST, so they are excluded from wpm and accuracy.
        """
        if self.finished or self.pos >= len(self.target):
            return []
        now = time.monotonic()
        if self.start_time is None:
            self.start_time = now
        step = []

        def fill():
            self.state[self.pos] = ASSIST
            step.append(self.pos)
            self.pos += 1

        if self.target[self.pos] == "\n":  # this line is done: complete the next one
            fill()
            if self.auto_indent:
                step += self._skip_indent()
        while self.pos < len(self.target) and self.target[self.pos] != "\n":
            fill()
        if self.pos < len(self.target):
            fill()
            if self.auto_indent:
                step += self._skip_indent()
        self.steps.append(step)
        self.assist_uses += 1
        self.last_key_time = now  # don't charge the time before this to any block
        self._check_done()
        return step

    def assist_chars(self):
        return sum(1 for p, s in enumerate(self.state) if s == ASSIST and self.target[p] != "\n")

    def pause(self):
        if self.start_time is not None and not self.finished and self.paused_at is None:
            self.paused_at = time.monotonic()

    def resume(self):
        if self.paused_at is not None:
            gap = time.monotonic() - self.paused_at
            self.start_time += gap
            if self.last_key_time is not None:
                self.last_key_time += gap
            self.paused_at = None

    def backspace(self, word=False):
        """Undo the last step; with word=True, undo back to the previous whitespace."""
        if self.finished or not self.steps:
            return []
        changed = []

        def pop():
            step = self.steps.pop()
            for p in step:
                self.state[p] = PENDING
            self.pos = step[0]
            changed.extend(step)

        pop()
        if word:
            while self.steps and not self.target[self.steps[-1][0]].isspace():
                pop()
        return changed

    # ---- stats -----------------------------------------------------------

    def elapsed(self):
        if self.start_time is None:
            return 0.0
        return (self.end_time or self.paused_at or time.monotonic()) - self.start_time

    def correct_chars(self):
        return sum(1 for s in self.state if s == CORRECT)

    def wpm(self):
        minutes = self.elapsed() / 60
        return self.correct_chars() / 5 / minutes if minutes > 0 else 0.0

    def raw_wpm(self):
        minutes = self.elapsed() / 60
        return self.keystrokes / 5 / minutes if minutes > 0 else 0.0

    def accuracy(self):
        if not self.keystrokes:
            return 100.0
        return 100.0 * self.correct_keystrokes / self.keystrokes

    def progress(self):
        return self.pos / len(self.target) if self.target else 0.0

    def _series(self):
        total = self.elapsed()
        points = []
        if total <= 0:
            return points
        idx = keys = good = 0
        for s in range(1, max(1, math.ceil(total)) + 1):
            t = min(s, total)
            errs = 0
            while idx < len(self.events) and self.events[idx][0] <= t + 1e-9:
                keys += 1
                good += self.events[idx][1]
                errs += not self.events[idx][1]
                idx += 1
            minutes = t / 60
            points.append((t, good / 5 / minutes, keys / 5 / minutes, errs))
        return points

    def summary(self):
        sections = []
        for i, s in enumerate(self.sections):
            keys = self.sec_keys[i]
            sections.append({
                "title": s.title,
                "lines": s.lines_label,
                "time": self.sec_time[i],
                "keys": keys,
                "errors": self.sec_errors[i],
                "accuracy": 100.0 * (keys - self.sec_errors[i]) / keys if keys else 100.0,
            })
        return Results(
            wpm=self.wpm(),
            raw=self.raw_wpm(),
            accuracy=self.accuracy(),
            elapsed=self.elapsed(),
            correct_chars=self.correct_chars(),
            wrong_chars=sum(1 for s in self.state if s == WRONG),
            keystrokes=self.keystrokes,
            errors=self.keystrokes - self.correct_keystrokes,
            missed=Counter(self.missed),
            series=self._series(),
            sections=sections,
            assist_uses=self.assist_uses,
            assist_chars=self.assist_chars(),
        )


def key_name(ch):
    return {" ": "space", "\n": "enter", "\t": "tab"}.get(ch, ch)
