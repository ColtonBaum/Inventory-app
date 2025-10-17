# routes/inventory.py
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, send_from_directory, abort, current_app
)
from models import Trailer, InventoryResponse, Invoice
from database import db
from utils.invoice_generator import generate_invoice
from utils.tooling_lists import get_tooling_list  # helper to fetch list by name
from sqlalchemy import desc
from datetime import datetime, timedelta
from collections import defaultdict
import os

inventory_bp = Blueprint('inventory', __name__)

# ---------- Helpers ----------
def _apply_ln25_from_form(trailer, form):
    """
    Accept common LN-25 field aliases from forms and write to whichever Trailer
    attribute actually exists in your model. No DB migration required.
    """
    incoming = (
        form.get('ln_25s') or form.get('ln_25') or form.get('ln25') or
        form.get('LN_25') or form.get('LN25') or form.get('LN_25s') or ''
    )
    incoming = (incoming or '').strip()
    if not incoming:
        return

    # Try common attribute names; stop at the first one this model has.
    for attr in ['ln_25s', 'ln_25', 'ln25', 'lN_25s', 'LN_25', 'LN25', 'LN_25s', 'ln25s']:
        if hasattr(trailer, attr):
            setattr(trailer, attr, incoming)
            break


def _week_range(dt: datetime):
    """Return (monday, sunday) date objects for the week containing dt (Mon–Sun)."""
    if not dt:
        return (None, None)
    d = dt.date()
    monday = d - timedelta(days=d.weekday())  # Monday=0
    sunday = monday + timedelta(days=6)
    return (monday, sunday)


# ---------- Dashboard ----------
@inventory_bp.route('/')
def dashboard():
    query = Trailer.query

    job_name = request.args.get('job_name')
    if job_name:
        query = query.filter(Trailer.job_name.ilike(f"%{job_name}%"))

    job_number = request.args.get('job_number')
    if job_number:
        query = query.filter(Trailer.job_number.ilike(f"%{job_number}%"))

    status = request.args.get('status')
    if status:
        query = query.filter(Trailer.status == status)
    else:
        query = query.filter(Trailer.status != 'Completed')

    inventory_type = request.args.get('inventory_type')
    if inventory_type:
        query = query.filter(Trailer.inventory_type == inventory_type)

    trailers = query.order_by(desc(Trailer.id)).all()
    return render_template('dashboard.html', trailers=trailers)

# ---------- Global Invoices Tab (all invoices) ----------
@inventory_bp.route('/invoices')
def view_invoices():
    q = (request.args.get('q') or "").strip().lower()

    invoices = Invoice.query.order_by(Invoice.created_at.desc()).all()
    trailer_ids = {inv.trailer_id for inv in invoices}
    trailers = {t.id: t for t in Trailer.query.filter(Trailer.id.in_(trailer_ids)).all()} if trailer_ids else {}

    if q:
        def match(inv):
            t = trailers.get(inv.trailer_id)
            if not t:
                return False
            hay = " ".join([
                str(t.id or ""),
                t.job_name or "",
                t.job_number or "",
                t.location or "",
                t.tooling_list_name or "",
                t.assigned_user or "",
            ]).lower()
            return q in hay
        invoices = [inv for inv in invoices if match(inv)]

    # --- Weekly grouping (Mon–Sun) ---
    buckets = defaultdict(list)  # (monday_date, sunday_date) -> [Invoice,...]
    undated = []  # handle None created_at
    for inv in invoices:
        if inv.created_at:
            wk = _week_range(inv.created_at)
            buckets[wk].append(inv)
        else:
            undated.append(inv)

    # Sort buckets by week start descending
    grouped_invoices = []
    for wk, items in buckets.items():
        grouped_invoices.append((wk, sorted(items, key=lambda i: (i.created_at or datetime.min), reverse=True)))
    grouped_invoices.sort(key=lambda pair: (pair[0][0] or datetime.min.date()), reverse=True)

    # Put undated at the end, with a (None, None) key
    if undated:
        grouped_invoices.append(((None, None), undated))

    return render_template(
        'invoices.html',
        invoices=invoices,            # fallback in template
        trailers=trailers,
        q=q,
        grouped_invoices=grouped_invoices
    )

# NEW: Delete an invoice (removes DB row and file if present)
@inventory_bp.route('/invoice/<int:invoice_id>/delete', methods=['POST'])
def delete_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)

    # Best-effort file removal
    try:
        if invoice.file_path:
            file_path = os.path.abspath(invoice.file_path)
            if os.path.exists(file_path):
                os.remove(file_path)
    except Exception:
        current_app.logger.exception("Failed to remove invoice file")

    db.session.delete(invoice)
    db.session.commit()
    flash('Invoice deleted.', 'info')
    return redirect(url_for('inventory.view_invoices'))

