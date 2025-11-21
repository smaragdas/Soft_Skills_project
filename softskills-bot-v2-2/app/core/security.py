from fastapi import Request, HTTPException
from fastapi.security.utils import get_authorization_scheme_param
from app.core.settings import settings

async def verify_api_key(request: Request):
    """
    Ελέγχει αν υπάρχει σωστό API Key στο header x-api-key.
    """
    api_key = request.headers.get("x-api-key")
    if not api_key or api_key != getattr(settings, "API_KEY", "supersecret123"):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
