import re
from typing import Iterable

PAREN_COMMENT_RE = re.compile(r"\([^)]*\)")
WHITESPACE_RE = re.compile(r"\s+")


def strip_comments(line: str) -> str:
    candidate = line.strip()
    if not candidate or candidate.startswith("%"):
        return ""

    # Remove inline parenthesis comments first, then semicolon comments.
    without_paren_comments = PAREN_COMMENT_RE.sub("", candidate)
    without_semicolon_comments = without_paren_comments.split(";", 1)[0]
    cleaned = WHITESPACE_RE.sub(" ", without_semicolon_comments).strip()
    return cleaned


def parse_gcode_lines(lines: Iterable[str]) -> list[str]:
    parsed_lines: list[str] = []
    for line in lines:
        cleaned = strip_comments(line)
        if cleaned:
            parsed_lines.append(cleaned)
    return parsed_lines


def parse_gcode_text(text: str) -> list[str]:
    return parse_gcode_lines(text.splitlines())
