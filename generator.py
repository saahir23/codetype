"""Asks a local Ollama model to solve a coding question in Python as typeable, explained blocks.

Uses only the standard library (urllib) to talk to Ollama's HTTP API.
"""
import json
import os
import urllib.error
import urllib.request

from models import Section, Snippet

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_URL.startswith("http"):
    OLLAMA_URL = "http://" + OLLAMA_URL

SUGGESTED_MODEL = "qwen2.5-coder:7b"
# Coding models first when choosing a default.
PREFERRED = ("qwen2.5-coder", "qwen3-coder", "deepseek-coder", "codellama", "codegemma",
             "starcoder", "qwen", "deepseek", "llama3", "gemma", "phi", "mistral")

# Requested line counts. Long snippets get tiring to type, so even "long" is capped.
LENGTHS = {"short": "8-20", "medium": "20-40", "long": "40-60"}

NOT_RUNNING = ("Can't reach Ollama at " + OLLAMA_URL + ".\n\n"
               "Start it by opening the Ollama app (or run `ollama serve` in a terminal), "
               "then press the refresh button next to the model list.")

SYSTEM_PROMPT = """You are a Python tutor. Solve the user's coding question in Python 3 and \
teach the solution. Your answer is shown in a typing-practice app: the learner types the \
code block by block, and the explanation of the block they are on is shown next to it.

Return JSON with:
- title: a short name for the solution.
- overview: 2-3 sentences explaining the approach.
- complexity: time and space complexity, e.g. "O(n) time, O(1) space".
- code: the complete Python program, runnable as-is with only the standard library.
- blocks: walk through `code` from top to bottom in pieces of 1-6 lines each, such as an \
import, a function signature, a loop, a condition, a return, or the usage example. \
Together the blocks cover every line of `code`, in order. Each block has:
  - title: a few words naming what the block does.
  - code: the lines of this block, copied exactly from `code`.
  - explanation: 1-3 simple sentences saying what the block does, why, and what each \
function, method or keyword in it means.
  - concepts: 1-3 short tags such as "recursion" or "dictionary".

Code rules: correct, idiomatic Python that follows PEP 8, indented with 4 spaces, ASCII \
characters only, few or no comments (the explanations are shown separately), and ending \
with a short usage example that prints a result."""

MAX_ATTEMPTS = 2  # one retry if the model's code has a syntax error

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "overview": {"type": "string"},
        "complexity": {"type": "string"},
        "code": {"type": "string"},
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "code": {"type": "string"},
                    "explanation": {"type": "string"},
                    "concepts": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "code", "explanation", "concepts"],
            },
        },
    },
    "required": ["title", "overview", "complexity", "code", "blocks"],
}

_REPLACEMENTS = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
}
# Top-level lines starting with these get a blank line before them.
_DEFINITIONS = ("def ", "async def ", "class ", "@")
_COMMENTS = ("#",)


class GenerationError(Exception):
    """A problem worth showing to the user as-is."""


