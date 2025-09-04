# routes/trailer_assignment.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import Trailer, InventoryResponse, Invoice
from database import db
from utils.tooling_lists import tooling_lists, get_tooling_list
from utils.invoice_generator import generate_invoice  # keep import (even if it returns HTML path)

trailer_assignment_bp = Blueprint('trailer_assignment', __name__)

# -----------------------------------------------------------------------------
# CREATE / ASSIGN — show form and create a trailer
# -----------------------------------------------------------------------------
@trailer_assignment_bp.route('/assign_trailer', methods=['GET', 'POST'], endpoint='assign_trailer')
def assign_trailer():
    if request.method == 'POST':
        # Required fields
        job_name     = (request.form.get('job_name') or '').strip()
        job_number   = (request.form.get('job_number') or '').strip()
        tooling_list = (request.form.get('tooling_list_name') or '').strip()

        # Optional fields
        location       = (request.form.get('location') or '').strip()
        submitted_by   = (request.form.get('submitted_by') or '').strip()
        assigned_user  = (request.form.get('assigned_user') or submitted_by or '').strip() or None
        foreman_name   = (request.form.get('foreman_name') or '').strip() or None
        external_id    = (request.form.get('trailer_id') or '').strip() or None  # external trailer ID

        # Capture LN-25 serials if provided (supports a few name variants from the UI)
        ln25_val = (request.form.get('ln_25s') or
                    request.form.get('lN-25s') or
                    request.form.get('LN_25') or '').strip() or None

        # Optional: extra tooling credit-back items coming from dynamic rows
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

        # Persist new trailer
        t = Trailer(
            trailer_id=external_id,
            job_name=job_name,
            job_number=job_number,
            location=location,
            tooling_list_name=tooling_list,
            inventory_type=tooling_list,  # mirrored for compatibility
            assigned_user=assigned_user,
            status='Pending',
            extra_tooling=extra_tooling_data or None,
            foreman_name=foreman_name
        )
        # If model has an LN-25 field, save it
        if ln25_val:
            for attr in ('ln_25s', 'lN_25s', 'LN_25'):
                if hasattr(t, attr):
                    setattr(t, attr, ln25_val)
                    break

        db.session.add(t)
        db.session.commit()

        flash('Trailer assigned.', 'success')
        return redirect(url_for('inventory.dashboard'))

    # GET – render the form
    list_options = list(tooling_lists.keys())  # e.g. ["Standard Trailer", "Semi Trailer", ...]
    return render_template('assign_trailer.html', list_options=list_options)


