# routes/billing.py
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session, current_app, make_response, abort
)
from models import ItemPrice, Trailer, InventoryResponse, WarehouseProduct, WarehouseOrder, WarehouseOrderLine
from database import db
from utils.tooling_lists import get_tooling_list
from functools import wraps
from collections import defaultdict
from datetime import datetime
import io

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')


# ---------- Auth ----------
def billing_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('billing_auth'):
            return redirect(url_for('billing.login', next=request.url))
        return f(*args, **kwargs)
    return decorated


@billing_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if pw == current_app.config.get('BILLING_PASSWORD', ''):
            session['billing_auth'] = True
            next_url = request.args.get('next') or url_for('billing.billing_dashboard')
            return redirect(next_url)
        flash('Incorrect password.', 'danger')
    return render_template('billing_login.html')


@billing_bp.route('/logout')
def logout():
    session.pop('billing_auth', None)
    flash('Logged out of billing.', 'info')
    return redirect(url_for('inventory.dashboard'))


# ---------- Dashboard ----------
@billing_bp.route('/')
@billing_required
def billing_dashboard():
    q = (request.args.get('q') or '').strip().lower()
    trailers = Trailer.query.filter(Trailer.status == 'Completed').order_by(Trailer.id.desc()).all()
    if q:
        trailers = [t for t in trailers if q in (t.job_name or '').lower()
                     or q in (t.job_number or '').lower()
                     or q in str(t.id)]
    return render_template('billing_dashboard.html', trailers=trailers, q=q)


# ---------- Pricing Management ----------
@billing_bp.route('/pricing', methods=['GET', 'POST'])
@billing_required
def pricing():
    if request.method == 'POST':
        # Bulk update prices
        for key, val in request.form.items():
            if key.startswith('price_'):
                item_number = key[6:]  # strip 'price_'
                try:
                    price_val = float(val) if val.strip() else 0.0
                except ValueError:
                    price_val = 0.0

                existing = ItemPrice.query.filter_by(item_number=item_number).first()
                if existing:
                    existing.price = price_val
                else:
                    item_name = request.form.get(f'name_{item_number}', '')
                    db.session.add(ItemPrice(
                        item_number=item_number,
                        item_name=item_name,
                        price=price_val
                    ))
        db.session.commit()
        flash('Prices updated.', 'success')
        return redirect(url_for('billing.pricing'))

    # Build a master list of all items across all tooling lists + any already-priced items
    from utils.tooling_lists import tooling_lists as all_lists
    all_items = {}  # item_number -> item_name
    for list_name, items in all_lists.items():
        for item in items:
            num = item.get('Item Number', '').strip()
            name = item.get('Item Name', '').strip()
            if num and num not in all_items:
                all_items[num] = name

    # Merge in any existing prices
    prices = {p.item_number: p for p in ItemPrice.query.all()}
    for num in prices:
        if num not in all_items:
            all_items[num] = prices[num].item_name or ''

    # Search filter
    q = (request.args.get('q') or '').strip().lower()

    # Build display rows
    rows = []
    for num, name in sorted(all_items.items(), key=lambda x: (x[1] or '').lower()):
        if q and q not in num.lower() and q not in name.lower():
            continue
        p = prices.get(num)
        rows.append({
            'item_number': num,
            'item_name': name,
            'price': p.price if p else 0.0,
        })

    return render_template('billing_pricing.html', rows=rows, q=q)


