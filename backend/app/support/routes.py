"""
app/support/routes.py
Customer Support System — tickets, knowledge base, admin management
"""
import re
import json
import secrets
import logging
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    jwt_required, get_jwt_identity, verify_jwt_in_request
)
from sqlalchemy import func, or_

from app.extensions import db
from app.models import (
    User, SupportTicket, TicketMessage,
    KnowledgeBaseCategory, KnowledgeBaseArticle,
    ForumPost, ForumReply,
)

support_bp = Blueprint('support', __name__)
logger = logging.getLogger(__name__)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user = User.query.get(int(get_jwt_identity()))
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return fn(*args, **kwargs)
    return wrapper


def get_optional_user():
    try:
        verify_jwt_in_request(optional=True)
        uid = get_jwt_identity()
        return User.query.get(int(uid)) if uid else None
    except Exception:
        return None


# ── Utilities ─────────────────────────────────────────────────────────────────

def _generate_ticket_number():
    return 'TKT-' + secrets.token_hex(4).upper()


def _search_kb(query: str, limit: int = 3):
    """Keyword relevance search across KB articles."""
    if not query:
        return []
    words = [w.lower() for w in re.findall(r'\w{3,}', query)]
    if not words:
        return []
    results = []
    for article in KnowledgeBaseArticle.query.filter_by(is_published=True).all():
        corpus = (
            (article.title or '') + ' ' +
            (article.content or '') + ' ' +
            ' '.join(article.get_tags())
        ).lower()
        score = sum(corpus.count(w) for w in words)
        if score > 0:
            results.append((score, article))
    results.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in results[:limit]]


def _ticket_confirmation_html(ticket, name, suggestions):
    sug_html = ''
    if suggestions:
        items = ''.join(f'<li style="margin:4px 0">{a.title}</li>' for a in suggestions)
        sug_html = f'''
        <div style="margin-top:20px">
          <p style="font-weight:600;color:#1a202c">While you wait, these articles might help:</p>
          <ul style="color:#4a5568;padding-left:20px">{items}</ul>
        </div>'''

    return f'''
    <div style="font-family:sans-serif;max-width:560px;padding:32px;background:#f7fafc;border-radius:12px">
      <div style="text-align:center;margin-bottom:28px">
        <div style="font-size:.8rem;letter-spacing:2px;color:#718096;text-transform:uppercase;margin-bottom:8px">OTPGuard Support</div>
        <h2 style="color:#1a202c;margin:0">Ticket Received</h2>
        <div style="display:inline-block;background:#0a0e1a;color:#00ff88;font-family:monospace;font-size:1.4rem;font-weight:800;padding:8px 20px;border-radius:8px;margin-top:12px">#{ticket.ticket_number}</div>
      </div>
      <p>Hi <strong>{name}</strong>,</p>
      <p>We've received your request. Our support team will respond shortly.</p>
      <table style="width:100%;background:#fff;border-radius:8px;padding:16px;border-collapse:collapse;margin:16px 0">
        <tr><td style="padding:6px 10px;color:#718096;font-size:.9rem">Subject</td>
            <td style="padding:6px 10px;font-weight:600;color:#1a202c">{ticket.subject}</td></tr>
        <tr><td style="padding:6px 10px;color:#718096;font-size:.9rem">Category</td>
            <td style="padding:6px 10px;text-transform:capitalize">{ticket.category}</td></tr>
        <tr><td style="padding:6px 10px;color:#718096;font-size:.9rem">Priority</td>
            <td style="padding:6px 10px;text-transform:capitalize">{ticket.priority}</td></tr>
        <tr><td style="padding:6px 10px;color:#718096;font-size:.9rem">Status</td>
            <td style="padding:6px 10px;color:#00b860;font-weight:700">Open</td></tr>
      </table>
      {sug_html}
      <p style="margin-top:20px;font-size:.85rem;color:#718096">Reply to this email or visit our support center to update your ticket.</p>
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0"/>
      <p style="font-size:.75rem;color:#a0aec0">OTPGuard Support Team · otpguard.co.ke</p>
    </div>'''


# ══════════════════════════════════════════════════════════════════════════════
#  KNOWLEDGE BASE  (public)
# ══════════════════════════════════════════════════════════════════════════════

@support_bp.route('/kb/categories', methods=['GET'])
def kb_categories():
    cats = KnowledgeBaseCategory.query.order_by(KnowledgeBaseCategory.sort_order).all()
    return jsonify({'categories': [c.to_dict() for c in cats]}), 200


@support_bp.route('/kb/articles', methods=['GET'])
def kb_articles():
    search   = request.args.get('search', '').strip()
    cat_id   = request.args.get('category_id', type=int)
    featured = request.args.get('featured', '').lower() == 'true'
    page     = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 12, type=int), 50)

    q = KnowledgeBaseArticle.query.filter_by(is_published=True)
    if cat_id:
        q = q.filter_by(category_id=cat_id)
    if featured:
        q = q.filter_by(is_featured=True)
    if search:
        q = q.filter(or_(
            KnowledgeBaseArticle.title.ilike(f'%{search}%'),
            KnowledgeBaseArticle.content.ilike(f'%{search}%'),
            KnowledgeBaseArticle.tags.ilike(f'%{search}%'),
        ))

    paginated = q.order_by(
        KnowledgeBaseArticle.is_featured.desc(),
        KnowledgeBaseArticle.view_count.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'articles': [a.to_dict() for a in paginated.items],
        'total':    paginated.total,
        'pages':    paginated.pages,
    }), 200


