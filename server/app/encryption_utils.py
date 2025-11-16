"""
Encryption utilities for PII anonymization maps using Azure Key Vault.

This module provides encryption/decryption for anonymization maps
to ensure PII is securely stored even in backup storage.
"""

import base64
import json
import logging
import os
from typing import Dict, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class EncryptionUtils:
    """
    Handles encryption/decryption of anonymization maps.
    
    Uses Fernet (symmetric encryption) with keys from Azure Key Vault.
    Falls back to environment variable for local development.
    """
    
    def __init__(self, encryption_key: str = None, key_vault_client=None, secret_name: str = "ANONYMIZATION-ENCRYPTION-KEY"):
        """
        Initialize encryption utilities.
        
        Args:
            encryption_key: Base64-encoded Fernet key. If None, tries Key Vault then env var.
            key_vault_client: Optional Azure Key Vault SecretClient for production use.
            secret_name: Name of the secret in Key Vault (default: ANONYMIZATION-ENCRYPTION-KEY).
        """
        if encryption_key:
            # Explicit key provided
            self.key = encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
            logger.info("Using explicitly provided encryption key")
        elif key_vault_client:
            # Production: Try to get from Key Vault
            try:
                secret = key_vault_client.get_secret(secret_name)
                self.key = secret.value.encode()
                logger.info(f"Successfully loaded encryption key from Key Vault secret: {secret_name}")
            except Exception as e:
                logger.error(f"Failed to retrieve encryption key from Key Vault: {e}")
                raise ValueError("Cannot initialize encryption without valid key from Key Vault")
        else:
            # Fallback: Try environment variable (for local development)
            env_key = os.environ.get("ANONYMIZATION_ENCRYPTION_KEY")
            if env_key:
                self.key = env_key.encode()
                logger.info("Using encryption key from ANONYMIZATION_ENCRYPTION_KEY environment variable")
            else:
                # Generate a key (for development only - NOT for production)
                logger.warning(
                    "No encryption key provided. Generating temporary key. "
                    "⚠️  WARNING: This key will be lost when the process restarts! "
                    "For production, use Azure Key Vault or set ANONYMIZATION_ENCRYPTION_KEY env var."
                )
                self.key = Fernet.generate_key()
        
        self.fernet = Fernet(self.key)
    
    def encrypt_map(self, anonymization_map: Dict[str, str]) -> str:
        """
        Encrypt an anonymization map.
        
        Args:
            anonymization_map: Dictionary mapping tokens to original values
            
        Returns:
            Base64-encoded encrypted data
        """
        try:
            # Convert to JSON
            json_data = json.dumps(anonymization_map, ensure_ascii=False)
            
            # Encrypt
            encrypted_data = self.fernet.encrypt(json_data.encode('utf-8'))
            
            # Return as base64 string
            return base64.b64encode(encrypted_data).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error encrypting anonymization map: {e}")
            raise
    
    def decrypt_map(self, encrypted_data: str) -> Dict[str, str]:
        """
        Decrypt an anonymization map.
        
        Args:
            encrypted_data: Base64-encoded encrypted data
            
        Returns:
            Decrypted anonymization map dictionary
        """
        try:
            # Decode base64
            encrypted_bytes = base64.b64decode(encrypted_data.encode('utf-8'))
            
            # Decrypt
            decrypted_data = self.fernet.decrypt(encrypted_bytes)
            
            # Parse JSON
            anonymization_map = json.loads(decrypted_data.decode('utf-8'))
            
            return anonymization_map
            
        except Exception as e:
            logger.error(f"Error decrypting anonymization map: {e}")
            raise
    
    def get_key_info(self) -> Dict:
        """
        Get information about the encryption key (for debugging).
        
        Returns:
            Dictionary with key information (not the key itself)
        """
        return {
            "key_length": len(self.key),
            "algorithm": "Fernet (AES-128 in CBC mode)",
            "key_source": "environment" if os.environ.get("ANONYMIZATION_ENCRYPTION_KEY") else "generated"
        }
    
    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet key.
        
        Returns:
            Base64-encoded key as string
        """
        key = Fernet.generate_key()
        return key.decode('utf-8')
    
    @staticmethod
    def derive_key_from_password(password: str, salt: bytes = None) -> str:
        """
        Derive an encryption key from a password.
        
        Args:
            password: Password string
            salt: Salt bytes (if None, uses a default - not recommended for production)
            
        Returns:
            Base64-encoded derived key
        """
        if salt is None:
            # Default salt (for development only)
            salt = b'pharmacy-voice-agent-salt-2025'
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key.decode('utf-8')


# Singleton instance
_encryption_utils = None


def get_encryption_utils() -> EncryptionUtils:
    """
    Get singleton instance of EncryptionUtils.
    
    Returns:
        EncryptionUtils instance
    """
    global _encryption_utils
    if _encryption_utils is None:
        _encryption_utils = EncryptionUtils()
    return _encryption_utils
