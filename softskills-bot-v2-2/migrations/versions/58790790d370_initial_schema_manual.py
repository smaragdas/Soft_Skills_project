"""initial schema (manual)

Revision ID: 000000000001
Revises: 
Create Date: 2025-10-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

# revision identifiers, used by Alembic.
revision = "000000000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # participants
    op.create_table(
        "participants",
        sa.Column("participant_id", pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False, unique=True),
        sa.Column("cohort", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), server_default=sa.text("NOW()"), nullable=False),
    )

    # sessions (pre/post per participant)
    op.create_table(
        "sessions",
        sa.Column("session_id", pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("participant_id", pg.UUID(as_uuid=True), sa.ForeignKey("participants.participant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase", sa.String(length=8), nullable=False),  # 'pre' | 'post'
        sa.Column("started_at", sa.TIMESTAMP(timezone=False), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=False), nullable=True),
        sa.CheckConstraint("phase IN ('pre','post')", name="ck_sessions_phase"),
        sa.UniqueConstraint("participant_id", "phase", name="uq_sessions_participant_phase"),
    )
    op.create_index("idx_sessions_pid", "sessions", ["participant_id"])

    # responses (answers per item)
    op.create_table(
        "responses",
        sa.Column("response_id", pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("session_id", pg.UUID(as_uuid=True), sa.ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),   # leadership, communication, teamwork, problem_solving
        sa.Column("qtype", sa.String(length=8), nullable=False),       # 'mc' | 'open'
        sa.Column("answer_json", pg.JSONB, nullable=True),
        sa.Column("score_raw", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_responses_session", "responses", ["session_id"])
    op.create_index("idx_responses_category", "responses", ["category"])

    # per-category normalized scores (0..100) + level
    op.create_table(
        "scores",
        sa.Column("session_id", pg.UUID(as_uuid=True), sa.ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("score_norm", sa.Numeric(), nullable=False),  # 0..100
        sa.Column("level", sa.String(length=8), nullable=False),  # 'low' | 'mid' | 'high'
        sa.PrimaryKeyConstraint("session_id", "category", name="pk_scores"),
    )

    # delivered materials log (for audit)
    op.create_table(
        "materials_delivered",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("session_id", pg.UUID(as_uuid=True), sa.ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("file_key", sa.Text(), nullable=False),  # e.g. leadership/leadership_mid.pdf
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=False), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("downloaded_at", sa.TIMESTAMP(timezone=False), nullable=True),
    )

    # post-test tokens (magic links)
    op.create_table(
        "post_tokens",
        sa.Column("nonce", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("participant_id", pg.UUID(as_uuid=True), sa.ForeignKey("participants.participant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=False), nullable=False),
        sa.Column("used", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), server_default=sa.text("NOW()"), nullable=False),
    )

    # rater ratings (blind)
    op.create_table(
        "rater_ratings",
        sa.Column("rating_id", pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("answer_id", pg.UUID(as_uuid=True), sa.ForeignKey("responses.response_id", ondelete="CASCADE"), nullable=False),
        sa.Column("rater_id", sa.String(length=64), nullable=False),
        sa.Column("score_rater", sa.Numeric(), nullable=False),  # 0..1
        sa.Column("updated_at", sa.TIMESTAMP(timezone=False), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("answer_id", "rater_id", name="uq_ratings_answer_rater"),
    )
    op.create_index("idx_ratings_answer", "rater_ratings", ["answer_id"])


def downgrade() -> None:
    op.drop_index("idx_ratings_answer", table_name="rater_ratings")
    op.drop_table("rater_ratings")
    op.drop_table("post_tokens")
    op.drop_table("materials_delivered")
    op.drop_table("scores")
    op.drop_index("idx_responses_category", table_name="responses")
    op.drop_index("idx_responses_session", table_name="responses")
    op.drop_table("responses")
    op.drop_index("idx_sessions_pid", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("participants")
