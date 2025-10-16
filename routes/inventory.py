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
from collections import defaultdict
from datetime import timedelta
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
    """
    Adds weekly (Mon–Sun) grouping while preserving your existing free-text filter.
    Template will receive both `invoices` (flat list for backward-compat) and
    `grouped_invoices` = [((week_start_date, week_end_date), [invoices...]), ...]
    newest-first by week.
    """
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

    # ---- Weekly grouping (Mon–Sun) ----
    groups = defaultdict(list)
    for inv in invoices:
        dt = getattr(inv, "created_at", None) or getattr(inv, "invoice_date", None)
        if dt is None:
            # Put undated invoices in a special bucket using their own id as a unique key
            groups[(None, None)].append(inv)
            continue
        # Compute week window using naive datetimes (server local). If you store tz-aware datetimes,
        # this still works since weekday() is calendar-based.
        week_start = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
        key = (week_start.date(), week_end.date())
        groups[key].append(inv)

    # Sort groups newest-first by start date (None goes last)
    def _group_sort_key(kv):
        (start_date, _end_date) = kv[0]
        # Place None at the very end
        return (start_date is None, start_date if start_date is not None else 0)

    grouped_invoices = sorted(groups.items(), key=_group_sort_key, reverse=True)

    return render_template(
        'invoices.html',
        invoices=invoices,                 # kept for backward compatibility
        grouped_invoices=grouped_invoices, # new: weekly buckets
        trailers=trailers,
        q=q
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
    """
    1) Group flagged (Missing/Red Tag) items by Category (excluding 'Extra Tooling' which
       gets its own section). Each category contains aggregated rows per item.
    2) Extras credit-back shows ALL extras for the trailer (not just flagged), including
       items marked Complete and even items with no responses yet.
    """
    trailer = Trailer.query.get_or_404(trailer_id)

    # --- A) FLAGGED (non-extra) grouped by category ---
    flagged_q = (InventoryResponse.query
                 .filter(InventoryResponse.trailer_id == trailer_id,
                         InventoryResponse.status.in_(["Missing", "Red Tag"]))
                 .all())

    # Build category -> (item_number,item_name) -> counts
    cat_map = defaultdict(lambda: defaultdict(lambda: {"item_number": "", "item_name": "",
                                                       "missing_qty": 0, "redtag_qty": 0}))
    for r in flagged_q:
        cat = (r.category or 'General').strip()
        if cat.lower() == 'extra tooling':
            # handled in Extras section
            continue
        key = (r.item_number, r.item_name)
        bucket = cat_map[cat][key]
        bucket["item_number"] = r.item_number
        bucket["item_name"] = r.item_name
        qty = 0
        try:
            qty = int(r.quantity or 0)
        except Exception:
            pass
        if r.status == "Missing":
            bucket["missing_qty"] += qty
        elif r.status == "Red Tag":
            bucket["redtag_qty"] += qty

    # Convert to sorted structure suitable for simple, non-accordion rendering
    grouped_flagged = []
    for category, items_dict in cat_map.items():
        rows = list(items_dict.values())
        rows.sort(key=lambda x: (x["item_name"] or "").lower())
        grouped_flagged.append((category, rows))
    grouped_flagged.sort(key=lambda kv: kv[0].lower())

    # --- B) EXTRAS CREDIT-BACK (ALL items, not filtered) ---
    # Source of truth = trailer.extra_tooling (assigned list)
    extras_catalog = trailer.extra_tooling or []  # [{item_name, item_number, quantity}, ...]

    # Collect ALL extra responses (any status) for this trailer
    extra_resps = (InventoryResponse.query
                   .filter(InventoryResponse.trailer_id == trailer_id,
                           InventoryResponse.category.ilike('%extra tooling%'))
                   .all())

    # Aggregate responses by item_number/name into per-status counts & last note per status
    resp_map = defaultdict(lambda: {"item_number": "", "item_name": "",
                                    "missing_qty": 0, "redtag_qty": 0, "complete_qty": 0,
                                    "notes_missing": "", "notes_redtag": "", "notes_complete": ""})
    for r in extra_resps:
        key = (r.item_number, r.item_name)
        bucket = resp_map[key]
        bucket["item_number"] = r.item_number or ""
        bucket["item_name"] = r.item_name or ""
        qty = 0
        try:
            qty = int(r.quantity or 0)
        except Exception:
            pass
        status = (r.status or "").lower()
        if status == "missing":
            bucket["missing_qty"] += qty
            bucket["notes_missing"] = r.note or bucket["notes_missing"]
        elif status == "red tag":
            bucket["redtag_qty"] += qty
            bucket["notes_redtag"] = r.note or bucket["notes_redtag"]
        elif status == "complete":
            bucket["complete_qty"] += qty
            bucket["notes_complete"] = r.note or bucket["notes_complete"]

    # Merge catalog (assigned extras) with responses so ALL extras appear
    extras_rows_map = {}
    for item in extras_catalog:
        key = (item.get("item_number") or "", item.get("item_name") or "")
        base = {
            "item_number": key[0],
            "item_name": key[1],
            "assigned_qty": int(item.get("quantity") or 0),
            "missing_qty": 0, "redtag_qty": 0, "complete_qty": 0,
            "notes_missing": "", "notes_redtag": "", "notes_complete": ""
        }
        # overlay response counts if present
        if key in resp_map:
            base.update({k: v for k, v in resp_map[key].items() if k in base or k.startswith("notes_")})
        extras_rows_map[key] = base

    # Also include any extra responses that weren't in the original catalog (edge case)
    for key, agg in resp_map.items():
        if key not in extras_rows_map:
            extras_rows_map[key] = {
                "item_number": agg["item_number"],
                "item_name": agg["item_name"],
                "assigned_qty": 0,
                "missing_qty": agg["missing_qty"],
                "redtag_qty": agg["redtag_qty"],
                "complete_qty": agg["complete_qty"],
                "notes_missing": agg["notes_missing"],
                "notes_redtag": agg["notes_redtag"],
                "notes_complete": agg["notes_complete"],
            }

    extras_rows = sorted(extras_rows_map.values(), key=lambda x: (x["item_name"] or "").lower())

    # ---- Back-compat outputs (so your existing template keeps working) ----
    # Old: rows (main flagged, aggregated) and extra_rows (flagged extras only)
    # We'll still compute them, but note: the new UI should use grouped_flagged + extras_rows.
    def _to_legacy_rows_for_main(grouped):
        legacy = []
        for _cat, rows in grouped:
            for r in rows:
                legacy.append({
                    "item_name": r["item_name"],
                    "item_number": r["item_number"],
                    "missing_qty": r["missing_qty"],
                    "redtag_qty": r["redtag_qty"],
                })
        # keep name sort to match previous behavior
        return sorted(legacy, key=lambda x: (x["item_name"] or "").lower())

    rows_main_legacy = _to_legacy_rows_for_main(grouped_flagged)

    def _to_legacy_rows_for_extras(extras):
        # previously only flagged shown; keep everything but the template may only show missing/redtag
        return [{
            "item_name": r["item_name"],
            "item_number": r["item_number"],
            "missing_qty": r["missing_qty"],
            "redtag_qty": r["redtag_qty"],
            # note: complete_qty is now available if you update the template
        } for r in extras]

    rows_extra_legacy = _to_legacy_rows_for_extras(extras_rows)

    return render_template(
        'pull_list.html',
        trailer=trailer,
        # NEW preferred context:
        grouped_flagged=grouped_flagged,  # [(category, [rows...]), ...]
        extras_rows=extras_rows,          # ALL extras (missing/red tag/complete, plus assigned_qty)
        # Back-compat:
        rows=rows_main_legacy,
        extra_rows=rows_extra_legacy
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
