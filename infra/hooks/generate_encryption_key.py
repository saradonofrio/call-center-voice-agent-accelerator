#!/usr/bin/env python3
"""
Generate a Fernet encryption key for PII anonymization.

This script generates a proper Fernet-compatible encryption key
that can be stored in Azure Key Vault during infrastructure provisioning.
"""

from cryptography.fernet import Fernet

if __name__ == "__main__":
    key = Fernet.generate_key()
    print(key.decode())