# ---------- Add / Edit / Delete Trailer (meta) ----------
@inventory_bp.route('/trailer/add', methods=['GET', 'POST'])
def add_trailer():
    """
    Optional meta add route (separate from assign flow).
    Stores extra_tooling consistently as item_name/item_number/quantity.
    """
    if request.method == 'POST':
        tooling_items = []
        names = request.form.getlist('tool_name')
        numbers = request.form.getlist('tool_number')
        qtys = request.form.getlist('tool_qty')

        for name, number, qty in zip(names, numbers, qtys):
            name = (name or '').strip()
            number = (number or '').strip()
            if name and number:
                tooling_items.append({
                    'item_name': name,
                    'item_number': number,
                    'quantity': int(qty or 0)
                })

        trailer = Trailer(
            job_name=request.form['job_name'],
            job_number=request.form['job_number'],
            location=request.form.get('location') or '',
            tooling_list_name=request.form.get('tooling_list_name') or 'Standard Trailer',
            assigned_user=(request.form.get('assigned_user') or None),
            status='Pending',
            inventory_type=request.form.get('inventory_type') or None,
            extra_tooling=tooling_items
        )

        # Capture LN-25 from the form into whichever attribute exists on Trailer
        _apply_ln25_from_form(trailer, request.form)

        db.session.add(trailer)
        db.session.commit()
        flash('Trailer assigned. Status set to Pending.', 'success')
        return redirect(url_for('inventory.dashboard'))

    return render_template('add_edit_trailer.html', mode='Add')

@inventory_bp.route('/trailer/<int:trailer_id>/edit-meta', methods=['GET', 'POST'])
def edit_trailer(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)
    if request.method == 'POST':
        tooling_items = []
        names = request.form.getlist('tool_name')
        numbers = request.form.getlist('tool_number')
        qtys = request.form.getlist('tool_qty')

        for name, number, qty in zip(names, numbers, qtys):
            name = (name or '').strip()
            number = (number or '').strip()
            if name and number:
                tooling_items.append({
                    'item_name': name,
                    'item_number': number,
                    'quantity': int(qty or 0)
                })

        trailer.job_name = request.form['job_name']
        trailer.job_number = request.form['job_number']
        trailer.location = request.form.get('location') or ''
        trailer.tooling_list_name = request.form.get('tooling_list_name') or trailer.tooling_list_name
        trailer.assigned_user = request.form.get('assigned_user') or trailer.assigned_user
        trailer.extra_tooling = tooling_items

        # Capture/overwrite LN-25 from the form
        _apply_ln25_from_form(trailer, request.form)

        db.session.commit()
        flash('Trailer details updated.', 'success')
        return redirect(url_for('inventory.dashboard'))

    return render_template('add_edit_trailer.html', mode='Edit', trailer=trailer)

@inventory_bp.route('/trailer/<int:trailer_id>/delete', methods=['POST'])
def delete_trailer(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)
    db.session.delete(trailer)
    db.session.commit()
    flash('Trailer deleted.', 'info')
    return redirect(url_for('inventory.dashboard'))

# ---------- OPTIONAL inline LN-25 updater ----------
@inventory_bp.route('/trailer/<int:trailer_id>/ln25', methods=['POST'])
def update_ln25(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)
    _apply_ln25_from_form(trailer, request.form)
    db.session.commit()
    flash('LN-25 updated.', 'success')
    return redirect(request.referrer or url_for('inventory.inventory_form', trailer_id=trailer.id))

# ---------- Inventory Form (GET only: start -> In Progress) ----------
@inventory_bp.route('/trailer/<int:trailer_id>', methods=['GET'])
def inventory_form(trailer_id):
    """
    Renders the inventory form. When opened from Pending, mark as In Progress.
    Actual submission is posted to `trailer_assignment.trailer_update`.
    """
    trailer = Trailer.query.get_or_404(trailer_id)

    # Resolve list name robustly, then fetch items
    list_name = (trailer.tooling_list_name or trailer.inventory_type or "").strip()
    tooling_list = get_tooling_list(list_name) or []
    current_app.logger.info(f"[INV_FORM] trailer={trailer.id} list_name='{list_name}' items={len(tooling_list)}")

    # Mark In Progress on first open
    if trailer.status == 'Pending':
        trailer.status = 'In Progress'
        db.session.commit()

    return render_template(
        'inventory_form.html',
        trailer=trailer,
        tooling_list=tooling_list,
        credit_back_items=trailer.extra_tooling or [],
        existing=None,
        read_only=False
    )

