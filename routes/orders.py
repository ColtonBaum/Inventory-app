# routes/orders.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import Trailer, WarehouseOrder, WarehouseOrderLine, WarehouseProduct
from database import db

orders_bp = Blueprint('orders', __name__, url_prefix='/orders')


@orders_bp.route('/')
def orders_list():
    orders = WarehouseOrder.query.order_by(WarehouseOrder.created_at.desc()).all()
    trailers = {t.id: t for t in Trailer.query.all()}
    return render_template('orders_list.html', orders=orders, trailers=trailers)


@orders_bp.route('/new', methods=['GET', 'POST'])
def new_order():
    if request.method == 'POST':
        trailer_id_raw = request.form.get('trailer_id') or None
        trailer_id = int(trailer_id_raw) if trailer_id_raw else None
        notes = (request.form.get('notes') or '').strip()
        submitted_by = (request.form.get('submitted_by') or '').strip()
        order = WarehouseOrder(trailer_id=trailer_id, status='Pending',
                               notes=f"Submitted by: {submitted_by}\n{notes}".strip() if submitted_by else notes)
        db.session.add(order)
        db.session.flush()

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
            db.session.add(WarehouseOrderLine(order_id=order.id, item_number=num,
                                              item_name=name.strip(), quantity=qty))
        db.session.commit()
        flash('Order submitted successfully!', 'success')
        return redirect(url_for('orders.view_order', order_id=order.id))

    trailers = Trailer.query.filter(Trailer.status != 'Completed').order_by(Trailer.id.desc()).all()
    products = WarehouseProduct.query.order_by(WarehouseProduct.item_name).all()
    return render_template('orders_new.html', trailers=trailers, products=products)


@orders_bp.route('/<int:order_id>')
def view_order(order_id):
    order = WarehouseOrder.query.get_or_404(order_id)
    trailer = Trailer.query.get(order.trailer_id) if order.trailer_id else None
    return render_template('orders_view.html', order=order, trailer=trailer)
