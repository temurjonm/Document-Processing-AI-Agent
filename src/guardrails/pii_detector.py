# Detects personally identifiable information (PII) in text using regex.
# PII types: SSN, email, phone, credit card numbers.
#
# This runs at two points:
# 1. During ingestion: tags chunks that contain PII (stored in metadata)
# 2. Before returning answers: scans for PII leakage in generated text
#
# For production: add spaCy NER for names/addresses (regex can't catch those).

import re  # Python's built-in regex module


# ── PII Regex Patterns ──
# Each pattern matches a specific type of PII
# Compiled patterns (re.compile) are faster than re.search with a string
PII_PATTERNS = {
    # SSN: 3 digits, dash, 2 digits, dash, 4 digits (e.g., 123-45-6789)
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),

    # Email: standard email format (e.g., john@example.com)
    # \S+ matches non-whitespace before/after the @
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),

    # Phone: matches common US formats (123-456-7890, 123.456.7890, 1234567890)
    # [-.]? means the separator is optional and can be dash or dot
    "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),

    # Credit card: 4 groups of 4 digits, separated by spaces or dashes
    # e.g., 4111-2222-3333-4444 or 4111 2222 3333 4444
    "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
}


def detect_pii(text: str) -> dict:
    """
    Scan text for PII using regex patterns.

    Args:
        text: the text to scan
    Returns:
        {has_pii: bool, entities: [{type, value, start, end}]}
    """
    entities = []  # will hold all detected PII entities

    # Run each pattern against the text
    for pii_type, pattern in PII_PATTERNS.items():
        # finditer returns all non-overlapping matches in the text
        # Each match has .group() (the matched text) and .start()/.end() (positions)
        for match in pattern.finditer(text):
            entities.append({
                "type": pii_type,                   # e.g., "ssn", "email"
                "value": match.group(),             # the actual matched text
                "start": match.start(),             # character position start
                "end": match.end()                  # character position end
            })

    return {
        "has_pii": len(entities) > 0,  # True if any PII was found
        "entities": entities,
        "count": len(entities)
    }


def redact_pii(text: str, entities: list[dict] = None) -> str:
    """
    Replace PII in text with [REDACTED] placeholders.
    If entities aren't provided, detect them first.

    Args:
        text: the text containing PII
        entities: optional — pre-detected entities from detect_pii()
    Returns:
        text with PII replaced by [REDACTED]
    """
    # If no entities provided, detect them
    if entities is None:
        detection = detect_pii(text)
        entities = detection["entities"]

    # If no PII found, return the text unchanged
    if not entities:
        return text

    # Sort entities by start position in REVERSE order
    # Why reverse? If we replace from the beginning, positions shift.
    # Replacing from the end keeps earlier positions valid.
    sorted_entities = sorted(entities, key=lambda e: e["start"], reverse=True)

    # Replace each PII entity with [REDACTED]
    for entity in sorted_entities:
        text = text[:entity["start"]] + "[REDACTED]" + text[entity["end"]:]

    return text


def scan_and_tag_chunk(chunk: dict) -> dict:
    """
    Scan a chunk for PII and add the result to its metadata.
    Called during ingestion to tag chunks that contain sensitive data.

    Args:
        chunk: a chunk dict from the chunker
    Returns:
        the chunk with added pii_detected metadata
    """
    detection = detect_pii(chunk["text"])

    # Add PII info to the chunk's metadata
    chunk["has_pii"] = detection["has_pii"]
    chunk["pii_types"] = list(set(e["type"] for e in detection["entities"]))

    return chunk