# ---------- Read-only View of Submitted Form ----------
@inventory_bp.route('/trailer/<int:trailer_id>/view')
def view_form(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)

    list_name = (trailer.tooling_list_name or trailer.inventory_type or "").strip()
    tooling_list = get_tooling_list(list_name) or []
    current_app.logger.info(f"[INV_VIEW] trailer={trailer.id} list_name='{list_name}' items={len(tooling_list)}")

    existing_responses = InventoryResponse.query.filter_by(trailer_id=trailer.id).all()
    existing = {}
    for r in existing_responses:
        bucket = existing.setdefault(r.item_number, {
            'statuses': set(),
            'notes': {},
            'quantity': r.quantity
        })
        bucket['statuses'].add(r.status)
        key = r.status.lower().replace(' ', '')
        bucket['notes'][key] = r.note
        bucket['quantity'] = r.quantity

    return render_template(
        'inventory_form.html',
        trailer=trailer,
        tooling_list=tooling_list,
        credit_back_items=trailer.extra_tooling or [],
        existing=existing,
        read_only=True
    )

# ---------- Pull List (HTML "invoice" view) ----------
@inventory_bp.route('/trailer/<int:trailer_id>/pull-list')
def pull_list(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)

    # All responses for this trailer
    all_responses = (InventoryResponse.query
                     .filter(InventoryResponse.trailer_id == trailer_id)
                     .all())

    # --- Group main flagged items (Missing/Red Tag) by Category ---
    flagged = [r for r in all_responses if r.status in ("Missing", "Red Tag") and (r.category or '').strip().lower() != 'extra tooling']

    grouped = defaultdict(lambda: defaultdict(lambda: {"Missing": 0, "Red Tag": 0}))
    for r in flagged:
        category = (r.category or 'General').strip() or 'General'
        key = (r.item_number, r.item_name)
        try:
            qty = int(r.quantity or 0)
        except Exception:
            qty = 0
        if r.status in ("Missing", "Red Tag"):
            grouped[category][key][r.status] += qty

    # convert to template-friendly list: [(category, [rows...]), ...]
    grouped_flagged = []
    for category, items_map in grouped.items():
        rows = []
        for (item_number, item_name), counts in items_map.items():
            rows.append({
                "item_name": item_name,
                "item_number": item_number,
                "missing_qty": counts.get("Missing", 0),
                "redtag_qty": counts.get("Red Tag", 0),
            })
        rows.sort(key=lambda x: (x["item_name"] or "").lower())
        grouped_flagged.append((category, rows))
    # stable sort by category name
    grouped_flagged.sort(key=lambda pair: (pair[0] or "").lower())

    # --- Extras: show ALL items with Assigned/Missing/RedTag/Complete ---
    # Build assigned quantities from trailer.extra_tooling
    assigned_map = {}  # (item_number, item_name) -> assigned_qty
    for it in (trailer.extra_tooling or []):
        key = ((it.get('item_number') or '').strip(), (it.get('item_name') or '').strip())
        assigned_map[key] = int(it.get('quantity') or 0)

    # Aggregate extra responses by status
    extra_counts = defaultdict(lambda: {"assigned": 0, "Missing": 0, "Red Tag": 0, "Complete": 0})
    # seed from assigned_map so even items without responses appear
    for key, qty in assigned_map.items():
        extra_counts[key]["assigned"] = qty

    for r in all_responses:
        if (r.category or '').strip().lower() == 'extra tooling':
            key = (r.item_number or '', r.item_name or '')
            try:
                qty = int(r.quantity or 0)
            except Exception:
                qty = 0
            if r.status in ("Missing", "Red Tag", "Complete"):
                extra_counts[key][r.status] += qty
            # if an extra item is only in responses (not in assigned_map), keep assigned=0
            extra_counts[key]["assigned"] = max(extra_counts[key].get("assigned", 0), assigned_map.get(key, 0))

    extras_rows = []
    for (item_number, item_name), counts in extra_counts.items():
        extras_rows.append({
            "item_name": item_name,
            "item_number": item_number,
            "assigned_qty": counts.get("assigned", 0),
            "missing_qty": counts.get("Missing", 0),
            "redtag_qty": counts.get("Red Tag", 0),
            "complete_qty": counts.get("Complete", 0),
        })
    extras_rows.sort(key=lambda x: (x["item_name"] or "").lower())

    # Fallback legacy rows
    rows_main = []
    rows_extra = []

    return render_template(
        'pull_list.html',
        trailer=trailer,
        grouped_flagged=grouped_flagged,
        extras_rows=extras_rows,
        rows=rows_main,
        extra_rows=rows_extra
    )

