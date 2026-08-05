"""add ficha tecnica and document urls to drugs

Revision ID: 7862d9ea1d65
Revises: 272aeb551e68
Create Date: 2026-08-05 17:30:06.080810

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7862d9ea1d65"
down_revision: str | Sequence[str] | None = "272aeb551e68"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Renombrado, no drop+add: `documento_html` siempre almacenó el prospecto, nunca la
    # ficha técnica (que no se obtenía todavía) — autogenerate lo detecta como columna
    # eliminada + `prospecto_html` nueva, lo que perdería el contenido ya cacheado de los
    # fármacos indexados hasta ahora. `alter_column` preserva los datos existentes.
    op.alter_column("drugs", "documento_html", new_column_name="prospecto_html")
    op.add_column("drugs", sa.Column("ficha_tecnica_html", sa.String(), nullable=True))
    op.add_column("drugs", sa.Column("prospecto_url", sa.String(), nullable=True))
    op.add_column("drugs", sa.Column("ficha_tecnica_url", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("drugs", "ficha_tecnica_url")
    op.drop_column("drugs", "prospecto_url")
    op.drop_column("drugs", "ficha_tecnica_html")
    op.alter_column("drugs", "prospecto_html", new_column_name="documento_html")
