from pydantic import BaseModel
from typing import Dict, Optional

class ScoreOpenRequest(BaseModel):
    category: str
    question_id: str
    text: str
    user_id: Optional[str] = None

class ScoreOpenResponse(BaseModel):
    text: str
    category: str
    question_id: str
    feedback: Dict[str, str]
    model: str = "heuristic"
    score: float = 0.0