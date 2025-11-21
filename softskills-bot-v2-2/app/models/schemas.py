from pydantic import BaseModel, Field
from typing import Optional, List

class ScoreOpenIn(BaseModel):
    category: str
    question_id: str
    text: str
    user_id: Optional[str] = None

class ScoreMCIn(BaseModel):
    category: str
    question_id: str
    choices: List[str]
    user_id: Optional[str] = None

class ScoreOut(BaseModel):
    status: str
    category: str
    question_id: str
    answer_id: str
    score: float
    confidence: float
    rationale: str
    saved: bool = False
