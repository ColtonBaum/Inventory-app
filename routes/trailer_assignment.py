# routes/trailer_assignment.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import Trailer, InventoryResponse, Invoice
from database import db
from utils.tooling_lists import tooling_lists
from utils.invoice_generator import generate_invoice

trailer_assignment_bp = Blueprint('trailer_assignment', __name__)

# ----------------------------------------------------------------------------- 
# CREATE / ASSIGN
# -----------------------------------------------------------------------------
@trailer_assignment_bp.route('/assign_trailer', methods=['GET', 'POST'], endpoint='assign_trailer')
def assign_trailer():
    if request.method == 'POST':
        job_name     = (request.form.get('job_name') or '').strip()
        job_number   = (request.form.get('job_number') or '').strip()
        tooling_list = (request.form.get('tooling_list_name') or '').strip()

        location       = (request.form.get('location') or '').strip()
        submitted_by   = (request.form.get('submitted_by') or '').strip()
        assigned_user  = (request.form.get('assigned_user') or submitted_by or '').strip() or None
        foreman_name   = (request.form.get('foreman_name') or '').strip() or None
        external_id    = (request.form.get('trailer_id') or '').strip() or None

        ln25_val = (request.form.get('ln_25s') or request.form.get('lN-25s') or request.form.get('LN_25') or '').strip() or None

        extra_tooling_data = []
        if request.form.get('enable_credit_back'):
            raw        = request.form.to_dict(flat=False)
            names      = raw.get('extra_tooling_items[][item_name]', []) or raw.get('extra_tooling_items[item_name][]', [])
            numbers    = raw.get('extra_tooling_items[][item_number]', []) or raw.get('extra_tooling_items[item_number][]', [])
            quantities = raw.get('extra_tooling_items[][quantity]', []) or raw.get('extra_tooling_items[quantity][]', [])
            categories = raw.get('extra_tooling_items[][category]', []) or raw.get('extra_tooling_items[category][]', [])
            for i in range(max(len(names), len(numbers), len(quantities), len(categories))):
                name = names[i] if i < len(names) else ''
                num  = numbers[i] if i < len(numbers) else ''
                cat  = categories[i] if i < len(categories) else ''
                try:
                    qty = int(quantities[i]) if i < len(quantities) and str(quantities[i]).strip() != '' else 0
                except Exception:
                    qty = 0
                if name or num:
                    extra_tooling_data.append({
                        'item_name': name,
                        'item_number': num,
                        'quantity': qty,
                        'category': cat or 'Extra Tooling'
                    })

        t = Trailer(
            trailer_id=external_id,
            job_name=job_name,
            job_number=job_number,
            location=location,
            tooling_list_name=tooling_list,
            inventory_type=tooling_list,
            assigned_user=assigned_user,
            status='Pending',
            extra_tooling=extra_tooling_data or None,
            foreman_name=foreman_name
        )
        if ln25_val:
            for attr in ('ln_25s', 'lN_25s', 'LN_25'):
                if hasattr(t, attr):
                    setattr(t, attr, ln25_val)
                    break

        db.session.add(t)
        db.session.commit()
        flash('Trailer assigned.', 'success')
        return redirect(url_for('inventory.dashboard'))

    list_options = list(tooling_lists.keys())
    return render_template('assign_trailer.html', list_options=list_options)

