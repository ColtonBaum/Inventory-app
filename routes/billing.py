# routes/billing.py
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session, current_app, make_response, abort
)
from models import ItemPrice, Trailer, InventoryResponse
from database import db
from utils.tooling_lists import get_tooling_list
from functools import wraps
from collections import defaultdict
from datetime import datetime
import io

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')


# ---------- Auth ----------
def billing_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('billing_auth'):
            return redirect(url_for('billing.login', next=request.url))
        return f(*args, **kwargs)
    return decorated


@billing_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if pw == current_app.config.get('BILLING_PASSWORD', ''):
            session['billing_auth'] = True
            next_url = request.args.get('next') or url_for('billing.billing_dashboard')
            return redirect(next_url)
        flash('Incorrect password.', 'danger')
    return render_template('billing_login.html')


@billing_bp.route('/logout')
def logout():
    session.pop('billing_auth', None)
    flash('Logged out of billing.', 'info')
    return redirect(url_for('inventory.dashboard'))


# ---------- Dashboard ----------
@billing_bp.route('/')
@billing_required
def billing_dashboard():
    q = (request.args.get('q') or '').strip().lower()
    trailers = Trailer.query.filter(Trailer.status == 'Completed').order_by(Trailer.id.desc()).all()
    if q:
        trailers = [t for t in trailers if q in (t.job_name or '').lower()
                     or q in (t.job_number or '').lower()
                     or q in str(t.id)]
    return render_template('billing_dashboard.html', trailers=trailers, q=q)


# ---------- Pricing Management ----------
@billing_bp.route('/pricing', methods=['GET', 'POST'])
@billing_required
def pricing():
    if request.method == 'POST':
        # Bulk update prices
        for key, val in request.form.items():
            if key.startswith('price_'):
                item_number = key[6:]  # strip 'price_'
                try:
                    price_val = float(val) if val.strip() else 0.0
                except ValueError:
                    price_val = 0.0

                existing = ItemPrice.query.filter_by(item_number=item_number).first()
                if existing:
                    existing.price = price_val
                else:
                    item_name = request.form.get(f'name_{item_number}', '')
                    db.session.add(ItemPrice(
                        item_number=item_number,
                        item_name=item_name,
                        price=price_val
                    ))
        db.session.commit()
        flash('Prices updated.', 'success')
        return redirect(url_for('billing.pricing'))

    # Build a master list of all items across all tooling lists + any already-priced items
    from utils.tooling_lists import tooling_lists as all_lists
    all_items = {}  # item_number -> item_name
    for list_name, items in all_lists.items():
        for item in items:
            num = item.get('Item Number', '').strip()
            name = item.get('Item Name', '').strip()
            if num and num not in all_items:
                all_items[num] = name

    # Merge in any existing prices
    prices = {p.item_number: p for p in ItemPrice.query.all()}
    for num in prices:
        if num not in all_items:
            all_items[num] = prices[num].item_name or ''

    # Search filter
    q = (request.args.get('q') or '').strip().lower()

    # Build display rows
    rows = []
    for num, name in sorted(all_items.items(), key=lambda x: (x[1] or '').lower()):
        if q and q not in num.lower() and q not in name.lower():
            continue
        p = prices.get(num)
        rows.append({
            'item_number': num,
            'item_name': name,
            'price': p.price if p else 0.0,
        })

    return render_template('billing_pricing.html', rows=rows, q=q)


# ---------- Generate Billing Invoice for a Trailer ----------
@billing_bp.route('/invoice/<int:trailer_id>')
@billing_required
def generate_billing_invoice(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)

    # Get all responses for this trailer
    responses = InventoryResponse.query.filter_by(trailer_id=trailer_id).all()

    # Get the tooling list to know expected quantities
    list_name = (trailer.tooling_list_name or trailer.inventory_type or '').strip()
    tooling_list = get_tooling_list(list_name) or []

    # Build expected qty map
    expected_map = {}
    for item in tooling_list:
        num = item.get('Item Number', '').strip()
        expected_map[num] = {
            'item_name': item.get('Item Name', ''),
            'quantity': int(item.get('Quantity', 0)) if str(item.get('Quantity', 0)).isdigit() else 0,
        }

    # Build response status map
    response_map = defaultdict(lambda: {'missing': 0, 'redtag': 0, 'complete': False, 'note': ''})
    for r in responses:
        key = r.item_number
        if r.status == 'Missing':
            response_map[key]['missing'] += (r.quantity or 0)
            if r.note:
                response_map[key]['note'] = r.note
        elif r.status == 'Red Tag':
            response_map[key]['redtag'] += (r.quantity or 0)
            if r.note:
                response_map[key]['note'] = r.note
        elif r.status == 'Complete':
            response_map[key]['complete'] = True

    # Load prices
    price_map = {p.item_number: p.price for p in ItemPrice.query.all()}

    # Build line items — only items that are missing or red tagged
    line_items = []
    total = 0.0
    for num, info in expected_map.items():
        resp = response_map.get(num, {})
        missing_qty = resp.get('missing', 0)
        redtag_qty = resp.get('redtag', 0)
        billable_qty = missing_qty + redtag_qty
        if billable_qty <= 0:
            continue
        unit_price = price_map.get(num, 0.0)
        line_total = unit_price * billable_qty
        total += line_total
        line_items.append({
            'item_number': num,
            'item_name': info['item_name'],
            'missing_qty': missing_qty,
            'redtag_qty': redtag_qty,
            'billable_qty': billable_qty,
            'unit_price': unit_price,
            'line_total': line_total,
            'note': resp.get('note', ''),
        })

    # Also add extra tooling items
    extra_responses = [r for r in responses if (r.category or '').strip().lower() == 'extra tooling']
    extra_map = defaultdict(lambda: {'missing': 0, 'redtag': 0, 'item_name': '', 'note': ''})
    for r in extra_responses:
        key = r.item_number
        extra_map[key]['item_name'] = r.item_name
        if r.status == 'Missing':
            extra_map[key]['missing'] += (r.quantity or 0)
            if r.note:
                extra_map[key]['note'] = r.note
        elif r.status == 'Red Tag':
            extra_map[key]['redtag'] += (r.quantity or 0)
            if r.note:
                extra_map[key]['note'] = r.note

    for num, info in extra_map.items():
        billable_qty = info['missing'] + info['redtag']
        if billable_qty <= 0:
            continue
        unit_price = price_map.get(num, 0.0)
        line_total = unit_price * billable_qty
        total += line_total
        line_items.append({
            'item_number': num,
            'item_name': info['item_name'],
            'missing_qty': info['missing'],
            'redtag_qty': info['redtag'],
            'billable_qty': billable_qty,
            'unit_price': unit_price,
            'line_total': line_total,
            'note': info.get('note', ''),
        })

    line_items.sort(key=lambda x: (x['item_name'] or '').lower())

    return render_template(
        'billing_invoice.html',
        trailer=trailer,
        line_items=line_items,
        total=total,
        now=datetime.now,
    )
