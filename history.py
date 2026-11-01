"""Saves finished runs and past free-ground questions under data/."""
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from models import Section, Snippet

DATA_DIR = Path(__file__).parent / "data"
HISTORY_FILE = DATA_DIR / "history.json"
QUESTIONS_FILE = DATA_DIR / "questions.json"
MAX_RUNS = 500
MAX_QUESTIONS = 100


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _write(path, items):
    try:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(items, indent=1), encoding="utf-8")
    except OSError:
        pass  # saving is a bonus; never crash the app over it


# ---- typing runs ----------------------------------------------------------

def load():
    return _read(HISTORY_FILE)


def save_run(entry):
    runs = load()
    runs.append(entry)
    _write(HISTORY_FILE, runs[-MAX_RUNS:])


def all_time_missed(runs):
    total = Counter()
    for run in runs:
        total.update(run.get("missed", {}))
    return total


def _average(runs, key):
    values = [r[key] for r in runs if key in r]
    return sum(values) / len(values) if values else None


def summarize(runs):
    """Everything the profile page shows. Autocomplete is kept apart from typing stats."""
    recent, previous = runs[-10:], runs[-20:-10]
    best = max(runs, key=lambda r: r.get("wpm", 0), default=None)
    by_mode = {}
    for mode in ("free", "tutorials"):
        mode_runs = [r for r in runs if r.get("mode") == mode]
        by_mode[mode] = {"runs": len(mode_runs), "wpm": _average(mode_runs, "wpm"),
                         "accuracy": _average(mode_runs, "accuracy")}

    assisted = [r for r in runs if r.get("assist", {}).get("uses")]
    assist_chars = sum(r["assist"].get("chars", 0) for r in assisted)
    code_chars = sum(r.get("assist", {}).get("total", 0) for r in runs)
    return {
        "runs": len(runs),
        "time": sum(r.get("time", 0) for r in runs),
        "chars": sum(r.get("chars", 0) for r in runs),
        "best_wpm": best.get("wpm", 0) if best else None,
        "best_title": best.get("title", "") if best else "",
        "recent_wpm": _average(recent, "wpm"),
        "recent_accuracy": _average(recent, "accuracy"),
        "previous_wpm": _average(previous, "wpm"),
        "by_mode": by_mode,
        "lessons_done": sorted({r.get("title", "") for r in runs if r.get("mode") == "tutorials"}),
        "missed": all_time_missed(runs),
        "assist": {
            "uses": sum(r["assist"]["uses"] for r in assisted),
            "chars": assist_chars,
            "share": 100 * assist_chars / code_chars if code_chars else 0.0,
            "runs": len(assisted),
        },
    }


# ---- free-ground questions -------------------------------------------------

def save_question(snippet: Snippet):
    """Keep answered questions so they can be practised again, newest first."""
    items = [q for q in _read(QUESTIONS_FILE)
             if (q.get("question"), q.get("language")) != (snippet.question, snippet.language)]
    entry = asdict(snippet)
    entry["date"] = datetime.now().isoformat(timespec="seconds")
    items.insert(0, entry)
    _write(QUESTIONS_FILE, items[:MAX_QUESTIONS])


def load_questions() -> list[Snippet]:
    snippets = []
    for q in _read(QUESTIONS_FILE):
        try:
            q = dict(q)
            q.pop("date", None)
            q["sections"] = [Section(**s) for s in q["sections"]]
            snippets.append(Snippet(**q))
        except (KeyError, TypeError):
            continue  # skip entries written by an older version
    return snippets
