"""
Azure AD / Entra ID Authentication Module

Provides JWT token validation for API endpoints using Microsoft Identity Platform.
"""

import logging
import os
from functools import wraps
from typing import Optional, List

import jwt
from jwt import PyJWKClient
from quart import request, jsonify

logger = logging.getLogger(__name__)


class AzureADAuth:
    """Azure AD authentication handler for API endpoints."""
    
    def __init__(self, tenant_id: str, client_id: str, audience: Optional[str] = None):
        """
        Initialize Azure AD authentication.
        
        Args:
            tenant_id: Azure AD tenant ID
            client_id: Application (client) ID from app registration
            audience: Expected audience in token (defaults to client_id)
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.audience = audience or f"api://{client_id}"
        
        # Microsoft's public key endpoint for token validation
        self.jwks_uri = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        self.issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        
        # Initialize JWKS client for fetching public keys
        self.jwks_client = PyJWKClient(self.jwks_uri)
        
        logger.info("Azure AD Auth initialized - Tenant: %s, Client: %s", tenant_id, client_id)
    
    def validate_token(self, token: str) -> dict:
        """
        Validate JWT token from Azure AD.
        
        Args:
            token: JWT token from Authorization header
            
        Returns:
            dict: Decoded token claims if valid
            
        Raises:
            jwt.InvalidTokenError: If token is invalid
        """
        try:
            # Get signing key from Microsoft's JWKS endpoint
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            
            # Decode and validate token
            decoded = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                }
            )
            
            logger.info("Token validated successfully for user: %s", 
                       decoded.get("preferred_username", "unknown"))
            return decoded
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            raise
        except jwt.InvalidAudienceError:
            logger.warning("Invalid token audience")
            raise
        except jwt.InvalidIssuerError:
            logger.warning("Invalid token issuer")
            raise
        except Exception as e:
            logger.error("Token validation failed: %s", str(e))
            raise
    
    def has_role(self, token_claims: dict, required_role: str) -> bool:
        """
        Check if token contains required app role.
        
        Args:
            token_claims: Decoded token claims
            required_role: Required role name (e.g., 'Admin', 'User')
            
        Returns:
            bool: True if user has the role
        """
        roles = token_claims.get("roles", [])
        return required_role in roles
    
    def get_user_info(self, token_claims: dict) -> dict:
        """
        Extract user information from token claims.
        
        Args:
            token_claims: Decoded token claims
            
        Returns:
            dict: User information
        """
        return {
            "user_id": token_claims.get("oid"),  # Object ID
            "username": token_claims.get("preferred_username"),
            "name": token_claims.get("name"),
            "email": token_claims.get("email"),
            "roles": token_claims.get("roles", []),
        }


def require_auth(auth_handler: AzureADAuth, required_roles: Optional[List[str]] = None):
    """
    Decorator to require Azure AD authentication on endpoints.
    
    Args:
        auth_handler: AzureADAuth instance
        required_roles: Optional list of required roles (e.g., ['Admin'])
        
    Usage:
        @app.route("/api/documents", methods=["POST"])
        @require_auth(azure_ad_auth, required_roles=["Admin"])
        async def upload_documents():
            # Access user info from g.user
            user = g.user
            ...
    """
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            # Extract token from Authorization header
            auth_header = request.headers.get('Authorization')
            
            if not auth_header:
                logger.warning("No Authorization header provided")
                return jsonify({"error": "Missing Authorization header"}), 401
            
            if not auth_header.startswith('Bearer '):
                logger.warning("Invalid Authorization header format")
                return jsonify({"error": "Invalid Authorization header format"}), 401
            
            token = auth_header.split(' ')[1]
            
            try:
                # Validate token
                token_claims = auth_handler.validate_token(token)
                
                # Check required roles if specified
                if required_roles:
                    user_roles = token_claims.get("roles", [])
                    if not any(role in user_roles for role in required_roles):
                        logger.warning(
                            "User %s missing required roles. Has: %s, Needs: %s",
                            token_claims.get("preferred_username"),
                            user_roles,
                            required_roles
                        )
                        return jsonify({
                            "error": "Insufficient permissions",
                            "required_roles": required_roles
                        }), 403
                
                # Store user info in request context
                from quart import g
                g.user = auth_handler.get_user_info(token_claims)
                g.token_claims = token_claims
                
                # Call the actual endpoint
                return await f(*args, **kwargs)
                
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token has expired"}), 401
            except jwt.InvalidTokenError as e:
                logger.warning("Invalid token: %s", str(e))
                return jsonify({"error": "Invalid token"}), 401
            except Exception as e:
                logger.error("Authentication error: %s", str(e), exc_info=True)
                return jsonify({"error": "Authentication failed"}), 500
        
        return decorated_function
    return decorator


def require_auth_optional(auth_handler: AzureADAuth):
    """
    Decorator for optional authentication (extracts user if token present).
    
    Useful for endpoints that work with or without authentication,
    but provide different functionality based on auth status.
    """
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                try:
                    token_claims = auth_handler.validate_token(token)
                    from quart import g
                    g.user = auth_handler.get_user_info(token_claims)
                    g.token_claims = token_claims
                except Exception as e:
                    logger.warning("Optional auth failed: %s", str(e))
                    # Continue without auth
            
            return await f(*args, **kwargs)
        
        return decorated_function
    return decorator
