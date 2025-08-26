# routes/trailer_assignment.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import Trailer
from database import db
from utils.tooling_lists import tooling_lists  # for rendering dynamic options

trailer_assignment_bp = Blueprint('trailer_assignment', __name__)

@trailer_assignment_bp.route('/assign_trailer', methods=['GET', 'POST'])
def assign_trailer():
    if request.method == 'POST':
        # Required fields
        job_name   = (request.form.get('job_name') or '').strip()
        job_number = (request.form.get('job_number') or '').strip()
        # 🔁 read the correct field name from the form
        tooling_list = (request.form.get('tooling_list_name') or '').strip()

        # Optional fields
        location      = (request.form.get('location') or '').strip()
        assigned_user = (request.form.get('assigned_user') or '').strip() or None
        foreman_name  = (request.form.get('foreman_name') or '').strip() or None
        external_id   = (request.form.get('trailer_id') or '').strip() or None  # external trailer ID

        # Optional: extra tooling credit-back items
        extra_tooling_data = []
        enable_credit_back = request.form.get('enable_credit_back')
        if enable_credit_back:
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

        # Create and persist the trailer
        t = Trailer(
            trailer_id=external_id,
            job_name=job_name,
            job_number=job_number,
            location=location,
            tooling_list_name=tooling_list,  # used to choose which list to render
            inventory_type=tooling_list,     # mirrored for compatibility
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
