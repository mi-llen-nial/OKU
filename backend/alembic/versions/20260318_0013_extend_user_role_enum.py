"""Extend user role enum for institutional RBAC.

Revision ID: 20260318_0013
Revises: 20260317_0012
Create Date: 2026-03-18 12:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260318_0013"
down_revision: Union[str, None] = "20260317_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for value in ("methodist", "institution_admin", "superadmin"):
        bind.execute(sa.text(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{value}'"))


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place.
    pass

