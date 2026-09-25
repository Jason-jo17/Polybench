import re

# Maps canonical language name to fence tags models commonly emit.
_LANG_ALIASES: dict[str, list[str]] = {
    "python": ["python", "py", "python3"],
    "javascript": ["javascript", "js", "typescript", "ts", "node"],
    "go": ["go", "golang"],
    "rust": ["rust", "rs"],
}

# Keywords that indicate plausible raw code (no fence) for a given language.
_LANG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "python": ("def ", "class "),
    "javascript": ("function ", "const ", "let ", "var ", "export "),
    "go": ("func ", "package "),
    "rust": ("fn ", "pub fn ", "impl "),
}


def extract_code(raw: str | None, language: str) -> str | None:
    """Extract a code block from raw LLM output.

    Preference order:
    1. Fenced block whose tag matches the language (or a known alias) — pick longest.
    2. Any generic fenced block — pick longest.
    3. Whole string if it looks like plausible code for the language.
    """
    if not raw:
        return None

    aliases = _LANG_ALIASES.get(language, [language])
    tag_pattern = "(?:" + "|".join(re.escape(a) for a in aliases) + ")"

    # 1. Language-tagged fenced blocks.
    lang_matches = re.findall(
        rf"```{tag_pattern}\s*\n(.*?)```",
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if lang_matches:
        return str(max(lang_matches, key=len)).strip()

    # 2. Any fenced block (```, ```anylang).
    generic_matches = re.findall(r"```(?:\w+)?\s*\n(.*?)```", raw, flags=re.DOTALL)
    if generic_matches:
        return str(max(generic_matches, key=len)).strip()

    # 3. Heuristic: does the raw string look like code for this language?
    keywords = _LANG_KEYWORDS.get(language, ())
    if any(kw in raw for kw in keywords):
        return raw.strip()

    return None
