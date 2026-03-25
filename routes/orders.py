# routes/orders.py — public order submission (no auth required)
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import Trailer, WarehouseOrder, WarehouseOrderLine
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
        requester_name = (request.form.get('requester_name') or '').strip()
        notes = (request.form.get('notes') or '').strip()
        trailer_id_raw = request.form.get('trailer_id') or None
        trailer_id = int(trailer_id_raw) if trailer_id_raw else None

        order = WarehouseOrder(
            trailer_id=trailer_id,
            requester_name=requester_name,
            status='Pending',
            billed=False,
            notes=notes,
        )
        db.session.add(order)
        db.session.flush()

        item_names = request.form.getlist('item_name')
        quantities = request.form.getlist('quantity')
        any_added = False
        for name, qty_raw in zip(item_names, quantities):
            name = name.strip()
            if not name:
                continue
            try:
                qty = int(qty_raw or 0)
            except ValueError:
                qty = 0
            if qty <= 0:
                continue
            db.session.add(WarehouseOrderLine(order_id=order.id, item_name=name, quantity=qty))
            any_added = True

        if not any_added:
            db.session.rollback()
            flash('Please add at least one item with a quantity.', 'danger')
            trailers = Trailer.query.filter(Trailer.status != 'Completed').order_by(Trailer.id.desc()).all()
            return render_template('orders_new.html', trailers=trailers)

        db.session.commit()
        flash('Order submitted! The warehouse team will review it.', 'success')
        return redirect(url_for('orders.view_order', order_id=order.id))

    trailers = Trailer.query.filter(Trailer.status != 'Completed').order_by(Trailer.id.desc()).all()
    return render_template('orders_new.html', trailers=trailers)


@orders_bp.route('/<int:order_id>')
def view_order(order_id):
    order = WarehouseOrder.query.get_or_404(order_id)
    trailer = Trailer.query.get(order.trailer_id) if order.trailer_id else None
    return render_template('orders_view.html', order=order, trailer=trailer)
