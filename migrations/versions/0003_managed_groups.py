from alembic import op
import sqlalchemy as sa

revision = "0003_managed_groups"
down_revision = "0002_admin_configs"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "managed_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("added_by", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_managed_groups_chat_id", "managed_groups", ["chat_id"])

def downgrade() -> None:
    op.drop_index("ix_managed_groups_chat_id", table_name="managed_groups")
    op.drop_table("managed_groups")
