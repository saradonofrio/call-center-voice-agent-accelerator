#!/usr/bin/env python3
"""Test specifico per nomi con apostrofo."""

import sys
sys.path.insert(0, '/workspaces/call-center-voice-agent-accelerator/server')

from app.pii_anonymizer import PIIAnonymizer

anonymizer = PIIAnonymizer(reversible=True)

test_cases = [
    "Sono Francesco D'Angelo",
    "Mi chiamo Maria Dell'Orto",
    "Dott. D'Amico",
    "Sig. De Luca",
]

for text in test_cases:
    result = anonymizer.anonymize_text(text, f"test-{hash(text)}")
    print(f"Input:  '{text}'")
    print(f"Output: '{result['anonymized_text']}'")
    print(f"Map: {result.get('anonymization_map', {})}")
    print()
