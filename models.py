"""Shared data types for codetype."""
from dataclasses import dataclass, field


@dataclass
class Section:
    """A block of the code (e.g. a loop or a function) with its explanation."""
    start_line: int  # 1-based, inclusive
    end_line: int    # 1-based, inclusive
    title: str
    explanation: str
    concepts: list[str] = field(default_factory=list)

    @property
    def lines_label(self) -> str:
        if self.start_line == self.end_line:
            return f"line {self.start_line}"
        return f"lines {self.start_line}-{self.end_line}"


@dataclass
class Snippet:
    """A piece of code to type, plus everything the side panel needs."""
    title: str
    language: str
    overview: str
    code: str
    sections: list[Section]
    complexity: str = ""
    question: str = ""  # free ground: what the user asked
    model: str = ""     # free ground: which Ollama model answered
    level: str = ""     # tutorials: Beginner / Intermediate / Advanced