# ---------- Generate Billing Invoice for a Trailer ----------
@billing_bp.route('/invoice/<int:trailer_id>')
@billing_required
def generate_billing_invoice(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)

    # Get all responses for this trailer
    responses = InventoryResponse.query.filter_by(trailer_id=trailer_id).all()

    # Get the tooling list to know expected quantities
    list_name = (trailer.tooling_list_name or trailer.inventory_type or '').strip()
    tooling_list = get_tooling_list(list_name) or []

    # Build expected qty map
    expected_map = {}
    for item in tooling_list:
        num = item.get('Item Number', '').strip()
        expected_map[num] = {
            'item_name': item.get('Item Name', ''),
            'quantity': int(item.get('Quantity', 0)) if str(item.get('Quantity', 0)).isdigit() else 0,
        }

    # Build response status map
    response_map = defaultdict(lambda: {'missing': 0, 'redtag': 0, 'complete': False, 'note': ''})
    for r in responses:
        key = r.item_number
        if r.status == 'Missing':
            response_map[key]['missing'] += (r.quantity or 0)
            if r.note:
                response_map[key]['note'] = r.note
        elif r.status == 'Red Tag':
            response_map[key]['redtag'] += (r.quantity or 0)
            if r.note:
                response_map[key]['note'] = r.note
        elif r.status == 'Complete':
            response_map[key]['complete'] = True

    # Load prices
    price_map = {p.item_number: p.price for p in ItemPrice.query.all()}

    # Build line items — only items that are missing or red tagged
    line_items = []
    total = 0.0
    for num, info in expected_map.items():
        resp = response_map.get(num, {})
        missing_qty = resp.get('missing', 0)
        redtag_qty = resp.get('redtag', 0)
        billable_qty = missing_qty + redtag_qty
        if billable_qty <= 0:
            continue
        unit_price = price_map.get(num, 0.0)
        line_total = unit_price * billable_qty
        total += line_total
        line_items.append({
            'item_number': num,
            'item_name': info['item_name'],
            'missing_qty': missing_qty,
            'redtag_qty': redtag_qty,
            'billable_qty': billable_qty,
            'unit_price': unit_price,
            'line_total': line_total,
            'note': resp.get('note', ''),
        })

    # Also add extra tooling items
    extra_responses = [r for r in responses if (r.category or '').strip().lower() == 'extra tooling']
    extra_map = defaultdict(lambda: {'missing': 0, 'redtag': 0, 'item_name': '', 'note': ''})
    for r in extra_responses:
        key = r.item_number
        extra_map[key]['item_name'] = r.item_name
        if r.status == 'Missing':
            extra_map[key]['missing'] += (r.quantity or 0)
            if r.note:
                extra_map[key]['note'] = r.note
        elif r.status == 'Red Tag':
            extra_map[key]['redtag'] += (r.quantity or 0)
            if r.note:
                extra_map[key]['note'] = r.note

    for num, info in extra_map.items():
        billable_qty = info['missing'] + info['redtag']
        if billable_qty <= 0:
            continue
        unit_price = price_map.get(num, 0.0)
        line_total = unit_price * billable_qty
        total += line_total
        line_items.append({
            'item_number': num,
            'item_name': info['item_name'],
            'missing_qty': info['missing'],
            'redtag_qty': info['redtag'],
            'billable_qty': billable_qty,
            'unit_price': unit_price,
            'line_total': line_total,
            'note': info.get('note', ''),
        })

    line_items.sort(key=lambda x: (x['item_name'] or '').lower())

    return render_template(
        'billing_invoice.html',
        trailer=trailer,
        line_items=line_items,
        total=total,
        now=datetime.now,
    )


# ---------- Warehouse Stock ----------
@billing_bp.route('/warehouse')
@billing_required
def warehouse_inventory():
    q = (request.args.get('q') or '').strip().lower()
    products = WarehouseProduct.query.order_by(WarehouseProduct.item_name).all()
    if q:
        products = [p for p in products if q in (p.item_name or '').lower() or q in (p.item_number or '').lower()]
    low_stock = [p for p in products if p.quantity_on_hand <= p.reorder_point]
    return render_template('billing_inventory.html', products=products, low_stock=low_stock, q=q)


@billing_bp.route('/warehouse/product/<int:product_id>/edit', methods=['GET', 'POST'])
@billing_required
def edit_product(product_id):
    product = WarehouseProduct.query.get_or_404(product_id)
    if request.method == 'POST':
        product.item_name = request.form.get('item_name', product.item_name)
        product.quantity_on_hand = int(request.form.get('quantity_on_hand', 0) or 0)
        product.reorder_point = int(request.form.get('reorder_point', 0) or 0)
        try:
            product.unit_cost = float(request.form.get('unit_cost', 0) or 0)
        except ValueError:
            product.unit_cost = 0.0
        db.session.commit()
        flash('Product updated.', 'success')
        return redirect(url_for('billing.warehouse_inventory'))
    return render_template('billing_edit_product.html', product=product)


