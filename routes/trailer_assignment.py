# routes/trailer_assignment.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import Trailer, InventoryResponse, Invoice
from database import db
from utils.tooling_lists import tooling_lists, get_tooling_list
from utils.invoice_generator import generate_invoice
import re  # <-- for parsing integers out of free-text

trailer_assignment_bp = Blueprint('trailer_assignment', __name__)

# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
_int_re = re.compile(r"(-?\d+)")

def parse_first_int(s, default=0):
    """
    Return the first integer found in a text string like '2 grinders'.
    If none found, return default (0).
    """
    if not s:
        return default
    m = _int_re.search(str(s))
    return int(m.group(1)) if m else default

def f(form, name, default=None):
    return form.get(name, default)

# ---------------------------------------------------------------------
# CREATE / ASSIGN
# ---------------------------------------------------------------------
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

        ln25_val = (request.form.get('ln_25s') or
                    request.form.get('lN-25s') or
                    request.form.get('LN_25') or '').strip() or None

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

# ---------------------------------------------------------------------
# UPDATE (compat metadata)
# ---------------------------------------------------------------------
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

# ---------------------------------------------------------------------
# UPDATE (submission) — uses free-text fields for Missing/Red Tag with qty parsing
# ---------------------------------------------------------------------
@trailer_assignment_bp.route('/trailer/<int:trailer_id>/update', methods=['POST'], strict_slashes=False)
@trailer_assignment_bp.route('/trailer/<int:trailer_id>/update/', methods=['POST'], strict_slashes=False)
def trailer_update(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)

    submitted_by = (f(request.form, 'submitted_by') or f(request.form, 'assigned_user') or '').strip()
    if submitted_by:
        trailer.assigned_user = submitted_by

    ln25_val = (f(request.form, 'ln_25s') or f(request.form, 'lN-25s') or f(request.form, 'LN_25') or '').strip()
    if ln25_val:
        for attr in ('ln_25s', 'lN_25s', 'LN_25'):
            if hasattr(trailer, attr):
                setattr(trailer, attr, ln25_val)
                break

    if 'location' in request.form:
        trailer.location = (f(request.form, 'location') or trailer.location or '').strip()
    if 'status' in request.form:
        trailer.status = (f(request.form, 'status') or trailer.status or 'Pending').strip()
    if 'job_name' in request.form:
        trailer.job_name = (f(request.form, 'job_name') or trailer.job_name or '').strip()
    if 'job_number' in request.form:
        trailer.job_number = (f(request.form, 'job_number') or trailer.job_number or '').strip()

    # fresh submission: wipe old responses
    InventoryResponse.query.filter_by(trailer_id=trailer.id).delete()

    list_name = (trailer.tooling_list_name or trailer.inventory_type or "").strip()
    tooling_list = get_tooling_list(list_name) or []

    responses = []
    flagged_items = []

    # ---------- main inventory ----------
    for item in tooling_list:
        item_number = item.get('Item Number') or item.get('itemNumber') or ''
        if not item_number:
            continue
        item_name   = item.get('Item Name')   or item.get('itemName')   or ''
        category    = item.get('Category')    or item.get('category')   or 'General'

        # checkboxes
        is_missing = bool(f(request.form, f"{item_number}_status_missing"))
        is_redtag  = bool(f(request.form, f"{item_number}_status_redtag"))
        is_complete= bool(f(request.form, f"{item_number}_status_complete"))

        # free-text fields user typed (e.g., "2 grinders")
        miss_text = (f(request.form, f"{item_number}_qty_missing", "") or "").strip()
        red_text  = (f(request.form, f"{item_number}_qty_redtag",  "") or "").strip()

        # use first integer found for counts
        miss_qty = parse_first_int(miss_text, default=0)
        red_qty  = parse_first_int(red_text,  default=0)

        # record rows only when checked AND qty>0, store the full text in note
        if is_missing and miss_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Missing',
                note=miss_text,            # keep what the user typed
                quantity=miss_qty,         # numeric count for pull list
                category=category
            )
            responses.append(r)
            flagged_items.append(r)

        if is_redtag and red_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Red Tag',
                note=red_text,
                quantity=red_qty,
                category=category
            )
            responses.append(r)
            flagged_items.append(r)

        # Optional: keep "Complete" entry with 0 for history (no effect on pull list)
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

    # ---------- extra tooling (credit-back) ----------
    credit_back = trailer.extra_tooling or []
    extra_responses = []
    for i, item in enumerate(credit_back):
        item_name   = item.get('item_name') or item.get('name') or ''
        item_number = item.get('item_number') or item.get('number') or ''

        cb_missing  = bool(f(request.form, f"cb_{i}_missing"))
        cb_redtag   = bool(f(request.form, f"cb_{i}_redtag"))
        cb_complete = bool(f(request.form, f"cb_{i}_complete"))

        miss_text = (f(request.form, f"cb_{i}_qty_missing", "") or "").strip()
        red_text  = (f(request.form, f"cb_{i}_qty_redtag",  "") or "").strip()

        miss_qty = parse_first_int(miss_text, default=0)
        red_qty  = parse_first_int(red_text,  default=0)

        if cb_missing and miss_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Missing',
                note=miss_text,
                quantity=miss_qty,
                category='Extra Tooling'
            )
            extra_responses.append(r)
            flagged_items.append(r)

        if cb_redtag and red_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Red Tag',
                note=red_text,
                quantity=red_qty,
                category='Extra Tooling'
            )
            extra_responses.append(r)
            flagged_items.append(r)

        if cb_complete:
            extra_responses.append(InventoryResponse(
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
    if extra_responses:
        db.session.add_all(extra_responses)

    # create invoice row (file path optional)
    if flagged_items:
        try:
            invoice_path = generate_invoice(trailer.id, flagged_items) or ""
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