@inventory_bp.route('/invoice/<int:invoice_id>/download')
def download_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    file_path = invoice.file_path
    if not file_path:
        abort(404)
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        abort(404)
    directory, filename = os.path.dirname(file_path), os.path.basename(file_path)
    return send_from_directory(directory, filename, as_attachment=True)

# ---------- Edit the Already-Submitted Form ----------
@inventory_bp.route('/trailer/<int:trailer_id>/edit-submission', methods=['GET', 'POST'])
def edit_submission(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)

    list_name = (trailer.tooling_list_name or trailer.inventory_type or "").strip()
    tooling_list = get_tooling_list(list_name) or []
    current_app.logger.info(f"[INV_EDIT] trailer={trailer.id} list_name='{list_name}' items={len(tooling_list)}")

    if request.method == 'POST':
        # accept either 'assigned_user' or legacy 'submitted_by'
        who = (request.form.get('assigned_user') or request.form.get('submitted_by') or "").strip()
        if who:
            trailer.assigned_user = who

        # Clear previous responses & invoices
        InventoryResponse.query.filter_by(trailer_id=trailer.id).delete()
        Invoice.query.filter_by(trailer_id=trailer.id).delete()
        db.session.commit()

        responses = []
        flagged_items = []

        # Re-collect regular tooling responses
        for item in tooling_list:
            item_number = item['Item Number']
            item_name = item['Item Name']
            category = item.get('Category', 'General')
            quantity = request.form.get(f"{item_number}_quantity", item.get('Quantity', 0))

            for status_key, status_label in [
                (f"{item_number}_status_missing", "Missing"),
                (f"{item_number}_status_redtag", "Red Tag"),
                (f"{item_number}_status_complete", "Complete"),
            ]:
                if request.form.get(status_key):
                    note_key = f"{item_number}_note_{status_label.lower().replace(' ', '')}"
                    note = request.form.get(note_key, '')

                    r = InventoryResponse(
                        trailer_id=trailer.id,
                        item_number=item_number,
                        item_name=item_name,
                        status=status_label,
                        note=note,
                        quantity=int(quantity) if str(quantity).isdigit() else 0,
                        category=category
                    )
                    responses.append(r)
                    if status_label in ['Missing', 'Red Tag']:
                        flagged_items.append(r)

        db.session.add_all(responses)
        db.session.commit()

        # Recreate invoice (or empty record)
        if flagged_items:
            invoice_path = generate_invoice(trailer.id, flagged_items) or ""
            db.session.add(Invoice(trailer_id=trailer.id, file_path=invoice_path))
        else:
            db.session.add(Invoice(trailer_id=trailer.id, file_path=""))

        # Extra tooling (credit-back) — collect ALL statuses; category 'Extra Tooling'
        extra_responses = []
        credit_back_items = trailer.extra_tooling or []
        for i, item in enumerate(credit_back_items):
            item_name = item.get('item_name') or ''
            item_number = item.get('item_number') or ''
            quantity = request.form.get(f"cb_{i}_quantity", item.get('quantity', 0))

            for status_key, status_label in [
                (f"cb_{i}_missing", "Missing"),
                (f"cb_{i}_redtag", "Red Tag"),
                (f"cb_{i}_complete", "Complete"),
            ]:
                if request.form.get(status_key):
                    note_key = f"cb_{i}_note_{status_label.lower().replace(' ', '')}"
                    note = request.form.get(note_key, '')

                    r = InventoryResponse(
                        trailer_id=trailer.id,
                        item_number=item_number,
                        item_name=item_name,
                        status=status_label,
                        note=note,
                        quantity=int(quantity) if str(quantity).isdigit() else 0,
                        category='Extra Tooling'
                    )
                    extra_responses.append(r)

        if extra_responses:
            db.session.add_all(extra_responses)

        db.session.commit()
        flash('Submission updated. Pull list regenerated.', 'success')
        return redirect(url_for('inventory.pull_list', trailer_id=trailer.id))

    # GET -> prefill map
    existing_responses = InventoryResponse.query.filter_by(trailer_id=trailer.id).all()
    existing = {}
    for r in existing_responses:
        bucket = existing.setdefault(r.item_number, {
            'statuses': set(),
            'notes': {},
            'quantity': r.quantity
        })
        bucket['statuses'].add(r.status)
        key = r.status.lower().replace(' ', '')
        bucket['notes'][key] = r.note
        bucket['quantity'] = r.quantity

    return render_template(
        'inventory_form.html',
        trailer=trailer,
        tooling_list=tooling_list,
        credit_back_items=trailer.extra_tooling or [],
        existing=existing,
        read_only=False
    )