@billing_bp.route('/warehouse/product/add', methods=['POST'])
@billing_required
def add_product():
    item_number = (request.form.get('item_number') or '').strip()
    if not item_number:
        flash('Item number is required.', 'danger')
        return redirect(url_for('billing.warehouse_inventory'))
    existing = WarehouseProduct.query.filter_by(item_number=item_number).first()
    if existing:
        flash('A product with that item number already exists.', 'warning')
        return redirect(url_for('billing.warehouse_inventory'))
    p = WarehouseProduct(
        item_number=item_number,
        item_name=(request.form.get('item_name') or '').strip(),
        quantity_on_hand=int(request.form.get('quantity_on_hand', 0) or 0),
        reorder_point=int(request.form.get('reorder_point', 0) or 0),
        unit_cost=float(request.form.get('unit_cost', 0) or 0),
    )
    db.session.add(p)
    db.session.commit()
    flash('Product added.', 'success')
    return redirect(url_for('billing.warehouse_inventory'))


# ---------- Warehouse Orders ----------
@billing_bp.route('/warehouse/orders')
@billing_required
def warehouse_orders():
    status_filter = request.args.get('status', '')
    q = WarehouseOrder.query.order_by(WarehouseOrder.created_at.desc())
    if status_filter:
        q = q.filter(WarehouseOrder.status == status_filter)
    orders = q.all()
    trailers = {t.id: t for t in Trailer.query.all()}
    return render_template('billing_orders.html', orders=orders, trailers=trailers, status_filter=status_filter)


@billing_bp.route('/warehouse/orders/new', methods=['GET', 'POST'])
@billing_required
def new_order():
    if request.method == 'POST':
        trailer_id_raw = request.form.get('trailer_id') or None
        trailer_id = int(trailer_id_raw) if trailer_id_raw else None
        notes = (request.form.get('notes') or '').strip()
        order = WarehouseOrder(trailer_id=trailer_id, status='Pending', notes=notes)
        db.session.add(order)
        db.session.flush()  # get order.id

        item_numbers = request.form.getlist('item_number')
        item_names = request.form.getlist('item_name')
        quantities = request.form.getlist('quantity')
        for num, name, qty_raw in zip(item_numbers, item_names, quantities):
            num = num.strip()
            if not num:
                continue
            try:
                qty = int(qty_raw or 0)
            except ValueError:
                qty = 0
            if qty <= 0:
                continue
            line = WarehouseOrderLine(order_id=order.id, item_number=num, item_name=name.strip(), quantity=qty)
            db.session.add(line)
        db.session.commit()
        flash('Order created.', 'success')
        return redirect(url_for('billing.view_order', order_id=order.id))

    trailers = Trailer.query.order_by(Trailer.id.desc()).all()
    products = WarehouseProduct.query.order_by(WarehouseProduct.item_name).all()
    return render_template('billing_order_new.html', trailers=trailers, products=products)


@billing_bp.route('/warehouse/orders/<int:order_id>')
@billing_required
def view_order(order_id):
    order = WarehouseOrder.query.get_or_404(order_id)
    trailer = Trailer.query.get(order.trailer_id) if order.trailer_id else None
    return render_template('billing_order_view.html', order=order, trailer=trailer)


@billing_bp.route('/warehouse/orders/<int:order_id>/status', methods=['POST'])
@billing_required
def update_order_status(order_id):
    order = WarehouseOrder.query.get_or_404(order_id)
    new_status = request.form.get('status', order.status)
    if new_status in ('Pending', 'Fulfilled', 'Cancelled'):
        order.status = new_status
        db.session.commit()
        flash(f'Order status updated to {new_status}.', 'success')
    return redirect(url_for('billing.view_order', order_id=order_id))


# ---------- Tooling List Management ----------
@billing_bp.route('/tooling-lists')
@billing_required
def tooling_lists_index():
    from models import ToolingListItem
    from sqlalchemy import func
    # Get all unique list names with item counts
    counts = (db.session.query(ToolingListItem.list_name, func.count(ToolingListItem.id))
              .group_by(ToolingListItem.list_name)
              .order_by(ToolingListItem.list_name)
              .all())
    return render_template('billing_tooling_lists.html', list_counts=counts)


@billing_bp.route('/tooling-lists/<list_name>')
@billing_required
def tooling_list_detail(list_name):
    from models import ToolingListItem
    items = (ToolingListItem.query.filter_by(list_name=list_name)
             .order_by(ToolingListItem.sort_order, ToolingListItem.id).all())
    return render_template('billing_tooling_list_detail.html', list_name=list_name, items=items)