@support_bp.route('/kb/articles/<slug>', methods=['GET'])
def kb_article(slug):
    article = KnowledgeBaseArticle.query.filter_by(slug=slug, is_published=True).first_or_404()
    article.view_count = (article.view_count or 0) + 1
    db.session.commit()
    return jsonify({'article': article.to_dict(full=True)}), 200


@support_bp.route('/kb/articles/<int:article_id>/vote', methods=['POST'])
def kb_vote(article_id):
    article = KnowledgeBaseArticle.query.get_or_404(article_id)
    data = request.get_json() or {}
    if data.get('helpful'):
        article.helpful_count = (article.helpful_count or 0) + 1
    else:
        article.not_helpful_count = (article.not_helpful_count or 0) + 1
    db.session.commit()
    return jsonify({'message': 'Vote recorded'}), 200


@support_bp.route('/kb/search', methods=['GET'])
def kb_search():
    query   = request.args.get('q', '').strip()
    results = _search_kb(query, limit=8)
    return jsonify({'results': [a.to_dict() for a in results], 'query': query}), 200


# ══════════════════════════════════════════════════════════════════════════════
#  TICKETS  (user-facing)
# ══════════════════════════════════════════════════════════════════════════════

@support_bp.route('/tickets', methods=['POST'])
def create_ticket():
    user = get_optional_user()
    data = request.get_json() or {}

    subject  = (data.get('subject') or '').strip()
    message  = (data.get('message') or '').strip()
    category = data.get('category', 'general')
    priority = data.get('priority', 'medium')
    name     = (data.get('name') or '').strip()
    email    = (data.get('email') or '').strip()

    if not subject or not message:
        return jsonify({'error': 'Subject and message are required'}), 400
    if len(message) > 5000:
        return jsonify({'error': 'Message too long (max 5000 chars)'}), 400

    if user:
        name  = name or user.full_name or user.email
        email = email or user.email
    elif not name or not email:
        return jsonify({'error': 'Name and email are required'}), 400

    # Unique ticket number
    for _ in range(10):
        number = _generate_ticket_number()
        if not SupportTicket.query.filter_by(ticket_number=number).first():
            break

    ticket = SupportTicket(
        ticket_number=number,
        user_id=user.id if user else None,
        guest_name=None if user else name,
        guest_email=None if user else email,
        subject=subject,
        category=category,
        priority=priority,
    )
    db.session.add(ticket)
    db.session.flush()

    # User's opening message
    db.session.add(TicketMessage(
        ticket_id=ticket.id,
        sender_type='user',
        sender_id=user.id if user else None,
        sender_name=name,
        message=message,
    ))

    # Auto-response with KB suggestions
    suggestions = _search_kb(f"{subject} {message}", limit=3)
    sug_text = ''
    if suggestions:
        titles = '\n'.join(f'• {a.title}' for a in suggestions)
        sug_text = f'\n\nWhile you wait, these articles might help:\n\n{titles}'

    db.session.add(TicketMessage(
        ticket_id=ticket.id,
        sender_type='system',
        sender_name='OTPGuard Support Bot',
        message=(
            f"Thanks for reaching out, {name}! We've received ticket #{number} "
            f"and our team will respond within 24 hours.{sug_text}"
        ),
    ))
    db.session.commit()

    # Confirmation email (non-blocking)
    try:
        from app.extensions import mail
        from flask_mail import Message as MailMsg
        mail.send(MailMsg(
            subject=f'[{number}] {subject}',
            recipients=[email],
            html=_ticket_confirmation_html(ticket, name, suggestions),
        ))
    except Exception as e:
        logger.warning(f'[SUPPORT] Confirmation email failed: {e}')

    return jsonify({
        'message':       'Ticket created successfully',
        'ticket_number': ticket.ticket_number,
        'ticket':        ticket.to_dict(include_messages=True),
    }), 201


