# app/models/autorating.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB

class Autorating(SQLModel, table=True):
    __tablename__ = "autorating"

    id: Optional[int] = Field(default=None, primary_key=True)
    answer_id: str
    score: float
    confidence: Optional[float] = None
    model_name: Optional[str] = None

    feedback: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    coaching: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))

    created_at: datetime = Field(default_factory=datetime.utcnow)