@billing_bp.route('/tooling-lists/<list_name>/add', methods=['POST'])
@billing_required
def tooling_list_add_item(list_name):
    from models import ToolingListItem
    item_number = (request.form.get('item_number') or '').strip()
    item_name = (request.form.get('item_name') or '').strip()
    category = (request.form.get('category') or 'General').strip()
    try:
        quantity = int(request.form.get('quantity') or 0)
    except ValueError:
        quantity = 0
    # Put new items at the end
    max_sort = db.session.query(db.func.max(ToolingListItem.sort_order)).filter_by(list_name=list_name).scalar() or 0
    db.session.add(ToolingListItem(list_name=list_name, item_number=item_number,
                                   item_name=item_name, category=category,
                                   quantity=quantity, sort_order=max_sort+1))
    db.session.commit()
    flash(f'Item added to {list_name}.', 'success')
    return redirect(url_for('billing.tooling_list_detail', list_name=list_name))


@billing_bp.route('/tooling-lists/item/<int:item_id>/edit', methods=['POST'])
@billing_required
def tooling_list_edit_item(item_id):
    from models import ToolingListItem
    item = ToolingListItem.query.get_or_404(item_id)
    item.item_number = (request.form.get('item_number') or item.item_number).strip()
    item.item_name = (request.form.get('item_name') or item.item_name).strip()
    item.category = (request.form.get('category') or item.category).strip()
    try:
        item.quantity = int(request.form.get('quantity') or item.quantity)
    except ValueError:
        pass
    db.session.commit()
    flash('Item updated.', 'success')
    return redirect(url_for('billing.tooling_list_detail', list_name=item.list_name))


@billing_bp.route('/tooling-lists/item/<int:item_id>/delete', methods=['POST'])
@billing_required
def tooling_list_delete_item(item_id):
    from models import ToolingListItem
    item = ToolingListItem.query.get_or_404(item_id)
    list_name = item.list_name
    db.session.delete(item)
    db.session.commit()
    flash('Item removed.', 'info')
    return redirect(url_for('billing.tooling_list_detail', list_name=list_name))


@billing_bp.route('/tooling-lists/new-list', methods=['POST'])
@billing_required
def tooling_list_create():
    list_name = (request.form.get('list_name') or '').strip()
    if not list_name:
        flash('List name is required.', 'danger')
        return redirect(url_for('billing.tooling_lists_index'))
    flash(f'List "{list_name}" created. Add items to it now.', 'success')
    return redirect(url_for('billing.tooling_list_detail', list_name=list_name))


