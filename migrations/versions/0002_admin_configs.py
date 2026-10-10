from alembic import op
import sqlalchemy as sa
revision = "0002_admin_configs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "admin_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_configs_chat_id", "admin_configs", ["chat_id"])

def downgrade() -> None:
    op.drop_index("ix_admin_configs_chat_id", table_name="admin_configs")
    op.drop_table("admin_configs")
