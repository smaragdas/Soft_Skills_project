from datetime import datetime
from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field, Column, JSON
from pydantic import ConfigDict

class Interaction(SQLModel, table=True):
    answer_id: str = Field(primary_key=True)
    category: str
    qtype: str  # 'open' or 'mc'
    question_id: str
    text_raw: Optional[str] = None
    user_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AutoRating(SQLModel, table=True):
    model_config = ConfigDict(protected_namespaces=())
    id: Optional[int] = Field(default=None, primary_key=True)
    answer_id: str = Field(foreign_key="interaction.answer_id")
    score: float
    confidence: Optional[float] = Field(default=None)
    model_name: Optional[str] = Field(default=None)
    feedback: Optional[str] = Field(default=None)
    coaching: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class HumanRating(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    answer_id: str
    rater_id: str
    score: float
    notes: Optional[str] = None
