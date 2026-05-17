"""Initial schema — all 15 tables

Revision ID: 001
Revises:
Create Date: 2026-05-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── plans ──────────────────────────────────────────────────────
    op.create_table(
        'plans',
        sa.Column('id',           sa.Integer(),     primary_key=True),
        sa.Column('name',         sa.String(50),    nullable=False, unique=True),
        sa.Column('display_name', sa.String(100)),
        sa.Column('price_kes',    sa.Integer(),     server_default='0'),
        sa.Column('price_usd',    sa.Integer(),     server_default='0'),
        sa.Column('max_users',    sa.Integer(),     server_default='50'),
        sa.Column('otp_channels', sa.Text(),        server_default='["email"]'),
        sa.Column('features',     sa.Text(),        server_default='["basic_dashboard"]'),
        sa.Column('sms_enabled',  sa.Boolean(),     server_default='false'),
        sa.Column('sms_cost_min', sa.Integer(),     server_default='0'),
        sa.Column('sms_cost_max', sa.Integer(),     server_default='0'),
        sa.Column('is_active',    sa.Boolean(),     server_default='true'),
        sa.Column('created_at',   sa.DateTime(),    server_default=sa.text('NOW()')),
    )

    # ── users ──────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id',            sa.Integer(),    primary_key=True),
        sa.Column('email',         sa.String(255),  nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255),  nullable=False),
        sa.Column('full_name',     sa.String(120)),
        sa.Column('phone',         sa.String(20)),
        sa.Column('role',          sa.String(20),   server_default='user'),
        sa.Column('plan',          sa.String(20),   server_default='starter'),
        sa.Column('mfa_enabled',   sa.Boolean(),    server_default='false'),
        sa.Column('mfa_secret',    sa.String(64)),
        sa.Column('mfa_method',    sa.String(20),   server_default='email'),
        sa.Column('is_active',     sa.Boolean(),    server_default='true'),
        sa.Column('created_at',    sa.DateTime(),   server_default=sa.text('NOW()')),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # ── api_keys ───────────────────────────────────────────────────
    op.create_table(
        'api_keys',
        sa.Column('id',         sa.Integer(),   primary_key=True),
        sa.Column('user_id',    sa.Integer(),   sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',       sa.String(100), nullable=False),
        sa.Column('key',        sa.String(64),  nullable=False, unique=True),
        sa.Column('is_active',  sa.Boolean(),   server_default='true'),
        sa.Column('last_used',  sa.DateTime()),
        sa.Column('created_at', sa.DateTime(),  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_api_keys_user_id', 'api_keys', ['user_id'])
    op.create_index('ix_api_keys_key',     'api_keys', ['key'])

    # ── otp_logs ───────────────────────────────────────────────────
    op.create_table(
        'otp_logs',
        sa.Column('id',         sa.Integer(),  primary_key=True),
        sa.Column('user_id',    sa.Integer(),  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('api_key_id', sa.Integer(),  sa.ForeignKey('api_keys.id', ondelete='SET NULL'), nullable=True),
        sa.Column('code',       sa.String(10), nullable=False),
        sa.Column('method',     sa.String(20)),
        sa.Column('status',     sa.String(20), server_default='pending'),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('timestamp',  sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime()),
    )
    op.create_index('ix_otp_logs_user_id',   'otp_logs', ['user_id'])
    op.create_index('ix_otp_logs_timestamp', 'otp_logs', ['timestamp'])

    # ── devices ────────────────────────────────────────────────────
    op.create_table(
        'devices',
        sa.Column('id',         sa.Integer(),   primary_key=True),
        sa.Column('user_id',    sa.Integer(),   sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ip',         sa.String(45)),
        sa.Column('location',   sa.String(120)),
        sa.Column('user_agent', sa.String(255)),
        sa.Column('trusted',    sa.Boolean(),   server_default='false'),
        sa.Column('last_seen',  sa.DateTime(),  server_default=sa.text('NOW()')),
        sa.Column('created_at', sa.DateTime(),  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_devices_user_id', 'devices', ['user_id'])

    # ── subscriptions ──────────────────────────────────────────────
    op.create_table(
        'subscriptions',
        sa.Column('id',         sa.Integer(),  primary_key=True),
        sa.Column('user_id',    sa.Integer(),  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan_id',    sa.Integer(),  sa.ForeignKey('plans.id'), nullable=False),
        sa.Column('status',     sa.String(20), server_default='active'),
        sa.Column('is_trial',   sa.Boolean(),  server_default='false'),
        sa.Column('trial_ends', sa.DateTime()),
        sa.Column('start_date', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('end_date',   sa.DateTime()),
        sa.Column('auto_renew', sa.Boolean(),  server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_subscriptions_user_id', 'subscriptions', ['user_id'])

    # ── usage_logs ─────────────────────────────────────────────────
    op.create_table(
        'usage_logs',
        sa.Column('id',         sa.Integer(),  primary_key=True),
        sa.Column('user_id',    sa.Integer(),  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('usage_type', sa.String(50)),
        sa.Column('quantity',   sa.Integer(),  server_default='1'),
        sa.Column('cost_kes',   sa.Integer(),  server_default='0'),
        sa.Column('extra_data', sa.Text(),     server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_usage_logs_user_id', 'usage_logs', ['user_id'])

    # ── usage_summaries ────────────────────────────────────────────
    op.create_table(
        'usage_summaries',
        sa.Column('id',              sa.Integer(),  primary_key=True),
        sa.Column('user_id',         sa.Integer(),  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('month',           sa.String(7)),
        sa.Column('email_otp_count', sa.Integer(),  server_default='0'),
        sa.Column('sms_otp_count',   sa.Integer(),  server_default='0'),
        sa.Column('totp_count',      sa.Integer(),  server_default='0'),
        sa.Column('total_users',     sa.Integer(),  server_default='0'),
        sa.Column('total_cost_kes',  sa.Integer(),  server_default='0'),
        sa.Column('updated_at',      sa.DateTime(), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_usage_summaries_user_id', 'usage_summaries', ['user_id'])

    # ── contact_messages ───────────────────────────────────────────
    op.create_table(
        'contact_messages',
        sa.Column('id',         sa.Integer(),   primary_key=True),
        sa.Column('name',       sa.String(120), nullable=False),
        sa.Column('email',      sa.String(255), nullable=False),
        sa.Column('subject',    sa.String(200), nullable=False),
        sa.Column('message',    sa.Text(),      nullable=False),
        sa.Column('is_read',    sa.Boolean(),   server_default='false'),
        sa.Column('created_at', sa.DateTime(),  server_default=sa.text('NOW()')),
    )

    # ── support_tickets ────────────────────────────────────────────
    op.create_table(
        'support_tickets',
        sa.Column('id',                  sa.Integer(),  primary_key=True),
        sa.Column('ticket_number',       sa.String(20), nullable=False, unique=True),
        sa.Column('user_id',             sa.Integer(),  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('guest_name',          sa.String(120)),
        sa.Column('guest_email',         sa.String(255)),
        sa.Column('subject',             sa.String(200), nullable=False),
        sa.Column('category',            sa.String(50),  server_default='general'),
        sa.Column('priority',            sa.String(20),  server_default='medium'),
        sa.Column('status',              sa.String(20),  server_default='open'),
        sa.Column('assigned_to_id',      sa.Integer(),   sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('first_response_at',   sa.DateTime()),
        sa.Column('resolved_at',         sa.DateTime()),
        sa.Column('satisfaction_rating', sa.Integer()),
        sa.Column('created_at',          sa.DateTime(),  server_default=sa.text('NOW()')),
        sa.Column('updated_at',          sa.DateTime(),  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_support_tickets_ticket_number', 'support_tickets', ['ticket_number'])
    op.create_index('ix_support_tickets_user_id',       'support_tickets', ['user_id'])
    op.create_index('ix_support_tickets_status',        'support_tickets', ['status'])
    op.create_index('ix_support_tickets_created_at',    'support_tickets', ['created_at'])

    # ── ticket_messages ────────────────────────────────────────────
    op.create_table(
        'ticket_messages',
        sa.Column('id',          sa.Integer(),   primary_key=True),
        sa.Column('ticket_id',   sa.Integer(),   sa.ForeignKey('support_tickets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_type', sa.String(20),  nullable=False),
        sa.Column('sender_id',   sa.Integer(),   sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sender_name', sa.String(120)),
        sa.Column('message',     sa.Text(),      nullable=False),
        sa.Column('is_internal', sa.Boolean(),   server_default='false'),
        sa.Column('created_at',  sa.DateTime(),  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_ticket_messages_ticket_id', 'ticket_messages', ['ticket_id'])

    # ── kb_categories ──────────────────────────────────────────────
    op.create_table(
        'kb_categories',
        sa.Column('id',          sa.Integer(),   primary_key=True),
        sa.Column('name',        sa.String(100), nullable=False),
        sa.Column('slug',        sa.String(100), nullable=False, unique=True),
        sa.Column('icon',        sa.String(50),  server_default='📚'),
        sa.Column('description', sa.String(300)),
        sa.Column('sort_order',  sa.Integer(),   server_default='0'),
        sa.Column('created_at',  sa.DateTime(),  server_default=sa.text('NOW()')),
    )

    # ── kb_articles ────────────────────────────────────────────────
    op.create_table(
        'kb_articles',
        sa.Column('id',                sa.Integer(),   primary_key=True),
        sa.Column('category_id',       sa.Integer(),   sa.ForeignKey('kb_categories.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title',             sa.String(200), nullable=False),
        sa.Column('slug',              sa.String(200), nullable=False, unique=True),
        sa.Column('content',           sa.Text(),      nullable=False),
        sa.Column('excerpt',           sa.String(400)),
        sa.Column('tags',              sa.Text(),      server_default='[]'),
        sa.Column('is_published',      sa.Boolean(),   server_default='true'),
        sa.Column('is_featured',       sa.Boolean(),   server_default='false'),
        sa.Column('helpful_count',     sa.Integer(),   server_default='0'),
        sa.Column('not_helpful_count', sa.Integer(),   server_default='0'),
        sa.Column('view_count',        sa.Integer(),   server_default='0'),
        sa.Column('created_at',        sa.DateTime(),  server_default=sa.text('NOW()')),
        sa.Column('updated_at',        sa.DateTime(),  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_kb_articles_category_id', 'kb_articles', ['category_id'])

    # ── forum_posts ────────────────────────────────────────────────
    op.create_table(
        'forum_posts',
        sa.Column('id',           sa.Integer(),   primary_key=True),
        sa.Column('user_id',      sa.Integer(),   sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('author_name',  sa.String(120), nullable=False),
        sa.Column('author_email', sa.String(255)),
        sa.Column('title',        sa.String(300), nullable=False),
        sa.Column('body',         sa.Text(),      nullable=False),
        sa.Column('category',     sa.String(50),  server_default='general'),
        sa.Column('tags',         sa.Text(),      server_default='[]'),
        sa.Column('upvotes',      sa.Integer(),   server_default='0'),
        sa.Column('views',        sa.Integer(),   server_default='0'),
        sa.Column('is_pinned',    sa.Boolean(),   server_default='false'),
        sa.Column('is_answered',  sa.Boolean(),   server_default='false'),
        sa.Column('created_at',   sa.DateTime(),  server_default=sa.text('NOW()')),
        sa.Column('updated_at',   sa.DateTime(),  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_forum_posts_created_at', 'forum_posts', ['created_at'])

    # ── forum_replies ──────────────────────────────────────────────
    op.create_table(
        'forum_replies',
        sa.Column('id',          sa.Integer(),   primary_key=True),
        sa.Column('post_id',     sa.Integer(),   sa.ForeignKey('forum_posts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id',     sa.Integer(),   sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('author_name', sa.String(120), nullable=False),
        sa.Column('body',        sa.Text(),      nullable=False),
        sa.Column('upvotes',     sa.Integer(),   server_default='0'),
        sa.Column('is_accepted', sa.Boolean(),   server_default='false'),
        sa.Column('created_at',  sa.DateTime(),  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_forum_replies_post_id', 'forum_replies', ['post_id'])


def downgrade() -> None:
    op.drop_table('forum_replies')
    op.drop_table('forum_posts')
    op.drop_table('kb_articles')
    op.drop_table('kb_categories')
    op.drop_table('ticket_messages')
    op.drop_table('support_tickets')
    op.drop_table('contact_messages')
    op.drop_table('usage_summaries')
    op.drop_table('usage_logs')
    op.drop_table('subscriptions')
    op.drop_table('devices')
    op.drop_table('otp_logs')
    op.drop_table('api_keys')
    op.drop_table('users')
    op.drop_table('plans')
