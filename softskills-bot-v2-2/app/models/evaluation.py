# app/models/evaluation.py
from sqlmodel import SQLModel, Field, Column, JSON
from typing import Optional, Dict, Any
from datetime import datetime

class Evaluation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[str] = Field(default=None, index=True)
    question_id: Optional[str] = Field(default=None, index=True)
    category: str = Field(index=True)
    modalities: str  # csv "mcq,text"

    measures: Dict[str, Any] = Field(sa_column=Column(JSON))
    result: Dict[str, Any] = Field(sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
