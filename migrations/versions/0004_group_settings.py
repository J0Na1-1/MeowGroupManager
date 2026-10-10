from alembic import op
import sqlalchemy as sa

revision = "0004_group_settings"
down_revision = "0003_managed_groups"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("managed_groups", sa.Column("verification_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("managed_groups", sa.Column("cleanup_mode", sa.String(32), nullable=False, server_default="dry_run"))

def downgrade() -> None:
    op.drop_column("managed_groups", "cleanup_mode")
    op.drop_column("managed_groups", "verification_enabled")
