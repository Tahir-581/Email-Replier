"""add email history and logs table

Revision ID: f2a07aa54445
Revises: 
Create Date: 2026-05-07 17:11:42.477725

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'f2a07aa54445'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # If this is a fresh DB (no tables yet), create baseline tables first.
    if not inspector.has_table("emails"):
        op.create_table(
            "emails",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("email_id", sa.VARCHAR(length=255), nullable=False),
            sa.Column("message_id", sa.VARCHAR(length=255), nullable=True),
            sa.Column("thread_id", sa.VARCHAR(length=255), nullable=True),
            sa.Column("subject", sa.Text(), nullable=True),
            sa.Column("from_addr", sa.VARCHAR(length=255), nullable=True),
            sa.Column("to_addr", sa.VARCHAR(length=255), nullable=False),
            sa.Column("date", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column(
                "status",
                sa.VARCHAR(length=50),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column(
                "history",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'::json"),
            ),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email_id"),
        )
        op.create_index(op.f("ix_emails_id"), "emails", ["id"], unique=False)
        op.create_index(op.f("ix_emails_email_id"), "emails", ["email_id"], unique=True)
        op.create_index(op.f("ix_emails_thread_id"), "emails", ["thread_id"], unique=False)
    else:
        # Existing DB: add missing history column.
        cols = {c["name"] for c in inspector.get_columns("emails")}
        if "history" not in cols:
            op.add_column(
                "emails",
                sa.Column(
                    "history",
                    sa.JSON(),
                    nullable=False,
                    server_default=sa.text("'[]'::json"),
                ),
            )
            op.alter_column("emails", "history", server_default=None)

    if not inspector.has_table("replies"):
        op.create_table(
            "replies",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("email_id", sa.VARCHAR(length=255), nullable=False),
            sa.Column("thread_id", sa.VARCHAR(length=255), nullable=True),
            sa.Column("from_addr", sa.VARCHAR(length=255), nullable=True),
            sa.Column("to_addr", sa.VARCHAR(length=255), nullable=True),
            sa.Column("subject", sa.Text(), nullable=True),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("intent_label", sa.VARCHAR(length=255), nullable=True),
            sa.Column("profile_type", sa.VARCHAR(length=100), nullable=True),
            sa.Column("sender_name", sa.VARCHAR(length=255), nullable=True),
            sa.Column("detected_intents", sa.JSON(), nullable=True),
            sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_replies_id"), "replies", ["id"], unique=False)
        op.create_index(op.f("ix_replies_email_id"), "replies", ["email_id"], unique=False)

    if not inspector.has_table("logs"):
        op.create_table(
            "logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("email_id", sa.VARCHAR(length=255), nullable=False),
            sa.Column("subject", sa.Text(), nullable=True),
            sa.Column("from_addr", sa.VARCHAR(length=255), nullable=True),
            sa.Column("to_addr", sa.VARCHAR(length=255), nullable=True),
            sa.Column("intent_id", sa.Integer(), nullable=True),
            sa.Column("intent_label", sa.VARCHAR(length=255), nullable=True),
            sa.Column("profile_type", sa.VARCHAR(length=100), nullable=True),
            sa.Column("is_relevant", sa.Boolean(), nullable=True),
            sa.Column("status", sa.VARCHAR(length=50), nullable=True),
            sa.Column("sent", sa.Boolean(), nullable=True),
            sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column(
                "payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'::json"),
            ),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_logs_email_id"), "logs", ["email_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("logs"):
        op.drop_index(op.f("ix_logs_email_id"), table_name="logs")
        op.drop_table("logs")

    if inspector.has_table("replies"):
        op.drop_index(op.f("ix_replies_email_id"), table_name="replies")
        op.drop_index(op.f("ix_replies_id"), table_name="replies")
        op.drop_table("replies")

    if inspector.has_table("emails"):
        cols = {c["name"] for c in inspector.get_columns("emails")}
        if "history" in cols:
            op.drop_column("emails", "history")
