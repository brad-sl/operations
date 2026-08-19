"""registry_tables_for_multi_tenant_t0

Revision ID: 002
Revises: 001
Create Date: 2026-07-16

Add traders, trader_configs, oauth_tokens, job_runs for SCALING-1000 T0-01
Postgres canonical registry. Encrypted tokens. Isolation by trader_id / portfolio_uuid.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # traders table (multi-tenant account registry)
    op.create_table(
        'traders',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ghl_contact_id', sa.String(length=100), nullable=True),
        sa.Column('ghl_location_id', sa.String(length=100), nullable=True),
        sa.Column('portfolio_uuid', sa.String(length=100), nullable=True),
        sa.Column('coinbase_account_id', sa.String(length=100), nullable=True),
        sa.Column('tier', sa.Enum('starter', 'pro', 'elite', name='tier_enum'), nullable=False, server_default='starter'),
        sa.Column('billing_status', sa.Enum('active', 'past_due', 'canceled', 'trialing', 'none', name='billing_status_enum'), nullable=False, server_default='none'),
        sa.Column('coinbase_status', sa.Enum('disconnected', 'connected', 'error', 'revoked', name='coinbase_status_enum'), nullable=False, server_default='disconnected'),
        sa.Column('auth_mode', sa.Enum('oauth', 'api_key', name='auth_mode_enum'), nullable=False, server_default='oauth'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_cycle_at', sa.DateTime(), nullable=True),
        sa.Column('last_rebalance_at', sa.DateTime(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('flags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ghl_contact_id'),
        sa.UniqueConstraint('portfolio_uuid'),
        sa.UniqueConstraint('coinbase_account_id'),
    )
    op.create_index('ix_traders_ghl_contact_id', 'traders', ['ghl_contact_id'])
    op.create_index('ix_traders_portfolio_uuid', 'traders', ['portfolio_uuid'])

    # trader_configs
    op.create_table(
        'trader_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('trader_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pairs', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('risk_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('allocation_overrides', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rebalance_frequency', sa.String(length=20), nullable=True, server_default='daily'),
        sa.Column('max_deploy_usd', sa.Float(), nullable=True),
        sa.Column('pair_count_cap', sa.Integer(), nullable=True, server_default='6'),
        sa.Column('tier_template_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('overrides', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['trader_id'], ['traders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trader_id'),
    )

    # oauth_tokens (encrypted at rest)
    op.create_table(
        'oauth_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('trader_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('access_token_enc', sa.Text(), nullable=False),
        sa.Column('refresh_token_enc', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('portfolio_uuid', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['trader_id'], ['traders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trader_id'),
    )
    op.create_index('ix_oauth_tokens_trader_id', 'oauth_tokens', ['trader_id'])

    # job_runs
    op.create_table(
        'job_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('trader_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('run_id', sa.String(length=100), nullable=False),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.Enum('pending', 'running', 'success', 'failed', 'cancelled', name='job_status_enum'), nullable=False, server_default='pending'),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_summary', sa.Text(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['trader_id'], ['traders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_job_runs_trader_id', 'job_runs', ['trader_id'])
    op.create_index('ix_job_runs_run_id', 'job_runs', ['run_id'])
    op.create_index('ix_job_runs_started_at', 'job_runs', ['started_at'])


def downgrade():
    op.drop_index('ix_job_runs_started_at', table_name='job_runs')
    op.drop_index('ix_job_runs_run_id', table_name='job_runs')
    op.drop_index('ix_job_runs_trader_id', table_name='job_runs')
    op.drop_table('job_runs')

    op.drop_index('ix_oauth_tokens_trader_id', table_name='oauth_tokens')
    op.drop_table('oauth_tokens')

    op.drop_table('trader_configs')

    op.drop_index('ix_traders_portfolio_uuid', table_name='traders')
    op.drop_index('ix_traders_ghl_contact_id', table_name='traders')
    op.drop_table('traders')

    # Enums are dropped implicitly or explicitly if needed
    # op.execute("DROP TYPE IF EXISTS tier_enum")
    # etc. but alembic usually handles
