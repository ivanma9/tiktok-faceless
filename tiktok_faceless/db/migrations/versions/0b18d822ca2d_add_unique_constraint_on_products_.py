"""add unique constraint on products account_id product_id

Revision ID: 0b18d822ca2d
Revises: c43d77205a57
Create Date: 2026-03-11 21:28:04.166336

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0b18d822ca2d"
down_revision: Union[str, None] = "c43d77205a57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode for constraint changes (copy-and-move strategy)
    with op.batch_alter_table("products") as batch_op:
        batch_op.create_unique_constraint(
            "uq_product_account_product", ["account_id", "product_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint("uq_product_account_product", type_="unique")