@support_bp.route('/tickets', methods=['GET'])
@jwt_required()
def list_user_tickets():
    user_id = int(get_jwt_identity())
    page    = request.args.get('page', 1, type=int)
    status  = request.args.get('status')

    q = SupportTicket.query.filter_by(user_id=user_id)
    if status and status != 'all':
        q = q.filter_by(status=status)

    paginated = q.order_by(SupportTicket.updated_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return jsonify({'tickets': [t.to_dict() for t in paginated.items], 'total': paginated.total}), 200


@support_bp.route('/tickets/lookup', methods=['POST'])
def lookup_ticket():
    data          = request.get_json() or {}
    ticket_number = (data.get('ticket_number') or '').strip().upper()
    email         = (data.get('email') or '').strip().lower()

    if not ticket_number or not email:
        return jsonify({'error': 'Ticket number and email are required'}), 400

    ticket = SupportTicket.query.filter_by(ticket_number=ticket_number).first()
    if not ticket or (ticket.requester_email or '').lower() != email:
        return jsonify({'error': 'Ticket not found'}), 404

    return jsonify({'ticket': ticket.to_dict(include_messages=True)}), 200


@support_bp.route('/tickets/<int:ticket_id>', methods=['GET'])
@jwt_required()
def get_ticket(ticket_id):
    user_id = int(get_jwt_identity())
    ticket  = SupportTicket.query.get_or_404(ticket_id)
    if ticket.user_id != user_id:
        u = User.query.get(user_id)
        if not u or u.role != 'admin':
            return jsonify({'error': 'Access denied'}), 403
    return jsonify({'ticket': ticket.to_dict(include_messages=True)}), 200


@support_bp.route('/tickets/<int:ticket_id>/reply', methods=['POST'])
@jwt_required()
def reply_ticket(ticket_id):
    user_id = int(get_jwt_identity())
    ticket  = SupportTicket.query.get_or_404(ticket_id)
    if ticket.user_id != user_id:
        return jsonify({'error': 'Access denied'}), 403
    if ticket.status == 'closed':
        return jsonify({'error': 'Ticket is closed'}), 400

    data    = request.get_json() or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Message is required'}), 400

    user = User.query.get(user_id)
    msg  = TicketMessage(
        ticket_id=ticket_id,
        sender_type='user',
        sender_id=user_id,
        sender_name=user.full_name or user.email,
        message=message,
    )
    db.session.add(msg)
    if ticket.status in ('waiting', 'resolved'):
        ticket.status = 'in_progress'
    ticket.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'message': 'Reply sent', 'ticket_message': msg.to_dict()}), 201


@support_bp.route('/tickets/<int:ticket_id>/rate', methods=['POST'])
@jwt_required()
def rate_ticket(ticket_id):
    user_id = int(get_jwt_identity())
    ticket  = SupportTicket.query.get_or_404(ticket_id)
    if ticket.user_id != user_id:
        return jsonify({'error': 'Access denied'}), 403

    data   = request.get_json() or {}
    rating = data.get('rating')
    if not isinstance(rating, int) or not (1 <= rating <= 5):
        return jsonify({'error': 'Rating must be 1-5'}), 400

    ticket.satisfaction_rating = rating
    db.session.commit()
    return jsonify({'message': 'Rating saved'}), 200


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — TICKETS
# ══════════════════════════════════════════════════════════════════════════════

@support_bp.route('/admin/tickets', methods=['GET'])
@admin_required
def admin_list_tickets():
    page     = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    status   = request.args.get('status')
    priority = request.args.get('priority')
    category = request.args.get('category')
    search   = request.args.get('search', '').strip()

    q = SupportTicket.query
    if status and status != 'all':
        q = q.filter_by(status=status)
    if priority:
        q = q.filter_by(priority=priority)
    if category:
        q = q.filter_by(category=category)
    if search:
        q = q.filter(or_(
            SupportTicket.subject.ilike(f'%{search}%'),
            SupportTicket.ticket_number.ilike(f'%{search}%'),
            SupportTicket.guest_email.ilike(f'%{search}%'),
        ))

    paginated = q.order_by(SupportTicket.updated_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    stats = {
        'open':        SupportTicket.query.filter_by(status='open').count(),
        'in_progress': SupportTicket.query.filter_by(status='in_progress').count(),
        'waiting':     SupportTicket.query.filter_by(status='waiting').count(),
        'resolved':    SupportTicket.query.filter_by(status='resolved').count(),
        'closed':      SupportTicket.query.filter_by(status='closed').count(),
        'total':       SupportTicket.query.count(),
    }

    return jsonify({
        'tickets': [t.to_dict() for t in paginated.items],
        'total':   paginated.total,
        'pages':   paginated.pages,
        'page':    page,
        'stats':   stats,
    }), 200


@support_bp.route('/admin/tickets/<int:ticket_id>', methods=['GET'])
@admin_required
def admin_get_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    d = ticket.to_dict()
    d['messages'] = [m.to_dict() for m in ticket.messages]  # includes internal notes
    return jsonify({'ticket': d}), 200


@support_bp.route('/admin/tickets/<int:ticket_id>', methods=['PATCH'])
@admin_required
def admin_update_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    data   = request.get_json() or {}

    valid_statuses  = ('open', 'in_progress', 'waiting', 'resolved', 'closed')
    valid_priorities = ('low', 'medium', 'high', 'urgent')

    if 'status' in data and data['status'] in valid_statuses:
        ticket.status = data['status']
        if data['status'] == 'resolved' and not ticket.resolved_at:
            ticket.resolved_at = datetime.now(timezone.utc)
    if 'priority' in data and data['priority'] in valid_priorities:
        ticket.priority = data['priority']
    if 'assigned_to_id' in data:
        ticket.assigned_to_id = data['assigned_to_id']

    ticket.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'message': 'Ticket updated', 'ticket': ticket.to_dict()}), 200


