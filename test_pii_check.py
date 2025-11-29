#!/usr/bin/env python3
"""Test PII anonymization with real-world examples."""

import sys
sys.path.insert(0, '/workspaces/call-center-voice-agent-accelerator/server')

from app.pii_anonymizer import PIIAnonymizer

def test_pii_detection():
    """Test various PII scenarios."""
    
    anonymizer = PIIAnonymizer(reversible=True)
    
    test_cases = [
        # Phone numbers
        ("Il mio numero è 3401234567", "phone"),
        ("Chiamami al +39 340 123 4567", "phone"),
        ("Telefono: 340-123-4567", "phone"),
        ("02 12345678", "phone"),
        
        # Names
        ("Mi chiamo Mario Rossi", "name"),
        ("Sono Francesco D'Angelo", "name"),
        ("Dott. Bianchi", "name"),
        ("Sig.ra Ferrari", "name"),
        
        # Addresses
        ("Abito in Via Roma 123", "address"),
        ("20100 Milano", "address"),
        ("Corso Italia, 45", "address"),
        
        # Email
        ("La mia email è mario.rossi@gmail.com", "email"),
        
        # Fiscal code
        ("Il mio codice fiscale è RSSMRA80A01H501Z", "fiscal_code"),
        
        # Credit card
        ("Carta 1234 5678 9012 3456", "credit_card"),
        
        # Medical terms
        ("Soffro di diabete", "medical"),
        ("Ho la pressione alta", "medical"),
    ]
    
    print("=" * 80)
    print("TEST PII ANONYMIZATION")
    print("=" * 80)
    
    for i, (text, expected_pii) in enumerate(test_cases, 1):
        result = anonymizer.anonymize_text(text, f"test-session-{i}")
        
        print(f"\n{i}. Test: {expected_pii.upper()}")
        print(f"   Input:      '{text}'")
        print(f"   Output:     '{result['anonymized_text']}'")
        print(f"   PII Found:  {result['pii_found']}")
        
        if expected_pii in result['pii_found']:
            print(f"   Status:     ✅ PASS - {expected_pii} detected")
        else:
            print(f"   Status:     ❌ FAIL - {expected_pii} NOT detected!")
            print(f"   Expected:   [{expected_pii}]")
    
    # Complex test
    print("\n" + "=" * 80)
    print("COMPLEX TEST - Multiple PII types")
    print("=" * 80)
    
    complex_text = """
    Mi chiamo Mario Rossi, abito in Via Garibaldi 15, 20100 Milano.
    Il mio numero è 340 123 4567 e la mia email è mario.rossi@gmail.com.
    Codice fiscale: RSSMRA80A01H501Z
    Soffro di diabete e prendo insulina.
    """
    
    result = anonymizer.anonymize_text(complex_text.strip(), "test-complex")
    
    print(f"\nInput:\n{complex_text}")
    print(f"\nOutput:\n{result['anonymized_text']}")
    print(f"\nPII Found: {result['pii_found']}")
    print(f"\nAnonymization Map:")
    for token, value in result.get('anonymization_map', {}).items():
        print(f"  {token} -> {value}")

if __name__ == "__main__":
    test_pii_detection()
