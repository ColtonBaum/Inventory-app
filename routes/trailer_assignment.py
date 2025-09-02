# routes/trailer_assignment.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import Trailer, InventoryResponse, Invoice
from database import db
from utils.tooling_lists import tooling_lists, get_tooling_list
from utils.invoice_generator import generate_invoice  # for invoice PDF/HTML generation

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

        # Optional: extra tooling credit-back items
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
        db.session.add(t)
        db.session.commit()

        flash('Trailer assigned.', 'success')
        return redirect(url_for('inventory.dashboard'))

    # GET – render the form
    list_options = list(tooling_lists.keys())  # e.g. ["Standard Trailer", "Semi Trailer", ...]
    return render_template('assign_trailer.html', list_options=list_options)


# -----------------------------------------------------------------------------
# UPDATE (compat) — accept POSTs to /trailer/<id> from the detail page form
# (Lightweight metadata update only; does NOT process inventory submission.)
# -----------------------------------------------------------------------------
@trailer_assignment_bp.route('/trailer/<int:trailer_id>', methods=['POST'], strict_slashes=False)
def update_trailer_post(trailer_id):
    t = Trailer.query.get_or_404(trailer_id)

    # Read fields safely; ignore missing ones
    job_name        = (request.form.get('job_name') or '').strip() or t.job_name
    job_number      = (request.form.get('job_number') or '').strip() or t.job_number
    location        = (request.form.get('location') or '').strip() or t.location

    # prefer submitted_by if present; else assigned_user; else keep existing
    submitted_by    = (request.form.get('submitted_by') or '').strip()
    assigned_user   = (request.form.get('assigned_user') or submitted_by or '').strip() or t.assigned_user

    foreman_name    = (request.form.get('foreman_name') or '').strip() or t.foreman_name
    tooling_list    = (request.form.get('tooling_list_name') or '').strip() or t.tooling_list_name
    status          = (request.form.get('status') or '').strip() or t.status

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
    submitted_by = (request.form.get('submitted_by') or '').strip()
    if submitted_by:
        trailer.assigned_user = submitted_by

    # Basic meta fields (if present in your form)
    if 'location' in request.form:
        trailer.location = (request.form.get('location') or trailer.location or '').strip()
    if 'status' in request.form:
        trailer.status = (request.form.get('status') or trailer.status or 'Pending').strip()
    if 'job_name' in request.form:
        trailer.job_name = (request.form.get('job_name') or trailer.job_name or '').strip()
    if 'job_number' in request.form:
        trailer.job_number = (request.form.get('job_number') or trailer.job_number or '').strip()

    # ----- MAIN SUBMISSION: parse all items and create responses -----
    # Clear existing responses for this trailer (fresh submission)
    InventoryResponse.query.filter_by(trailer_id=trailer.id).delete()

    list_name = (trailer.tooling_list_name or trailer.inventory_type or "").strip()
    tooling_list = get_tooling_list(list_name) or []

    responses = []
    flagged_items = []  # for invoice: Missing/Red Tag

    # Regular tooling items
    for item in tooling_list:
        item_number = item['Item Number']
        item_name = item['Item Name']
        category = item.get('Category', 'General')
        quantity = request.form.get(f"{item_number}_quantity", item.get('Quantity', 0))

        for key, label in [
            (f"{item_number}_status_missing",  "Missing"),
            (f"{item_number}_status_redtag",   "Red Tag"),
            (f"{item_number}_status_complete", "Complete"),
        ]:
            if request.form.get(key):
                note_key = f"{item_number}_note_{label.lower().replace(' ', '')}"
                note = request.form.get(note_key, '')
                r = InventoryResponse(
                    trailer_id=trailer.id,
                    item_number=item_number,
                    item_name=item_name,
                    status=label,
                    note=note,
                    quantity=int(quantity) if str(quantity).isdigit() else 0,
                    category=category
                )
                responses.append(r)
                if label in ('Missing', 'Red Tag'):
                    flagged_items.append(r)

    # Extra tooling (credit-back) stored on the trailer as dicts with item_name/item_number/quantity
    credit_back = trailer.extra_tooling or []
    extra_responses = []
    for i, item in enumerate(credit_back):
        item_name = item.get('item_name') or item.get('name') or ''
        item_number = item.get('item_number') or item.get('number') or ''
        quantity = request.form.get(f"cb_{i}_quantity", item.get('quantity', 0))

        for key, label in [
            (f"cb_{i}_missing",  "Missing"),
            (f"cb_{i}_redtag",   "Red Tag"),
            (f"cb_{i}_complete", "Complete"),
        ]:
            if request.form.get(key):
                note_key = f"cb_{i}_note_{label.lower().replace(' ', '')}"
                note = request.form.get(note_key, '')
                r = InventoryResponse(
                    trailer_id=trailer.id,
                    item_number=item_number,
                    item_name=item_name,
                    status=label,
                    note=note,
                    quantity=int(quantity) if str(quantity).isdigit() else 0,
                    category='Extra Tooling'
                )
                extra_responses.append(r)
                if label in ('Missing', 'Red Tag'):
                    flagged_items.append(r)

    if responses:
        db.session.add_all(responses)
    if extra_responses:
        db.session.add_all(extra_responses)

    # Create invoice record (with file if there are flagged items)
    if flagged_items:
        invoice_path = generate_invoice(trailer.id, flagged_items) or ""
        db.session.add(Invoice(trailer_id=trailer.id, file_path=invoice_path))
    else:
        db.session.add(Invoice(trailer_id=trailer.id, file_path=""))

    # Mark trailer completed on submit
    trailer.status = 'Completed'
    db.session.commit()

    flash('Inventory submitted. Trailer marked Completed and invoice recorded.', 'success')
    # Go to pull list (the HTML summary)
    return redirect(url_for('inventory.pull_list', trailer_id=trailer.id))