@support_bp.route('/admin/tickets/<int:ticket_id>/reply', methods=['POST'])
@admin_required
def admin_reply_ticket(ticket_id):
    from flask_jwt_extended import get_jwt_identity as _gji
    admin  = User.query.get(int(_gji()))
    ticket = SupportTicket.query.get_or_404(ticket_id)
    data   = request.get_json() or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Message is required'}), 400

    msg = TicketMessage(
        ticket_id=ticket_id,
        sender_type='agent',
        sender_id=admin.id,
        sender_name=admin.full_name or admin.email,
        message=message,
    )
    db.session.add(msg)

    if not ticket.first_response_at:
        ticket.first_response_at = datetime.now(timezone.utc)
    if ticket.status == 'open':
        ticket.status = 'in_progress'
    ticket.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    # Notify the user by email
    try:
        from app.extensions import mail
        from flask_mail import Message as MailMsg
        recipient = ticket.requester_email
        if recipient:
            mail.send(MailMsg(
                subject=f'Re: [{ticket.ticket_number}] {ticket.subject}',
                recipients=[recipient],
                html=f'''<div style="font-family:sans-serif;max-width:560px">
                    <h3 style="color:#1a202c">New reply on your support ticket</h3>
                    <p><strong>Ticket:</strong> #{ticket.ticket_number} — {ticket.subject}</p>
                    <div style="background:#f7fafc;padding:16px;border-radius:8px;margin:16px 0;border-left:4px solid #00b860">
                        <p style="color:#2d3748">{message}</p>
                    </div>
                    <p style="color:#718096;font-size:.85rem">OTPGuard Support Team</p>
                </div>'''
            ))
    except Exception as e:
        logger.warning(f'[SUPPORT] Reply email failed: {e}')

    return jsonify({'message': 'Reply sent', 'ticket_message': msg.to_dict()}), 201