# -----------------------------------------------------------------------------
# UPDATE (compat metadata) — POST /trailer/<id> from detail page (no inventory)
# -----------------------------------------------------------------------------
@trailer_assignment_bp.route('/trailer/<int:trailer_id>', methods=['POST'], strict_slashes=False)
def update_trailer_post(trailer_id):
    t = Trailer.query.get_or_404(trailer_id)

    # Read fields safely; ignore missing ones
    job_name        = (request.form.get('job_name') or '').strip() or t.job_name
    job_number      = (request.form.get('job_number') or '').strip() or t.job_number
    location        = (request.form.get('location') or '').strip() or t.location

    submitted_by    = (request.form.get('submitted_by') or '').strip()
    assigned_user   = (request.form.get('assigned_user') or submitted_by or '').strip() or t.assigned_user

    foreman_name    = (request.form.get('foreman_name') or '').strip() or t.foreman_name
    tooling_list    = (request.form.get('tooling_list_name') or '').strip() or t.tooling_list_name
    status          = (request.form.get('status') or '').strip() or t.status

    # Optional LN-25
    ln25_val = (request.form.get('ln_25s') or request.form.get('lN-25s') or request.form.get('LN_25') or '').strip()
    if ln25_val:
        for attr in ('ln_25s', 'lN_25s', 'LN_25'):
            if hasattr(t, attr):
                setattr(t, attr, ln25_val)
                break

    # Optional: handle extra tooling rows if your form posts them
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

    # Apply & save
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
# UPDATE (submission) — FULL inventory submission from inventory_form.html
# Accept both /trailer/<id>/update and /trailer/<id>/update/
# -----------------------------------------------------------------------------
@trailer_assignment_bp.route('/trailer/<int:trailer_id>/update', methods=['POST'], strict_slashes=False)
@trailer_assignment_bp.route('/trailer/<int:trailer_id>/update/', methods=['POST'], strict_slashes=False)
def trailer_update(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)

    # Optional: person submitting the form
    submitted_by = (request.form.get('submitted_by') or request.form.get('assigned_user') or '').strip()
    if submitted_by:
        trailer.assigned_user = submitted_by

    # LN-25 from form (if present)
    ln25_val = (request.form.get('ln_25s') or request.form.get('lN-25s') or request.form.get('LN_25') or '').strip()
    if ln25_val:
        for attr in ('ln_25s', 'lN_25s', 'LN_25'):
            if hasattr(trailer, attr):
                setattr(trailer, attr, ln25_val)
                break

    # Basic meta fields (if present in your form)
    if 'location' in request.form:
        trailer.location = (request.form.get('location') or trailer.location or '').strip()
    if 'status' in request.form:
        trailer.status = (request.form.get('status') or trailer.status or 'Pending').strip()
    if 'job_name' in request.form:
        trailer.job_name = (request.form.get('job_name') or trailer.job_name or '').strip()
    if 'job_number' in request.form:
        trailer.job_number = (request.form.get('job_number') or trailer.job_number or '').strip()

    # ---------- MAIN SUBMISSION ----------
    # Clear existing responses for this trailer (fresh submission)
    InventoryResponse.query.filter_by(trailer_id=trailer.id).delete()

    list_name = (trailer.tooling_list_name or trailer.inventory_type or "").strip()
    tooling_list = get_tooling_list(list_name) or []

    def to_int(val, default=0):
        try:
            return int(str(val).strip())
        except Exception:
            return default

    def f(name, default=None):
        return request.form.get(name, default)

    responses = []
    flagged_items = []  # for invoice: Missing/Red Tag

    # Regular tooling items
    for item in tooling_list:
        item_number = item.get('Item Number') or item.get('itemNumber') or ''
        if not item_number:
            continue
        item_name   = item.get('Item Name')   or item.get('itemName')   or ''
        category    = item.get('Category')    or item.get('category')   or 'General'
        expected_q  = item.get('Quantity')    or item.get('quantity')   or 0

        # Quantity from form (fall back to expected)
        posted_qty = f(f"{item_number}_quantity")
        qty = to_int(posted_qty, default=to_int(expected_q, 0))

        # Support both select and checkbox styles
        statuses = []
        sel = (f(f"{item_number}_status") or '').strip()
        if sel in ('Missing', 'Red Tag', 'Complete'):
            statuses.append(sel)
        else:
            if f(f"{item_number}_status_missing"):
                statuses.append('Missing')
            if f(f"{item_number}_status_redtag"):
                statuses.append('Red Tag')
            if f(f"{item_number}_status_complete"):
                statuses.append('Complete')

        # Notes (support both specific and generic)
        note_missing  = f(f"{item_number}_note_missing", "") if 'Missing' in statuses else ""
        note_redtag   = f(f"{item_number}_note_redtag",  "") if 'Red Tag' in statuses else ""
        note_complete = f(f"{item_number}_note_complete", "") if 'Complete' in statuses else ""
        generic_note  = f(f"{item_number}_note", "")

        for status in statuses:
            note = generic_note
            if status == 'Missing':
                note = note_missing or generic_note
            elif status == 'Red Tag':
                note = note_redtag or generic_note
            elif status == 'Complete':
                note = note_complete or generic_note

            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status=status,
                note=note or "",
                quantity=qty,
                category=category
            )
            responses.append(r)
            if status in ('Missing', 'Red Tag'):
                flagged_items.append(r)

    # Extra tooling (credit-back) stored as dicts with item_name/item_number/quantity
    credit_back = trailer.extra_tooling or []
    extra_responses = []
    for i, item in enumerate(credit_back):
        item_name   = item.get('item_name') or item.get('name') or ''
        item_number = item.get('item_number') or item.get('number') or ''
        expected_q  = item.get('quantity', 0)

        qty_val = to_int(f(f"cb_{i}_quantity"), default=to_int(expected_q, 0))

        # Support both checkbox and select styles
        cb_missing  = f(f"cb_{i}_missing")
        cb_redtag   = f(f"cb_{i}_redtag")
        cb_complete = f(f"cb_{i}_complete")
        sel = (f(f"extra_{i}_status") or '').strip()
        if sel in ('Missing', 'Red Tag', 'Complete'):
            if sel == 'Missing':
                cb_missing = 'on'
            elif sel == 'Red Tag':
                cb_redtag = 'on'
            elif sel == 'Complete':
                cb_complete = 'on'

        def note_for(label):
            return f(f"cb_{i}_note_{label}", "")

        for status, onflag in (('Missing', cb_missing), ('Red Tag', cb_redtag), ('Complete', cb_complete)):
            if onflag:
                r = InventoryResponse(
                    trailer_id=trailer.id,
                    item_number=str(item_number),
                    item_name=item_name,
                    status=status,
                    note=note_for(status.lower().replace(' ', '')),
                    quantity=qty_val,
                    category='Extra Tooling'
                )
                extra_responses.append(r)
                if status in ('Missing', 'Red Tag'):
                    flagged_items.append(r)

    if responses:
        db.session.add_all(responses)
    if extra_responses:
        db.session.add_all(extra_responses)

    # Create invoice DB row (optionally with generated file path)
    if flagged_items:
        try:
            invoice_path = generate_invoice(trailer.id, flagged_items) or ""
        except Exception:
            current_app.logger.exception("Invoice generation failed; proceeding without file.")
            invoice_path = ""
        db.session.add(Invoice(trailer_id=trailer.id, file_path=invoice_path))
    else:
        db.session.add(Invoice(trailer_id=trailer.id, file_path=""))

    # Mark trailer completed on submit
    trailer.status = 'Completed'
    db.session.commit()

    flash('Inventory submitted. Trailer marked Completed and invoice recorded.', 'success')
    # Go to pull list (the HTML summary)
    return redirect(url_for('inventory.pull_list', trailer_id=trailer.id))
