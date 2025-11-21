
from typing import Optional, Dict
from pydantic import BaseModel

class GLMPMeasures(BaseModel):
    meta: Optional[dict] = None
    text: Optional[Dict[str, float]] = None
    audio: Optional[Dict[str, float]] = None