@support_bp.route('/admin/tickets/<int:ticket_id>/note', methods=['POST'])
@admin_required
def admin_add_note(ticket_id):
    from flask_jwt_extended import get_jwt_identity as _gji
    admin  = User.query.get(int(_gji()))
    ticket = SupportTicket.query.get_or_404(ticket_id)
    data   = request.get_json() or {}
    note   = (data.get('note') or '').strip()
    if not note:
        return jsonify({'error': 'Note is required'}), 400

    msg = TicketMessage(
        ticket_id=ticket_id,
        sender_type='agent',
        sender_id=admin.id,
        sender_name=admin.full_name or admin.email,
        message=note,
        is_internal=True,
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({'message': 'Note added', 'ticket_message': msg.to_dict()}), 201


# ── Admin analytics ───────────────────────────────────────────────────────────

@support_bp.route('/admin/analytics', methods=['GET'])
@admin_required
def admin_support_analytics():
    now   = datetime.now(timezone.utc)
    day30 = now - timedelta(days=30)

    total         = SupportTicket.query.count()
    open_count    = SupportTicket.query.filter_by(status='open').count()
    resolved_30d  = SupportTicket.query.filter(
        SupportTicket.resolved_at >= day30
    ).count()
    created_30d = SupportTicket.query.filter(
        SupportTicket.created_at >= day30
    ).count()

    # Average first response time
    responded = SupportTicket.query.filter(
        SupportTicket.first_response_at.isnot(None)
    ).all()
    avg_response_hrs = None
    if responded:
        hrs = sum(
            (t.first_response_at - t.created_at).total_seconds() / 3600
            for t in responded
        )
        avg_response_hrs = round(hrs / len(responded), 1)

    # CSAT
    rated = SupportTicket.query.filter(
        SupportTicket.satisfaction_rating.isnot(None)
    ).all()
    avg_satisfaction = round(sum(t.satisfaction_rating for t in rated) / len(rated), 1) if rated else None

    by_category = db.session.query(
        SupportTicket.category, func.count(SupportTicket.id)
    ).group_by(SupportTicket.category).all()

    by_priority = db.session.query(
        SupportTicket.priority, func.count(SupportTicket.id)
    ).group_by(SupportTicket.priority).all()

    # 7-day daily volume
    daily = []
    for i in range(6, -1, -1):
        ds = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        de = ds + timedelta(days=1)
        daily.append({
            'day':      ds.strftime('%a'),
            'created':  SupportTicket.query.filter(
                SupportTicket.created_at >= ds, SupportTicket.created_at < de
            ).count(),
            'resolved': SupportTicket.query.filter(
                SupportTicket.resolved_at >= ds, SupportTicket.resolved_at < de
            ).count(),
        })

    return jsonify({
        'total_tickets':    total,
        'open_tickets':     open_count,
        'resolved_30d':     resolved_30d,
        'created_30d':      created_30d,
        'avg_response_hrs': avg_response_hrs,
        'avg_satisfaction': avg_satisfaction,
        'by_category':      [{'category': c, 'count': n} for c, n in by_category],
        'by_priority':      [{'priority': p, 'count': n} for p, n in by_priority],
        'daily_volume':     daily,
        'kb_articles':      KnowledgeBaseArticle.query.filter_by(is_published=True).count(),
        'kb_categories':    KnowledgeBaseCategory.query.count(),
    }), 200


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — KNOWLEDGE BASE
# ══════════════════════════════════════════════════════════════════════════════

@support_bp.route('/admin/kb/categories', methods=['GET'])
@admin_required
def admin_kb_categories():
    cats = KnowledgeBaseCategory.query.order_by(KnowledgeBaseCategory.sort_order).all()
    return jsonify({'categories': [c.to_dict() for c in cats]}), 200


@support_bp.route('/admin/kb/categories', methods=['POST'])
@admin_required
def admin_create_category():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if KnowledgeBaseCategory.query.filter_by(slug=slug).first():
        return jsonify({'error': 'Category with this name already exists'}), 409

    cat = KnowledgeBaseCategory(
        name=name,
        slug=slug,
        icon=data.get('icon', '📚'),
        description=data.get('description', ''),
        sort_order=data.get('sort_order', 0),
    )
    db.session.add(cat)
    db.session.commit()
    return jsonify({'category': cat.to_dict()}), 201


@support_bp.route('/admin/kb/articles', methods=['GET'])
@admin_required
def admin_kb_articles():
    articles = KnowledgeBaseArticle.query.order_by(
        KnowledgeBaseArticle.created_at.desc()
    ).all()
    return jsonify({'articles': [a.to_dict(full=True) for a in articles]}), 200


@support_bp.route('/admin/kb/articles', methods=['POST'])
@admin_required
def admin_create_article():
    data    = request.get_json() or {}
    title   = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    if not title or not content:
        return jsonify({'error': 'Title and content are required'}), 400

    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    base, counter = slug, 1
    while KnowledgeBaseArticle.query.filter_by(slug=slug).first():
        slug = f'{base}-{counter}'
        counter += 1

    article = KnowledgeBaseArticle(
        title=title,
        slug=slug,
        content=content,
        excerpt=data.get('excerpt') or content[:200],
        category_id=data.get('category_id'),
        tags=json.dumps(data.get('tags', [])),
        is_published=bool(data.get('is_published', True)),
        is_featured=bool(data.get('is_featured', False)),
    )
    db.session.add(article)
    db.session.commit()
    return jsonify({'article': article.to_dict(full=True)}), 201


@support_bp.route('/admin/kb/articles/<int:article_id>', methods=['PUT'])
@admin_required
def admin_update_article(article_id):
    article = KnowledgeBaseArticle.query.get_or_404(article_id)
    data    = request.get_json() or {}

    if 'title'        in data: article.title        = data['title']
    if 'content'      in data: article.content      = data['content']
    if 'excerpt'      in data: article.excerpt      = data['excerpt']
    if 'category_id'  in data: article.category_id  = data['category_id']
    if 'tags'         in data: article.tags         = json.dumps(data['tags'])
    if 'is_published' in data: article.is_published = bool(data['is_published'])
    if 'is_featured'  in data: article.is_featured  = bool(data['is_featured'])
    article.updated_at = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify({'article': article.to_dict(full=True)}), 200


@support_bp.route('/admin/kb/articles/<int:article_id>', methods=['DELETE'])
@admin_required
def admin_delete_article(article_id):
    article = KnowledgeBaseArticle.query.get_or_404(article_id)
    db.session.delete(article)
    db.session.commit()
    return jsonify({'message': 'Article deleted'}), 200


# ══════════════════════════════════════════════════════════════════════════════
#  GUEST CHAT  (ticket-number + email auth, no JWT needed)
# ══════════════════════════════════════════════════════════════════════════════

@support_bp.route('/tickets/chat/<ticket_number>/messages', methods=['GET'])
def chat_poll(ticket_number):
    """Poll chat messages — authenticated by ticket_number + email."""
    email  = request.args.get('email', '').strip().lower()
    ticket = SupportTicket.query.filter_by(ticket_number=ticket_number.upper()).first()
    if not ticket or (ticket.requester_email or '').lower() != email:
        return jsonify({'error': 'Chat session not found'}), 404
    messages = [m.to_dict() for m in ticket.messages if not m.is_internal]
    return jsonify({'messages': messages, 'status': ticket.status, 'ticket_number': ticket.ticket_number}), 200


@support_bp.route('/tickets/chat/<ticket_number>/reply', methods=['POST'])
def chat_send(ticket_number):
    """Send a chat message — authenticated by ticket_number + email in body."""
    data    = request.get_json() or {}
    email   = (data.get('email') or '').strip().lower()
    message = (data.get('message') or '').strip()
    ticket  = SupportTicket.query.filter_by(ticket_number=ticket_number.upper()).first()
    if not ticket or (ticket.requester_email or '').lower() != email:
        return jsonify({'error': 'Chat session not found'}), 404
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    if ticket.status == 'closed':
        return jsonify({'error': 'This chat has been closed'}), 400

    msg = TicketMessage(
        ticket_id=ticket.id,
        sender_type='user',
        sender_name=ticket.requester_name,
        message=message,
    )
    db.session.add(msg)
    if ticket.status in ('waiting', 'resolved'):
        ticket.status = 'in_progress'
    ticket.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'message': 'Sent', 'ticket_message': msg.to_dict()}), 201


# ══════════════════════════════════════════════════════════════════════════════
#  COMMUNITY FORUM
# ══════════════════════════════════════════════════════════════════════════════

