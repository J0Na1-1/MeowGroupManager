from alembic import op
import sqlalchemy as sa

revision = "0005_members_verification"
down_revision = "0004_group_settings"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("verifications", sa.Column("chat_id", sa.BigInteger(), nullable=False, server_default="0"))
    op.alter_column("verifications", "telegram_user_id", type_=sa.BigInteger(), existing_type=sa.Integer())
    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=False, server_default=""),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_group_members_chat_id", "group_members", ["chat_id"])
    op.create_index("ix_group_members_telegram_user_id", "group_members", ["telegram_user_id"])

def downgrade() -> None:
    op.drop_index("ix_group_members_telegram_user_id", table_name="group_members")
    op.drop_index("ix_group_members_chat_id", table_name="group_members")
    op.drop_table("group_members")
    op.drop_column("verifications", "chat_id")