# ---------- Warehouse Excel Import ----------
@billing_bp.route('/warehouse/import', methods=['GET', 'POST'])
@billing_required
def import_warehouse():
    if request.method == 'POST':
        f = request.files.get('file')
        if not f or not f.filename.endswith('.xlsx'):
            flash('Please upload a .xlsx file.', 'danger')
            return redirect(url_for('billing.import_warehouse'))

        try:
            import openpyxl
            wb = openpyxl.load_workbook(f, data_only=True)
            ws = wb.active
        except Exception as e:
            flash(f'Could not read Excel file: {e}', 'danger')
            return redirect(url_for('billing.import_warehouse'))

        # Scan up to 10 rows to find the actual header row
        ITEM_NUM_CANDIDATES = {
            'item number', 'item_number', 'item #', 'item no', 'part number', 'part #',
            'part no', 'sku', 'product number', 'product #', 'number', 'no', 'id',
            'item id', 'product id', 'code', 'item code', 'part code',
        }
        header_row_idx = None
        headers = []
        for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=10, values_only=True), start=1):
            row_vals = [(str(c or '').strip().lower()) for c in row]
            if any(v in ITEM_NUM_CANDIDATES for v in row_vals):
                header_row_idx = row_idx
                headers = row_vals
                break

        def find_col(candidates):
            for c in candidates:
                if c in headers:
                    return headers.index(c)
            return None

        col_num = find_col([
            'item number', 'item_number', 'item #', 'item no', 'part number', 'part #',
            'part no', 'sku', 'product number', 'product #', 'number', 'no', 'id',
            'item id', 'product id', 'code', 'item code', 'part code',
        ])
        col_name = find_col([
            'item name', 'item_name', 'product name', 'name', 'description', 'desc',
            'item description', 'product description', 'title',
        ])
        col_qty = find_col([
            'quantity', 'qty', 'on hand', 'quantity on hand', 'qty on hand',
            'stock', 'stock on hand', 'inventory', 'count', 'available', 'balance',
        ])
        col_price = find_col([
            'price', 'unit price', 'cost', 'unit cost', 'rate', 'each',
            'unit cost ($)', 'price ($)', 'cost ($)', 'sell price', 'list price',
        ])

        if col_num is None or header_row_idx is None:
            # Show all non-empty cell values from first 10 rows to help diagnose
            sample = []
            for row in ws.iter_rows(min_row=1, max_row=10, values_only=True):
                for cell in row:
                    v = str(cell or '').strip()
                    if v and v not in sample:
                        sample.append(v)
                if len(sample) > 20:
                    break
            flash(
                f'Could not find an "Item Number" column in the first 10 rows. '
                f'Values found: {", ".join(sample[:20]) or "(empty sheet)"}. '
                f'Rename your item number column to "Item Number" or "Item #".',
                'danger'
            )
            return redirect(url_for('billing.import_warehouse'))

        # Pre-load all existing records into dicts to avoid per-row DB queries
        existing_products = {p.item_number: p for p in WarehouseProduct.query.all()}
        existing_prices = {p.item_number: p for p in ItemPrice.query.all()}

        added = updated = priced = 0
        new_products = []
        new_prices = []

        for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
            item_number = str(row[col_num] or '').strip()
            if not item_number:
                continue
            item_name = str(row[col_name] or '').strip() if col_name is not None else ''
            try:
                qty = int(float(row[col_qty] or 0)) if col_qty is not None else None
            except (ValueError, TypeError):
                qty = None
            try:
                price = float(row[col_price] or 0) if col_price is not None else None
            except (ValueError, TypeError):
                price = None

            # Upsert WarehouseProduct (no per-row query)
            if qty is not None:
                wp = existing_products.get(item_number)
                if wp:
                    if item_name:
                        wp.item_name = item_name
                    wp.quantity_on_hand = qty
                    updated += 1
                else:
                    wp = WarehouseProduct(
                        item_number=item_number,
                        item_name=item_name,
                        quantity_on_hand=qty,
                    )
                    new_products.append(wp)
                    existing_products[item_number] = wp  # prevent duplicate adds
                    added += 1

            # Upsert ItemPrice (no per-row query)
            if price is not None:
                ip = existing_prices.get(item_number)
                if ip:
                    ip.price = price
                    if item_name and not ip.item_name:
                        ip.item_name = item_name
                else:
                    ip = ItemPrice(item_number=item_number, item_name=item_name, price=price)
                    new_prices.append(ip)
                    existing_prices[item_number] = ip  # prevent duplicate adds
                priced += 1

        if new_products:
            db.session.add_all(new_products)
        if new_prices:
            db.session.add_all(new_prices)
        db.session.commit()
        flash(f'Import complete: {added} products added, {updated} updated, {priced} prices set.', 'success')
        return redirect(url_for('billing.warehouse_inventory'))

    return render_template('billing_import.html')


# ---------- Metrics ----------
@billing_bp.route('/metrics')
@billing_required
def metrics():
    from sqlalchemy import func
    total_trailers = Trailer.query.count()
    completed_trailers = Trailer.query.filter_by(status='Completed').count()
    pending_trailers = Trailer.query.filter_by(status='Pending').count()
    in_progress_trailers = Trailer.query.filter_by(status='In Progress').count()

    # Most frequently flagged items (Missing or Red Tag)
    flagged_counts = (
        db.session.query(
            InventoryResponse.item_name,
            InventoryResponse.item_number,
            func.count(InventoryResponse.id).label('count')
        )
        .filter(InventoryResponse.status.in_(['Missing', 'Red Tag']))
        .group_by(InventoryResponse.item_name, InventoryResponse.item_number)
        .order_by(func.count(InventoryResponse.id).desc())
        .limit(10)
        .all()
    )

    # Warehouse low-stock items
    low_stock = WarehouseProduct.query.filter(
        WarehouseProduct.quantity_on_hand <= WarehouseProduct.reorder_point
    ).all()

    # Orders by status
    order_counts = (
        db.session.query(WarehouseOrder.status, func.count(WarehouseOrder.id))
        .group_by(WarehouseOrder.status)
        .all()
    )
    order_status_map = {s: c for s, c in order_counts}

    return render_template(
        'billing_metrics.html',
        total_trailers=total_trailers,
        completed_trailers=completed_trailers,
        pending_trailers=pending_trailers,
        in_progress_trailers=in_progress_trailers,
        flagged_counts=flagged_counts,
        low_stock=low_stock,
        order_status_map=order_status_map,
    )
