# app/core/settings.py
from __future__ import annotations

import os
from dataclasses import dataclass

# Προσπάθησε να φορτώσεις .env αν υπάρχει (δεν απαιτείται για να τρέξει)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    # Αν ο χρήστης γράψει "0,2" (ελληνικό κόμμα), το μετατρέπουμε σε 0.2
    raw = raw.replace(",", ".")
    try:
        return float(raw)
    except Exception:
        return default


@dataclass
class Settings:
    # Βασικά
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "softskills-bot")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///softskills.db")

    # API key του δικού μας FastAPI (x-api-key)
    API_KEY: str = os.getenv("API_KEY", "supersecret123")

    # OpenAI ρυθμίσεις (προαιρετικές – για LLM coaching)
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY") or None
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4-0613")  # or another valid model
    OPENAI_TEMPERATURE: float = _get_float("OPENAI_TEMPERATURE", 0.2)
    OPENAI_BASE_URL: str | None = os.getenv("OPENAI_BASE_URL") or None

    # Ανάλυση μόνο με κανόνες
    HEURISTIC_ONLY: bool = bool(os.getenv("HEURISTIC_ONLY", "false").lower() == "true")

    @property
    def LLM_configured(self) -> bool:
        """Αν υπάρχει OPENAI_API_KEY θεωρούμε ότι το LLM είναι διαθέσιμο."""
        return bool(self.OPENAI_API_KEY)

    def masked_openai_key(self) -> str:
        """Επιστρέφει το API key μασκαρισμένο για προβολή στα /_diag/config."""
        key = self.OPENAI_API_KEY or ""
        if not key:
            return ""
        if len(key) <= 8:
            return "*" * len(key)
        return "*" * (len(key) - 8) + key[-8:]


# Singleton ρυθμίσεων που κάνουν import τα υπόλοιπα modules
settings = Settings()
