"""Add Fibonacci pivots, CPR, PDH, PDL columns to indicator_data

Revision ID: 20241203_001
Revises: 20241128_001
Create Date: 2024-12-03

Adds:
- Previous Day High/Low (PDH, PDL)
- Central Pivot Range (CPR): TC, Pivot, BC
- Fibonacci Pivot Points: R1, R2, R3, S1, S2, S3
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20241203_001'
down_revision = '20241128_001'
branch_labels = None
depends_on = None


def upgrade():
    # Add Previous Day High/Low
    op.add_column('indicator_data', sa.Column('pdh', sa.Numeric(12, 4), comment='Previous Day High'))
    op.add_column('indicator_data', sa.Column('pdl', sa.Numeric(12, 4), comment='Previous Day Low'))
    op.add_column('indicator_data', sa.Column('pdc', sa.Numeric(12, 4), comment='Previous Day Close'))
    
    # Add Central Pivot Range (CPR)
    op.add_column('indicator_data', sa.Column('cpr_tc', sa.Numeric(12, 4), comment='CPR Top Central'))
    op.add_column('indicator_data', sa.Column('cpr_pivot', sa.Numeric(12, 4), comment='CPR Central Pivot'))
    op.add_column('indicator_data', sa.Column('cpr_bc', sa.Numeric(12, 4), comment='CPR Bottom Central'))
    op.add_column('indicator_data', sa.Column('cpr_width', sa.Numeric(8, 4), comment='CPR Width %'))
    
    # Add Fibonacci Pivot Points
    op.add_column('indicator_data', sa.Column('fib_r1', sa.Numeric(12, 4), comment='Fibonacci R1 (38.2%)'))
    op.add_column('indicator_data', sa.Column('fib_r2', sa.Numeric(12, 4), comment='Fibonacci R2 (61.8%)'))
    op.add_column('indicator_data', sa.Column('fib_r3', sa.Numeric(12, 4), comment='Fibonacci R3 (100%)'))
    op.add_column('indicator_data', sa.Column('fib_s1', sa.Numeric(12, 4), comment='Fibonacci S1 (38.2%)'))
    op.add_column('indicator_data', sa.Column('fib_s2', sa.Numeric(12, 4), comment='Fibonacci S2 (61.8%)'))
    op.add_column('indicator_data', sa.Column('fib_s3', sa.Numeric(12, 4), comment='Fibonacci S3 (100%)'))


def downgrade():
    # Remove Fibonacci Pivot Points
    op.drop_column('indicator_data', 'fib_s3')
    op.drop_column('indicator_data', 'fib_s2')
    op.drop_column('indicator_data', 'fib_s1')
    op.drop_column('indicator_data', 'fib_r3')
    op.drop_column('indicator_data', 'fib_r2')
    op.drop_column('indicator_data', 'fib_r1')
    
    # Remove CPR
    op.drop_column('indicator_data', 'cpr_width')
    op.drop_column('indicator_data', 'cpr_bc')
    op.drop_column('indicator_data', 'cpr_pivot')
    op.drop_column('indicator_data', 'cpr_tc')
    
    # Remove PDH/PDL
    op.drop_column('indicator_data', 'pdc')
    op.drop_column('indicator_data', 'pdl')
    op.drop_column('indicator_data', 'pdh')