# ----------------------------------------------------------------------------- 
# UPDATE (compat metadata)
# -----------------------------------------------------------------------------
@trailer_assignment_bp.route('/trailer/<int:trailer_id>', methods=['POST'], strict_slashes=False)
def update_trailer_post(trailer_id):
    t = Trailer.query.get_or_404(trailer_id)

    job_name        = (request.form.get('job_name') or '').strip() or t.job_name
    job_number      = (request.form.get('job_number') or '').strip() or t.job_number
    location        = (request.form.get('location') or '').strip() or t.location

    submitted_by    = (request.form.get('submitted_by') or '').strip()
    assigned_user   = (request.form.get('assigned_user') or submitted_by or '').strip() or t.assigned_user

    foreman_name    = (request.form.get('foreman_name') or '').strip() or t.foreman_name
    tooling_list    = (request.form.get('tooling_list_name') or '').strip() or t.tooling_list_name
    status          = (request.form.get('status') or '').strip() or t.status

    ln25_val = (request.form.get('ln_25s') or request.form.get('lN-25s') or request.form.get('LN_25') or '').strip()
    if ln25_val:
        for attr in ('ln_25s', 'lN_25s', 'LN_25'):
            if hasattr(t, attr):
                setattr(t, attr, ln25_val)
                break

    extra_tooling_data = None
    if request.form.get('enable_credit_back'):
        raw        = request.form.to_dict(flat=False)
        names      = raw.get('extra_tooling_items[][item_name]', []) or raw.get('extra_tooling_items[item_name][]', [])
        numbers    = raw.get('extra_tooling_items[][item_number]', []) or raw.get('extra_tooling_items[item_number][]', [])
        quantities = raw.get('extra_tooling_items[][quantity]', []) or raw.get('extra_tooling_items[quantity][]', [])
        categories = raw.get('extra_tooling_items[][category]', []) or raw.get('extra_tooling_items[category][]', [])
        rows = []
        for i in range(max(len(names), len(numbers), len(quantities), len(categories))):
            name = names[i] if i < len(names) else ''
            num  = numbers[i] if i < len(numbers) else ''
            cat  = categories[i] if i < len(categories) else ''
            try:
                qty = int(quantities[i]) if i < len(quantities) and str(quantities[i]).strip() != '' else 0
            except Exception:
                qty = 0
            if name or num:
                rows.append({
                    'item_name': name,
                    'item_number': num,
                    'quantity': qty,
                    'category': cat or 'Extra Tooling'
                })
        extra_tooling_data = rows

    t.job_name = job_name
    t.job_number = job_number
    t.location = location
    t.assigned_user = assigned_user or None
    t.foreman_name = foreman_name or None
    t.tooling_list_name = tooling_list
    t.inventory_type = tooling_list
    t.status = status
    if extra_tooling_data is not None:
        t.extra_tooling = extra_tooling_data

    db.session.commit()
    flash('Trailer updated.', 'success')
    return redirect(f'/trailer/{t.id}')