def _request(path, body=None, timeout=10.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(OLLAMA_URL + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_models():
    """Installed chat models, best coding models first."""
    try:
        data = _request("/api/tags", timeout=3)
    except (urllib.error.URLError, OSError, ValueError):
        raise GenerationError(NOT_RUNNING)
    names = [m["name"] for m in data.get("models", []) if "embed" not in m["name"]]

    def rank(name):
        return next((i for i, p in enumerate(PREFERRED) if p in name), len(PREFERRED))

    return sorted(names, key=rank)


def solve(question: str, length: str, model: str) -> Snippet:
    """Ask the model, and send its code back once for fixing if it doesn't compile."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {question}\n"
                                    f"Length: about {LENGTHS.get(length, '20-40')} lines "
                                    f"of code in total."},
    ]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        content = _chat(model, messages)
        try:
            parsed = json.loads(content)
        except ValueError:
            if attempt == MAX_ATTEMPTS:
                raise GenerationError("The model's answer wasn't valid JSON. Try again, or use "
                                      f"a coding model such as {SUGGESTED_MODEL}.")
            continue
        snippet = build_snippet(parsed)
        error = syntax_error(snippet.code)
        if error is None:
            snippet.question = question
            snippet.model = model
            return snippet
        messages += [
            {"role": "assistant", "content": content},
            {"role": "user", "content": f"That code has a Python syntax error ({error}). "
                                        "Return the corrected JSON in the same format."},
        ]
    raise GenerationError(f"The model kept writing code with a syntax error ({error}). "
                          "Try asking again or rephrasing the question.")


def syntax_error(code: str):
    """Describe the first syntax error in the code, or None. Compiles only, never runs it."""
    try:
        compile(code, "answer.py", "exec")
    except SyntaxError as e:
        return f"line {e.lineno}: {e.msg}"
    except ValueError as e:
        return str(e)
    return None


def _chat(model, messages):
    body = {
        "model": model,
        "stream": False,
        "format": SCHEMA,
        "options": {"temperature": 0.2},
        "messages": messages,
    }
    try:
        data = _request("/api/chat", body, timeout=900)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", "")
        except (OSError, ValueError):
            detail = ""
        if e.code == 404:
            raise GenerationError(f"The model '{model}' isn't installed.\n\n"
                                  f"Run:  ollama pull {model}")
        raise GenerationError(f"Ollama returned an error ({e.code}). {detail}".strip())
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
            raise GenerationError("The model took too long to answer. Try a shorter length "
                                  "or a smaller model.")
        raise GenerationError(NOT_RUNNING)
    return data.get("message", {}).get("content", "")


def _clean_lines(code: str) -> list[str]:
    """Make code typeable: plain ASCII, spaces not tabs, no fences or trailing spaces."""
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    for bad, good in _REPLACEMENTS.items():
        code = code.replace(bad, good)
    code = "".join(ch if ord(ch) < 128 else "?" for ch in code.expandtabs(4))
    lines = [line.rstrip() for line in code.split("\n") if not line.strip().startswith("```")]
    cleaned = []
    for line in lines:
        if line or (cleaned and cleaned[-1]):  # collapse runs of blank lines
            cleaned.append(line)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return cleaned


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _needs_gap(prev: str, first: str) -> bool:
    """Should a blank line separate two blocks? Mirrors how people space out code."""
    if _indent(first) > 0 or prev.startswith("@"):
        return False
    return (_indent(prev) > 0 or prev.strip() in ("}", "};", "end")
            or first.startswith(_DEFINITIONS))


def _section(block, start, end):
    concepts = [str(c).strip() for c in block.get("concepts", []) if str(c).strip()]
    return Section(
        start_line=start,
        end_line=end,
        title=str(block.get("title", "")).strip() or "Block",
        explanation=str(block.get("explanation", "")).strip(),
        concepts=concepts[:3],
    )


def _find_line(lines, wanted, start):
    """Index of the first line at or after `start` matching `wanted` (ignoring indentation)."""
    for i in range(start, len(lines)):
        if lines[i].strip() == wanted:
            return i
    if len(wanted) >= 8:  # tolerate a model trimming or extending a long line
        for i in range(start, len(lines)):
            got = lines[i].strip()
            if got and (got.startswith(wanted) or wanted.startswith(got)):
                return i
    return None


def _align_blocks(lines, blocks):
    """Map each block onto the full program by where its first line appears.

    The full program is the source of truth: a block runs until the next block starts,
    so a line the model left out of a block still stays in the code.
    """
    starts = []
    cursor = 0
    for block in blocks:
        first = next(l.strip() for l in _clean_lines(str(block.get("code", ""))) if l.strip())
        index = _find_line(lines, first, cursor)
        if index is not None:
            cursor = index + 1
            # A comment right above a block describes that block, so it belongs to it.
            floor = starts[-1][0] + 1 if starts else 0
            while index > floor and lines[index - 1].lstrip().startswith(_COMMENTS):
                index -= 1
            starts.append((index, block))
    sections = []
    for k, (index, block) in enumerate(starts):
        end = starts[k + 1][0] - 1 if k + 1 < len(starts) else len(lines) - 1
        while end > index and not lines[end]:
            end -= 1
        sections.append(_section(block, index + 1, end + 1))
    return sections


def _join_blocks(blocks):
    """Fallback when there is no full program: glue the blocks together."""
    lines: list[str] = []
    sections: list[Section] = []
    for block in blocks:
        block_lines = _clean_lines(str(block.get("code", "")))
        if lines and _needs_gap(lines[-1], block_lines[0]):
            lines.append("")
        start = len(lines) + 1
        lines.extend(block_lines)
        sections.append(_section(block, start, len(lines)))
    return lines, sections


def build_snippet(data: dict) -> Snippet:
    """Turn the model's JSON into a Snippet: clean code plus where each block sits."""
    blocks = [b for b in data.get("blocks", []) if _clean_lines(str(b.get("code", "")))]
    lines = _clean_lines(str(data.get("code", "")))
    while lines and not lines[0]:
        lines.pop(0)
    if lines:
        sections = _align_blocks(lines, blocks)
    else:
        lines, sections = _join_blocks(blocks)
    if not lines:
        raise GenerationError("The model returned no code. Try again.")
    overview = str(data.get("overview", "")).strip()
    if not sections:
        sections = [Section(1, len(lines), "Whole program", overview)]

    return Snippet(
        title=str(data.get("title", "")).strip() or "Solution",
        language="Python",
        overview=overview,
        code="\n".join(lines),
        sections=sections,
        complexity=str(data.get("complexity", "")).strip(),
    )
