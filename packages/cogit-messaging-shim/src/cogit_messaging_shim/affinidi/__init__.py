"""Optional native Affinidi DID authentication and independently signed responses."""

from .client import DidAuthClient, DidAuthConfig, DidAuthError, DidSession
from .jws import IdentityError, sign_jws, sign_quote, verification_method, verify_jws, verify_quote

__all__ = ["DidAuthClient", "DidAuthConfig", "DidAuthError", "DidSession", "IdentityError",
           "sign_jws", "sign_quote", "verification_method", "verify_jws", "verify_quote"]
