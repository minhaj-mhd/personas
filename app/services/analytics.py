"""Analytics helpers (pure, unit-testable)."""


def estimate_speaking_minutes(
    char_count: int, wpm: int = 150, chars_per_word: float = 5.0
) -> float:
    """Rough spoken-time estimate from a character count.

    We don't store audio durations, so approximate: chars → words (~5 chars/word) →
    minutes at a conversational ~150 wpm. Returns minutes rounded to 1 decimal.
    """
    if char_count <= 0:
        return 0.0
    words = char_count / chars_per_word
    return round(words / wpm, 1)