@support_bp.route('/forum/posts', methods=['GET'])
def forum_list():
    page     = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 50)
    category = request.args.get('category')
    search   = request.args.get('search', '').strip()
    sort     = request.args.get('sort', 'newest')  # newest | votes | unanswered

    q = ForumPost.query
    if category and category != 'all':
        q = q.filter_by(category=category)
    if search:
        q = q.filter(or_(
            ForumPost.title.ilike(f'%{search}%'),
            ForumPost.body.ilike(f'%{search}%'),
        ))
    if sort == 'votes':
        q = q.order_by(ForumPost.is_pinned.desc(), ForumPost.upvotes.desc())
    elif sort == 'unanswered':
        q = q.filter_by(is_answered=False).order_by(ForumPost.created_at.desc())
    else:
        q = q.order_by(ForumPost.is_pinned.desc(), ForumPost.created_at.desc())

    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'posts':  [p.to_dict() for p in paginated.items],
        'total':  paginated.total,
        'pages':  paginated.pages,
        'page':   page,
    }), 200


@support_bp.route('/forum/posts', methods=['POST'])
def forum_create():
    current_user = get_optional_user()
    data   = request.get_json() or {}
    title  = (data.get('title') or '').strip()
    body   = (data.get('body') or '').strip()
    name   = (data.get('author_name') or '').strip()
    email  = (data.get('author_email') or '').strip()

    if not title or not body:
        return jsonify({'error': 'Title and body are required'}), 400

    if current_user:
        name  = name or current_user.full_name or current_user.email
        email = email or current_user.email
    elif not name:
        return jsonify({'error': 'Name is required for guest posts'}), 400

    post = ForumPost(
        user_id=current_user.id if current_user else None,
        author_name=name,
        author_email=email,
        title=title,
        body=body,
        category=data.get('category', 'general'),
        tags=json.dumps(data.get('tags', [])),
    )
    db.session.add(post)
    db.session.commit()
    return jsonify({'post': post.to_dict()}), 201


@support_bp.route('/forum/posts/<int:post_id>', methods=['GET'])
def forum_get(post_id):
    post = ForumPost.query.get_or_404(post_id)
    post.views = (post.views or 0) + 1
    db.session.commit()
    return jsonify({'post': post.to_dict(include_replies=True)}), 200


@support_bp.route('/forum/posts/<int:post_id>/replies', methods=['POST'])
def forum_reply(post_id):
    current_user = get_optional_user()
    post = ForumPost.query.get_or_404(post_id)
    data = request.get_json() or {}
    body = (data.get('body') or '').strip()
    name = (data.get('author_name') or '').strip()

    if not body:
        return jsonify({'error': 'Reply body is required'}), 400

    if current_user:
        name = name or current_user.full_name or current_user.email
    elif not name:
        return jsonify({'error': 'Name is required'}), 400

    reply = ForumReply(
        post_id=post_id,
        user_id=current_user.id if current_user else None,
        author_name=name,
        body=body,
    )
    db.session.add(reply)
    post.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'reply': reply.to_dict()}), 201


@support_bp.route('/forum/posts/<int:post_id>/vote', methods=['POST'])
def forum_vote(post_id):
    post = ForumPost.query.get_or_404(post_id)
    post.upvotes = (post.upvotes or 0) + 1
    db.session.commit()
    return jsonify({'upvotes': post.upvotes}), 200


@support_bp.route('/forum/posts/<int:post_id>/replies/<int:reply_id>/vote', methods=['POST'])
def forum_reply_vote(post_id, reply_id):
    reply = ForumReply.query.filter_by(id=reply_id, post_id=post_id).first_or_404()
    reply.upvotes = (reply.upvotes or 0) + 1
    db.session.commit()
    return jsonify({'upvotes': reply.upvotes}), 200


@support_bp.route('/forum/posts/<int:post_id>/replies/<int:reply_id>/accept', methods=['POST'])
def forum_accept_reply(post_id, reply_id):
    current_user = get_optional_user()
    post  = ForumPost.query.get_or_404(post_id)
    reply = ForumReply.query.filter_by(id=reply_id, post_id=post_id).first_or_404()

    # Only original poster or admin can accept
    if current_user and (post.user_id == current_user.id or current_user.role == 'admin'):
        # Unaccept all other replies first
        for r in post.replies:
            r.is_accepted = False
        reply.is_accepted = True
        post.is_answered  = True
        db.session.commit()
        return jsonify({'message': 'Reply accepted'}), 200
    return jsonify({'error': 'Only the original poster can accept an answer'}), 403


@support_bp.route('/forum/categories', methods=['GET'])
def forum_categories():
    cats = db.session.query(
        ForumPost.category, func.count(ForumPost.id).label('count')
    ).group_by(ForumPost.category).all()
    return jsonify({'categories': [{'name': c, 'count': n} for c, n in cats]}), 200


# ══════════════════════════════════════════════════════════════════════════════
#  SEED DEFAULT DATA
# ══════════════════════════════════════════════════════════════════════════════

