"""Record which Clerk user a profile belongs to

Clerk owns identity; this database owns persistence. The internal `id` is
derived from the Clerk subject (UUIDv5), so the mapping already exists
implicitly — this column makes it inspectable, and its unique constraint makes
it impossible for one Clerk user to acquire two profiles even under a race.

Nullable, because rows created before Clerk (local development, legacy Supabase
Auth) are still valid and must not be destroyed.

Revision ID: 21593fe33ec1
Revises: f7a2c94db31e
Create Date: 2026-08-17 20:32:17.014166
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.types  # noqa: F401  (registers custom column types)


revision: str = '21593fe33ec1'
down_revision: str | None = 'f7a2c94db31e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('clerk_user_id', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_profiles_clerk_user_id'), ['clerk_user_id'], unique=True)



def downgrade() -> None:
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profiles_clerk_user_id'))
        batch_op.drop_column('clerk_user_id')

