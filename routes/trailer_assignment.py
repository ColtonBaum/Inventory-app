# routes/trailer_assignment.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import Trailer
from database import db
from utils.tooling_lists import tooling_lists  # for rendering dynamic options

trailer_assignment_bp = Blueprint('trailer_assignment', __name__)

# Handle updates that POST to /trailer/<id>
@trailer_assignment_bp.route('/trailer/<int:trailer_id>', methods=['POST'])
def update_trailer_post(trailer_id):
    t = Trailer.query.get_or_404(trailer_id)

    # Read fields safely; ignore missing ones
    job_name        = (request.form.get('job_name') or '').strip() or t.job_name
    job_number      = (request.form.get('job_number') or '').strip() or t.job_number
    location        = (request.form.get('location') or '').strip() or t.location
    assigned_user   = (request.form.get('assigned_user') or '').strip() or t.assigned_user
    foreman_name    = (request.form.get('foreman_name') or '').strip() or t.foreman_name
    tooling_list    = (request.form.get('tooling_list_name') or '').strip() or t.tooling_list_name
    status          = (request.form.get('status') or '').strip() or t.status

    # Optional: handle extra tooling rows if your edit form posts them
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

    # Apply updates
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

    # Send the user back to the trailer detail page (which handles GET /trailer/<id>)
    return redirect(f'/trailer/{t.id}')

    # GET – render the form
    list_options = list(tooling_lists.keys())  # e.g. ["Standard Trailer", "Semi Trailer", ...]
    return render_template('assign_trailer.html', list_options=list_options)


# NEW: Dedicated POST endpoint to update a trailer from the detail page form.
# This avoids conflicts with any existing GET /trailer/<id> route in another blueprint.
@trailer_assignment_bp.route('/trailer/<int:trailer_id>/update', methods=['POST'])
def trailer_update(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)

    # Read fields you submit from the trailer detail page form.
    # Adjust names to exactly match your template's <input name="...">.
    trailer.location = (request.form.get('location') or trailer.location or '').strip()
    trailer.assigned_user = (request.form.get('assigned_user') or '').strip() or None
    trailer.status = (request.form.get('status') or trailer.status or 'Pending').strip()

    # If your trailer detail form can change job info:
    if 'job_name' in request.form:
        trailer.job_name = (request.form.get('job_name') or trailer.job_name or '').strip()
    if 'job_number' in request.form:
        trailer.job_number = (request.form.get('job_number') or trailer.job_number or '').strip()

    # Optional: update extra tooling entries if your detail form includes them
    enable_credit_back = request.form.get('enable_credit_back')
    if enable_credit_back is not None:
        raw        = request.form.to_dict(flat=False)
        names      = raw.get('extra_tooling_items[][item_name]', []) or raw.get('extra_tooling_items[item_name][]', [])
        numbers    = raw.get('extra_tooling_items[][item_number]', []) or raw.get('extra_tooling_items[item_number][]', [])
        quantities = raw.get('extra_tooling_items[][quantity]', []) or raw.get('extra_tooling_items[quantity][]', [])
        categories = raw.get('extra_tooling_items[][category]', []) or raw.get('extra_tooling_items[category][]', [])
        extra_tooling_data = []
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
        trailer.extra_tooling = extra_tooling_data or None

    db.session.commit()
    flash('Trailer updated.', 'success')

    # Redirect back to the detail page (adjust endpoint if your GET lives elsewhere)
    return redirect(url_for('inventory.trailer_detail', trailer_id=trailer_id))
