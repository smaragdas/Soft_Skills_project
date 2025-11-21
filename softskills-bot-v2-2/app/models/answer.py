from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, BigInteger
from sqlalchemy.sql import func

class Answer(SQLModel, table=True):
    __tablename__ = "answers"

    # BIGSERIAL
    id: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True)
    )

    # 🔧 ΠΡΟΣΘΕΣΕ αυτά τα δύο πεδία
    user_id:    Optional[str] = Field(default=None, index=True)
    text:       Optional[str] = None

    question_id: Optional[str] = Field(default=None, index=True)
    prompt:      Optional[str] = None
    category:    Optional[str] = None
    qtype:       Optional[str] = None

    # created_at TIMESTAMPTZ DEFAULT NOW()
    created_at: datetime = Field(sa_column_kwargs={"server_default": func.now()})