def seed_support_data():
    """Seed default KB categories and starter articles (runs once)."""
    if KnowledgeBaseCategory.query.count() > 0:
        return

    cats = [
        KnowledgeBaseCategory(name='Getting Started',   slug='getting-started',  icon='🚀', description='New to OTPGuard? Start here.',              sort_order=1),
        KnowledgeBaseCategory(name='Authentication',    slug='authentication',   icon='🔐', description='MFA, OTP methods, and TOTP setup guides.',   sort_order=2),
        KnowledgeBaseCategory(name='Billing & Plans',   slug='billing',          icon='💳', description='Pricing, upgrades, and billing questions.',  sort_order=3),
        KnowledgeBaseCategory(name='API & Integration', slug='api-integration',  icon='⚙️', description='API keys, SDKs, and integration guides.',   sort_order=4),
        KnowledgeBaseCategory(name='Troubleshooting',   slug='troubleshooting',  icon='🔧', description='Common issues and how to fix them.',         sort_order=5),
        KnowledgeBaseCategory(name='Security',          slug='security',         icon='🛡️', description='Security best practices and policies.',      sort_order=6),
    ]
    for c in cats:
        db.session.add(c)
    db.session.flush()

    m = {c.slug: c.id for c in KnowledgeBaseCategory.query.all()}

    articles = [
        KnowledgeBaseArticle(
            category_id=m.get('getting-started'), title='Quick Start Guide', slug='quick-start',
            is_featured=True, tags='["getting-started","setup","beginner"]',
            excerpt='Get up and running with OTPGuard in 5 minutes.',
            content="""# Quick Start Guide

Welcome to OTPGuard! Follow these steps to get up and running in minutes.

## Step 1: Create Your Account
Sign up at otpguard.co.ke with your email address and verify it.

## Step 2: Enable Multi-Factor Authentication
Navigate to your dashboard → Security Settings → Enable MFA.

## Step 3: Generate an API Key
Go to Settings → API Keys → Create New Key. Copy and store it securely.

## Step 4: Send Your First OTP
Use our API or SDK to trigger OTP verification for your users.

## Step 5: Verify the OTP
Call the verify endpoint with the code your user submits.

That's it! You're now protecting your users with OTPGuard.""",
        ),
        KnowledgeBaseArticle(
            category_id=m.get('authentication'), title='Setting Up Email OTP', slug='email-otp-setup',
            is_featured=True, tags='["email","otp","authentication"]',
            excerpt='Configure Email OTP — the simplest and most accessible MFA method.',
            content="""# Setting Up Email OTP

Email OTP is the default authentication method and requires no extra apps.

## How It Works
1. A 6-digit code is emailed to the user's registered address
2. The user enters the code within 5 minutes
3. The code expires after use or timeout

## Configuration
1. Log in to your OTPGuard dashboard
2. Navigate to **Security → Authentication Methods**
3. Ensure **Email OTP** is enabled (it is by default)
4. Configure the sender address in Settings → Email

## Troubleshooting Delivery Issues
- Check spam/junk folders
- Add `noreply@otpguard.co.ke` to safe senders
- Verify the user's email address is correct
- OTP codes expire after 5 minutes — request a new one""",
        ),
        KnowledgeBaseArticle(
            category_id=m.get('authentication'), title='Setting Up TOTP (Authenticator App)', slug='totp-setup',
            is_featured=True, tags='["totp","authenticator","google-authenticator","2fa"]',
            excerpt='Use Google Authenticator, Authy, or any TOTP app for maximum security.',
            content="""# Setting Up TOTP (Authenticator App)

TOTP provides the strongest MFA security by generating time-based codes locally.

## Supported Apps
- Google Authenticator
- Authy
- Microsoft Authenticator
- 1Password
- Bitwarden

## Setup Steps
1. Go to **Dashboard → Security → Authentication Methods**
2. Select **Authenticator App (TOTP)**
3. Scan the QR code with your authenticator app
4. Enter the 6-digit code shown in your app to confirm
5. **Save your backup codes** in a secure location

## Important Notes
- Backup codes are single-use emergency access codes
- Losing your authenticator app without backup codes can lock you out
- Codes refresh every 30 seconds""",
        ),
        KnowledgeBaseArticle(
            category_id=m.get('billing'), title='Understanding OTPGuard Plans', slug='understanding-plans',
            tags='["pricing","plans","billing","upgrade"]',
            excerpt='Compare Starter, Growth, Business, and Enterprise plans.',
            content="""# OTPGuard Plans Explained

## Starter (Free)
- Email OTP only
- Up to 50 end-users
- Basic security dashboard
- Community support

## Growth — KES 1,500/month
- Email + SMS OTP
- Up to 200 end-users
- Analytics dashboard
- Priority email support

## Business — KES 5,000/month
- All channels (Email, SMS, TOTP, Backup Codes)
- Up to 1,000 end-users
- Advanced analytics & reports
- Priority support with SLA

## Enterprise — Custom Pricing
- Unlimited end-users
- Dedicated infrastructure
- Custom integrations
- 24/7 dedicated support

## Upgrading Your Plan
Navigate to **Dashboard → Billing → Upgrade Plan** to switch plans instantly.""",
        ),
        KnowledgeBaseArticle(
            category_id=m.get('troubleshooting'), title='Not Receiving OTP Codes', slug='not-receiving-otp',
            is_featured=True, tags='["otp","sms","email","troubleshooting","not-receiving"]',
            excerpt='Solve the most common OTP delivery issues for both email and SMS.',
            content="""# Not Receiving OTP Codes

## Email OTP Not Arriving?
1. **Check your spam folder** — automated emails often end up there
2. **Add to safe senders** — whitelist `noreply@otpguard.co.ke`
3. **Verify your email** — ensure your account email is correct
4. **Wait 2 minutes** — email delivery can be delayed
5. **Request a new code** — OTPs expire after 5 minutes

## SMS OTP Not Arriving?
1. **Check your phone number** — ensure it includes country code (e.g. `+254...`)
2. **Check signal** — ensure your phone is not in airplane mode
3. **Carrier delays** — some carriers delay SMS by 1-2 minutes
4. **Premium SMS** — some countries require opting in to receive premium SMS
5. **Request a new code** — try again after 60 seconds

## Still Having Issues?
Contact our support team with:
- Your account email address
- The phone number or email receiving OTPs
- The exact time you attempted to receive the code""",
        ),
        KnowledgeBaseArticle(
            category_id=m.get('api-integration'), title='API Authentication & API Keys', slug='api-authentication',
            is_featured=True, tags='["api","authentication","api-key","integration","x-api-key"]',
            excerpt='How to authenticate with the OTPGuard API using API keys.',
            content="""# API Authentication

## Getting Your API Key
1. Log in to your dashboard
2. Go to **Settings → API Keys**
3. Click **Create New Key**
4. Give it a descriptive name (e.g. "Production App")
5. **Copy and store the key securely** — it won't be shown again

## Using Your API Key
Include the key in every request header:

```
X-API-Key: otpg_your_api_key_here
```

## Rate Limits
| Plan       | Requests/Day |
|------------|-------------|
| Starter    | 100         |
| Growth     | 1,000       |
| Business   | 10,000      |
| Enterprise | Unlimited   |

## Key Management Best Practices
- Never commit keys to version control
- Use environment variables (`.env` files)
- Create separate keys for dev/staging/production
- Rotate keys regularly
- Delete keys that are no longer needed""",
        ),
        KnowledgeBaseArticle(
            category_id=m.get('security'), title='Security Best Practices', slug='security-best-practices',
            tags='["security","best-practices","mfa","api-key"]',
            excerpt='Recommended security practices for OTPGuard administrators and developers.',
            content="""# Security Best Practices

## Protect Your API Keys
- **Never hardcode keys** — use environment variables
- **Rotate keys regularly** — at least every 90 days
- **Use separate keys** — different keys for dev/staging/production
- **Monitor usage** — check the API quota dashboard for anomalies
- **Delete unused keys** immediately

## MFA Configuration
- **Enforce MFA** for all users in your organization
- **Prefer TOTP** over SMS for highest security
- **Store backup codes** in a secure password manager
- **Review devices** — revoke trust from unrecognized devices

## Admin Account Security
- Enable MFA on your OTPGuard admin account
- Use a strong, unique password (16+ chars)
- Review the compliance audit log regularly
- Monitor security alerts in the admin dashboard

## Incident Response
If you suspect a compromise:
1. Rotate all API keys immediately
2. Review the audit log for suspicious activity
3. Reset MFA for affected accounts
4. Contact OTPGuard support""",
        ),
    ]
    for a in articles:
        db.session.add(a)
    db.session.commit()
    logger.info('[SUPPORT] Seeded default KB categories and articles')

    # Seed example forum posts
    if ForumPost.query.count() == 0:
        sample_posts = [
            ForumPost(author_name='Alice K.', title='How do I integrate OTPGuard with Django?',
                      body='I\'m building a Django app and want to add OTP verification. Has anyone done this? Is there an official SDK or do I need to call the REST API directly?',
                      category='api', tags='["django","integration","sdk"]', upvotes=12, views=89, is_pinned=True),
            ForumPost(author_name='Brian M.', title='SMS OTP not delivered to Safaricom numbers',
                      body='Some of our users on Safaricom (Kenya) are reporting they don\'t receive SMS OTPs. Airtel users seem fine. Is this a known issue?',
                      category='technical', tags='["sms","safaricom","kenya"]', upvotes=8, views=54),
            ForumPost(author_name='Carol W.', title='Best practices for OTP expiry time?',
                      body='We\'re debating whether to use 5-minute or 10-minute OTP expiry. What does everyone use? Any security considerations?',
                      category='security', tags='["otp","security","expiry"]', upvotes=15, views=120, is_answered=True),
        ] 

        for p in sample_posts:
            db.session.add(p)
        db.session.flush()

        # Add a reply to the third post
        answered_post = ForumPost.query.filter_by(is_answered=True).first()
        if answered_post:
            r = ForumReply(post_id=answered_post.id, author_name='OTPGuard Team',
                           body='We recommend 5 minutes for SMS/Email OTPs (balances UX and security). For TOTP the window is 30 seconds per RFC 6238. Longer windows increase the attack surface.',
                           upvotes=11, is_accepted=True)
            db.session.add(r)

        db.session.commit()
        logger.info('[SUPPORT] Seeded example forum posts')
