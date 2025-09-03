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
import os

inventory_bp = Blueprint('inventory', __name__)

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

    return render_template('invoices.html', invoices=invoices, trailers=trailers, q=q)

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

    flagged = (InventoryResponse.query
               .filter(InventoryResponse.trailer_id == trailer_id,
                       InventoryResponse.status.in_(["Missing", "Red Tag"]))
               .all())

    # Split aggregation: main vs Extra Tooling
    agg_main = {}
    agg_extra = {}

    for r in flagged:
        is_extra = (r.category or '').strip().lower() == 'extra tooling'
        target = agg_extra if is_extra else agg_main

        key = (r.item_number, r.item_name)
        bucket = target.setdefault(key, {"Missing": 0, "Red Tag": 0})
        if r.status in bucket:
            try:
                bucket[r.status] += int(r.quantity or 0)
            except Exception:
                pass

    def to_rows(agg_dict):
        rows = []
        for (item_number, item_name), counts in agg_dict.items():
            rows.append({
                "item_name": item_name,
                "item_number": item_number,
                "missing_qty": counts.get("Missing", 0),
                "redtag_qty": counts.get("Red Tag", 0),
            })
        rows.sort(key=lambda x: x["item_name"].lower())
        return rows

    rows_main = to_rows(agg_main)
    rows_extra = to_rows(agg_extra)

    return render_template(
        'pull_list.html',
        trailer=trailer,
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
        submitted_by = (request.form.get('submitted_by') or "").strip()
        if submitted_by:
            trailer.assigned_user = submitted_by

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

        # Extra tooling (credit-back) — use normalized keys
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