# ----------------------------------------------------------------------------- 
# UPDATE (submission) — use checkbox + text note fields as the per-status qty
# -----------------------------------------------------------------------------
@trailer_assignment_bp.route('/trailer/<int:trailer_id>/update', methods=['POST'], strict_slashes=False)
@trailer_assignment_bp.route('/trailer/<int:trailer_id>/update/', methods=['POST'], strict_slashes=False)
def trailer_update(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)

    # Save who submitted (your form uses "assigned_user")
    submitted_by = (request.form.get('submitted_by') or request.form.get('assigned_user') or '').strip()
    if submitted_by:
        trailer.assigned_user = submitted_by

    # LN-25 passthrough (if present anywhere)
    ln25_val = (request.form.get('ln_25s') or request.form.get('lN-25s') or request.form.get('LN_25') or '').strip()
    if ln25_val:
        for attr in ('ln_25s', 'lN_25s', 'LN_25'):
            if hasattr(trailer, attr):
                setattr(trailer, attr, ln25_val)
                break

    # Optional meta passthroughs
    if 'location' in request.form:
        trailer.location = (request.form.get('location') or trailer.location or '').strip()
    if 'status' in request.form:
        trailer.status = (request.form.get('status') or trailer.status or 'Pending').strip()
    if 'job_name' in request.form:
        trailer.job_name = (request.form.get('job_name') or trailer.job_name or '').strip()
    if 'job_number' in request.form:
        trailer.job_number = (request.form.get('job_number') or trailer.job_number or '').strip()

    # Fresh submission
    InventoryResponse.query.filter_by(trailer_id=trailer.id).delete()

    f = request.form.get

    def parse_qty_from_text(txt):
        """Pull a positive integer from a free-text input. Non-digits are ignored."""
        if txt is None:
            return 0
        s = ''.join(ch for ch in str(txt) if ch.isdigit())
        if not s:
            return 0
        try:
            n = int(s)
            return n if n > 0 else 0
        except Exception:
            return 0

    responses = []
    flagged = []

    # -------- MAIN INVENTORY (discover lines via the hidden *_item_name fields) --------
    base_keys = set()
    for key in request.form.keys():
        if key.endswith('_item_name'):
            base_keys.add(key[:-len('_item_name')])

    for base in base_keys:
        item_number = base
        item_name   = f(f"{base}_item_name") or ''
        category    = f(f"{base}_category")  or 'General'

        is_missing  = bool(f(f"{base}_status_missing"))
        is_redtag   = bool(f(f"{base}_status_redtag"))
        is_complete = bool(f(f"{base}_status_complete"))

        # Text inputs carry the user-entered counts
        miss_qty = parse_qty_from_text(f(f"{base}_note_missing"))
        red_qty  = parse_qty_from_text(f(f"{base}_note_redtag"))

        if is_missing and miss_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Missing',
                note=f(f"{base}_note_missing") or "",   # keep original text in case you want it later
                quantity=miss_qty,
                category=category
            )
            responses.append(r); flagged.append(r)

        if is_redtag and red_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Red Tag',
                note=f(f"{base}_note_redtag") or "",
                quantity=red_qty,
                category=category
            )
            responses.append(r); flagged.append(r)

        if is_complete:
            responses.append(InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Complete',
                note='',
                quantity=0,
                category=category
            ))

    # -------- EXTRA TOOLING (use posted hidden fields for each cb_* line) --------
    # We look for any keys like "cb_{i}_item_name" to discover indices.
    cb_indices = set()
    for key in request.form.keys():
        if key.startswith('cb_') and key.endswith('_item_name'):
            idx = key[len('cb_'):-len('_item_name')]
            if idx.isdigit():
                cb_indices.add(int(idx))

    for i in sorted(cb_indices):
        item_name   = f(f"cb_{i}_item_name") or ''
        item_number = f(f"cb_{i}_item_number") or ''

        cb_missing  = bool(f(f"cb_{i}_missing"))
        cb_redtag   = bool(f(f"cb_{i}_redtag"))
        cb_complete = bool(f(f"cb_{i}_complete"))

        miss_qty = parse_qty_from_text(f(f"cb_{i}_note_missing"))
        red_qty  = parse_qty_from_text(f(f"cb_{i}_note_redtag"))

        if cb_missing and miss_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Missing',
                note=f(f"cb_{i}_note_missing") or "",
                quantity=miss_qty,
                category='Extra Tooling'
            )
            responses.append(r); flagged.append(r)

        if cb_redtag and red_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Red Tag',
                note=f(f"cb_{i}_note_redtag") or "",
                quantity=red_qty,
                category='Extra Tooling'
            )
            responses.append(r); flagged.append(r)

        if cb_complete:
            responses.append(InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Complete',
                note='',
                quantity=0,
                category='Extra Tooling'
            ))

    if responses:
        db.session.add_all(responses)

    # Create an invoice record (file optional)
    if flagged:
        try:
            invoice_path = generate_invoice(trailer.id, flagged) or ""
        except Exception:
            current_app.logger.exception("Invoice generation failed; proceeding without file.")
            invoice_path = ""
        db.session.add(Invoice(trailer_id=trailer.id, file_path=invoice_path))
    else:
        db.session.add(Invoice(trailer_id=trailer.id, file_path=""))

    trailer.status = 'Completed'
    db.session.commit()

    flash('Inventory submitted. Trailer marked Completed and invoice recorded.', 'success')
    return redirect(url_for('inventory.pull_list', trailer_id=trailer.id))
