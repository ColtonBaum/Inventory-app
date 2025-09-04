# routes/trailer_assignment.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import Trailer, InventoryResponse, Invoice
from database import db
from utils.tooling_lists import tooling_lists, get_tooling_list
from utils.invoice_generator import generate_invoice  # keeps returning file path (or "")

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
# UPDATE (submission) — parse exactly what the form posted
# -----------------------------------------------------------------------------
@trailer_assignment_bp.route('/trailer/<int:trailer_id>/update', methods=['POST'], strict_slashes=False)
@trailer_assignment_bp.route('/trailer/<int:trailer_id>/update/', methods=['POST'], strict_slashes=False)
def trailer_update(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)

    submitted_by = (request.form.get('submitted_by') or request.form.get('assigned_user') or '').strip()
    if submitted_by:
        trailer.assigned_user = submitted_by

    ln25_val = (request.form.get('ln_25s') or request.form.get('lN-25s') or request.form.get('LN_25') or '').strip()
    if ln25_val:
        for attr in ('ln_25s', 'lN_25s', 'LN_25'):
            if hasattr(trailer, attr):
                setattr(trailer, attr, ln25_val)
                break

    if 'location' in request.form:
        trailer.location = (request.form.get('location') or trailer.location or '').strip()
    if 'status' in request.form:
        trailer.status = (request.form.get('status') or trailer.status or 'Pending').strip()
    if 'job_name' in request.form:
        trailer.job_name = (request.form.get('job_name') or trailer.job_name or '').strip()
    if 'job_number' in request.form:
        trailer.job_number = (request.form.get('job_number') or trailer.job_number or '').strip()

    # Fresh submission: clear previous responses
    InventoryResponse.query.filter_by(trailer_id=trailer.id).delete()

    f = request.form.get

    def to_int_or_zero(v):
        try:
            return int(v)
        except Exception:
            return 0

    # ----- DEBUG: log posted keys (first 25)
    try:
        posted_keys = list(request.form.keys())
        current_app.logger.info(
            "[SUBMIT] trailer=%s posted_keys_count=%d sample=%s",
            trailer.id, len(posted_keys), posted_keys[:25]
        )
    except Exception:
        pass

    # Resolve tooling list
    list_name = (trailer.tooling_list_name or trailer.inventory_type or "").strip()
    tooling_list = get_tooling_list(list_name) or []

    # Build candidate bases from BOTH hidden fields and known item numbers
    bases = set()
    for key in request.form.keys():
        if key.endswith('_item_name'):
            bases.add(key[:-len('_item_name')])
    for item in tooling_list:
        num = item.get('Item Number') or item.get('itemNumber') or ''
        if num:
            bases.add(str(num))

    # ----- DEBUG: base count
    try:
        current_app.logger.info("[SUBMIT] trailer=%s base_candidates=%d", trailer.id, len(bases))
    except Exception:
        pass

    responses = []
    flagged_items = []

    # MAIN inventory
    for base in bases:
        # Prefer names coming from the form when possible
        item_name = f(f"{base}_item_name")
        category  = f(f"{base}_category")

        # If hidden fields missing, try to look up from tooling_list
        if item_name is None or category is None:
            for it in tooling_list:
                if str(it.get('Item Number') or it.get('itemNumber') or '') == base:
                    item_name = item_name or it.get('Item Name') or it.get('itemName') or ''
                    category  = category  or it.get('Category')  or it.get('category')  or 'General'
                    break

        item_name = item_name or ''
        category  = category or 'General'

        # Checkbox flags
        is_missing  = bool(f(f"{base}_status_missing"))
        is_redtag   = bool(f(f"{base}_status_redtag"))
        is_complete = bool(f(f"{base}_status_complete"))

        # Numeric quantities (exactly as entered)
        miss_qty = to_int_or_zero(f(f"{base}_qty_missing") or "0")
        red_qty  = to_int_or_zero(f(f"{base}_qty_redtag")  or "0")

        # DEBUG per-base
        try:
            current_app.logger.debug(
                "[SUBMIT] base=%r missing=%s miss_qty=%s redtag=%s red_qty=%s",
                base, is_missing, miss_qty, is_redtag, red_qty
            )
        except Exception:
            pass

        if is_missing and miss_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(base),
                item_name=item_name,
                status='Missing',
                note='',
                quantity=miss_qty,
                category=category
            )
            responses.append(r)
            flagged_items.append(r)

        if is_redtag and red_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(base),
                item_name=item_name,
                status='Red Tag',
                note='',
                quantity=red_qty,
                category=category
            )
            responses.append(r)
            flagged_items.append(r)

        if is_complete:
            responses.append(InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(base),
                item_name=item_name,
                status='Complete',
                note='',
                quantity=0,
                category=category
            ))

    # EXTRA tooling (credit-back)
    credit_back = trailer.extra_tooling or []
    extra_responses = []
    for i, item in enumerate(credit_back):
        item_name   = item.get('item_name') or item.get('name') or ''
        item_number = item.get('item_number') or item.get('number') or ''

        cb_missing  = bool(f(f"cb_{i}_missing"))
        cb_redtag   = bool(f(f"cb_{i}_redtag"))
        cb_complete = bool(f(f"cb_{i}_complete"))

        miss_qty = to_int_or_zero(f(f"cb_{i}_qty_missing") or "0")
        red_qty  = to_int_or_zero(f(f"cb_{i}_qty_redtag")  or "0")

        try:
            current_app.logger.debug(
                "[SUBMIT][CB] idx=%d num=%r missing=%s miss_qty=%s redtag=%s red_qty=%s",
                i, item_number, cb_missing, miss_qty, cb_redtag, red_qty
            )
        except Exception:
            pass

        if cb_missing and miss_qty > 0:
            r = InventoryResponse(
                trailer_id=trailer.id,
                item_number=str(item_number),
                item_name=item_name,
                status='Missing',
                note='',
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
                note='',
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

    # DEBUG: totals written
    try:
        current_app.logger.info(
            "[SUBMIT] trailer=%s wrote main=%d extra=%d flagged=%d",
            trailer.id, len(responses), len(extra_responses), len(flagged_items)
        )
    except Exception:
        pass

    # Invoice row
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
