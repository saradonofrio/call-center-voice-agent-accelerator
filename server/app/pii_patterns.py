"""
PII Detection Patterns for Italian Context.

This module contains regex patterns and keyword lists for detecting
Personally Identifiable Information (PII) in Italian text.
"""

import re

# ============================================================
# PHONE NUMBER PATTERNS
# ============================================================
PHONE_PATTERNS = [
    # Italian mobile: +39 3XX XXXXXXX
    r'\+39\s?3\d{2}\s?\d{3}\s?\d{3,4}',
    # Mobile without country code: 3XX XXXXXXX
    r'\b3\d{2}[\s\-]?\d{3}[\s\-]?\d{3,4}\b',
    # Italian landline: +39 0XX XXXXXX
    r'\+39\s?0\d{1,3}\s?\d{6,8}',
    # Landline without country code: 0XX XXXXXX
    r'\b0\d{1,3}[\s\-]?\d{6,8}\b',
]

# ============================================================
# FISCAL CODE PATTERN (Codice Fiscale)
# ============================================================
# Format: 6 letters + 2 digits + letter + 2 digits + letter + 3 digits + letter
FISCAL_CODE_PATTERN = r'\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b'

# ============================================================
# EMAIL ADDRESS PATTERN
# ============================================================
EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

# ============================================================
# CREDIT CARD PATTERN
# ============================================================
# Matches: 1234 5678 9012 3456 or 1234-5678-9012-3456 or 1234567890123456
CREDIT_CARD_PATTERN = r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'

# ============================================================
# ITALIAN ADDRESS PATTERNS
# ============================================================
ADDRESS_PATTERNS = [
    # Via/Piazza/Corso + street name + number
    r'\b(via|piazza|corso|viale|largo|vicolo|str\.|v\.le)\s+[A-Za-zàèéìòù\s]+\s*,?\s*\d+',
    # CAP (postal code) + city
    r'\b\d{5}\s+[A-Za-zàèéìòù]+\b',
]

# ============================================================
# ITALIAN NAME PATTERNS (Common indicators)
# ============================================================
NAME_INDICATORS = [
    r'\bsono\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b',  # "sono Mario Rossi"
    r'\bchiamo\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b',  # "mi chiamo Mario Rossi"
    r'\bsig\.?\s+([A-Z][a-z]+)\b',  # "Sig. Rossi"
    r'\bsig\.ra\s+([A-Z][a-z]+)\b',  # "Sig.ra Rossi"
    r'\bdott\.?\s+([A-Z][a-z]+)\b',  # "Dott. Rossi"
]

# ============================================================
# MEDICAL TERMS (Pharmacy Context)
# ============================================================
# Terms that might be considered sensitive health data
MEDICAL_TERMS = [
    # Chronic conditions
    'diabete', 'diabetico', 'diabetica',
    'ipertensione', 'iperteso', 'ipertesa',
    'asma', 'asmatico', 'asmatica',
    'epilessia', 'epilettico', 'epilettica',
    'depressione', 'depresso', 'depressa',
    'ansia', 'ansioso', 'ansiosa',
    
    # Diseases
    'tumore', 'cancro', 'oncologico',
    'hiv', 'aids',
    'epatite',
    'insufficienza renale', 'insufficienza cardiaca',
    
    # Symptoms (may be too broad - use with caution)
    'chemioterapia', 'radioterapia',
    
    # Allergies
    'allergia', 'allergico', 'allergica',
    
    # Lab values
    'glicemia', 'emoglobina glicata', 'hba1c',
    'colesterolo', 'trigliceridi',
    'pressione arteriosa', 'pressione alta', 'pressione bassa',
    
    # Medications (specific drug names - partial list)
    'insulina', 'metformina',
    'warfarin', 'coumadin',
    'cardioaspirina',
]

# ============================================================
# ITALIAN COMMON NAMES (for enhanced detection)
# ============================================================
ITALIAN_FIRST_NAMES = [
    'mario', 'luigi', 'giuseppe', 'francesco', 'antonio', 'giovanni', 'pietro', 'paolo',
    'carlo', 'marco', 'andrea', 'stefano', 'alessandro', 'luca', 'matteo', 'davide',
    'maria', 'anna', 'lucia', 'sara', 'francesca', 'giovanna', 'rosa', 'elena',
    'laura', 'paola', 'claudia', 'giulia', 'chiara', 'valentina', 'federica', 'silvia',
]

ITALIAN_LAST_NAMES = [
    'rossi', 'russo', 'ferrari', 'esposito', 'bianchi', 'romano', 'colombo', 'ricci',
    'marino', 'greco', 'bruno', 'gallo', 'conti', 'de luca', 'costa', 'giordano',
    'mancini', 'rizzo', 'lombardi', 'moretti', 'barbieri', 'fontana', 'santoro', 'mariani',
]

# ============================================================
# GENERIC PII KEYWORDS
# ============================================================
PII_KEYWORDS = [
    'codice fiscale', 'tessera sanitaria', 'carta identità',
    'patente', 'passaporto', 'documento',
    'ricetta medica', 'prescrizione',
]

# ============================================================
# COMPILED PATTERNS (for performance)
# ============================================================
COMPILED_PHONE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in PHONE_PATTERNS]
COMPILED_FISCAL_CODE = re.compile(FISCAL_CODE_PATTERN)
COMPILED_EMAIL = re.compile(EMAIL_PATTERN, re.IGNORECASE)
COMPILED_CREDIT_CARD = re.compile(CREDIT_CARD_PATTERN)
COMPILED_ADDRESS_PATTERNS = [re.compile(p, re.IGNORECASE) for p in ADDRESS_PATTERNS]
COMPILED_NAME_INDICATORS = [re.compile(p, re.IGNORECASE) for p in NAME_INDICATORS]
