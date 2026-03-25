# inventory_app/models.py
from database import db


class Trailer(db.Model):
    __tablename__ = 'trailer'

    id = db.Column(db.Integer, primary_key=True)

    # External/field-visible trailer identifier (what you added to the form)
    trailer_id = db.Column(db.String(64), index=True)  # e.g., "T-1001"

    job_name = db.Column(db.String(120))
    job_number = db.Column(db.String(50))
    location = db.Column(db.String(120))

    # Kept for compatibility; not used to choose the list anymore
    inventory_type = db.Column(db.String(50))

    assigned_user = db.Column(db.String(80))  # set at submission time

    # Start new assignments as Pending; move to In Progress / Completed via app logic
    status = db.Column(db.String(50), nullable=False, server_default="Pending", index=True)

    # Stores a list of {"name","number","quantity"}
    extra_tooling = db.Column(db.JSON)

    # Which predefined tooling list this trailer uses (e.g., "Standard Trailer", "Gang Box", etc.)
    tooling_list_name = db.Column(db.String(100), index=True)

    foreman_name = db.Column(db.String(100))
    ln_25s = db.Column(db.String(120))
    notes = db.Column(db.Text)

    # Relationships
    responses = db.relationship(
        'InventoryResponse',
        backref='trailer',
        lazy=True,
        cascade='all, delete-orphan'
    )
    invoices = db.relationship(
        'Invoice',
        backref='trailer',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f"<Trailer id={self.id} trailer_id={self.trailer_id!r} job={self.job_name!r} status={self.status!r}>"


class InventoryResponse(db.Model):
    __tablename__ = 'inventory_response'

    id = db.Column(db.Integer, primary_key=True)
    trailer_id = db.Column(db.Integer, db.ForeignKey('trailer.id'), index=True, nullable=False)

    item_number = db.Column(db.String(50))
    item_name = db.Column(db.String(120))
    status = db.Column(db.String(20))  # Missing, Red Tag, Complete
    note = db.Column(db.Text)
    quantity = db.Column(db.Integer)
    category = db.Column(db.String(50))

    # Timestamp (DB-side default)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<InventoryResponse trailer_id={self.trailer_id} item={self.item_number!r} status={self.status!r}>"


class Invoice(db.Model):
    __tablename__ = 'invoice'

    id = db.Column(db.Integer, primary_key=True)
    trailer_id = db.Column(db.Integer, db.ForeignKey('trailer.id'), index=True, nullable=False)
    file_path = db.Column(db.String(255))
    billed = db.Column(db.Boolean, nullable=False, server_default='false', default=False)

    # Snapshot of line items at time of billing (JSON). Once populated, invoice
    # prices are frozen and won't change when ItemPrice is updated.
    line_items_json = db.Column(db.Text, nullable=True)

    # Timestamp (DB-side default)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<Invoice id={self.id} trailer_id={self.trailer_id} created_at={self.created_at}>"


class ItemPrice(db.Model):
    __tablename__ = 'item_price'

    id = db.Column(db.Integer, primary_key=True)
    item_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    item_name = db.Column(db.String(120))
    price = db.Column(db.Float, nullable=False, default=0.0)

    def __repr__(self):
        return f"<ItemPrice item_number={self.item_number!r} price={self.price}>"


class SpecialtyTool(db.Model):
    __tablename__ = 'specialty_tool'

    id = db.Column(db.Integer, primary_key=True)
    item_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    item_name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<SpecialtyTool item_number={self.item_number!r} qty={self.quantity}>"


class WarehouseProduct(db.Model):
    __tablename__ = 'warehouse_product'

    id = db.Column(db.Integer, primary_key=True)
    item_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    item_name = db.Column(db.String(120))
    quantity_on_hand = db.Column(db.Integer, default=0)
    reorder_point = db.Column(db.Integer, default=0)
    unit_cost = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    def __repr__(self):
        return f"<WarehouseProduct item_number={self.item_number!r} qty={self.quantity_on_hand}>"


class WarehouseOrder(db.Model):
    __tablename__ = 'warehouse_order'

    id = db.Column(db.Integer, primary_key=True)
    trailer_id = db.Column(db.Integer, db.ForeignKey('trailer.id'), nullable=True, index=True)
    status = db.Column(db.String(50), default='Pending')  # Pending, Billed, Cancelled
    billed = db.Column(db.Boolean, default=False, nullable=False)
    order_total = db.Column(db.Float, default=0.0)
    requester_name = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False, index=True)

    lines = db.relationship('WarehouseOrderLine', backref='order', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f"<WarehouseOrder id={self.id} status={self.status!r}>"


class WarehouseOrderLine(db.Model):
    __tablename__ = 'warehouse_order_line'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('warehouse_order.id'), nullable=False, index=True)
    item_number = db.Column(db.String(50), nullable=True)  # optional — matched at billing time
    item_name = db.Column(db.String(120))
    quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)   # snapshot at billing time
    line_total = db.Column(db.Float, default=0.0)   # snapshot at billing time

    def __repr__(self):
        return f"<WarehouseOrderLine order_id={self.order_id} item={self.item_number!r} qty={self.quantity}>"


class ToolingListItem(db.Model):
    __tablename__ = 'tooling_list_item'
    id = db.Column(db.Integer, primary_key=True)
    list_name = db.Column(db.String(100), nullable=False, index=True)
    item_number = db.Column(db.String(50))
    item_name = db.Column(db.String(120))
    category = db.Column(db.String(50))
    quantity = db.Column(db.Integer, default=0)
    sort_order = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<ToolingListItem list={self.list_name!r} item={self.item_number!r}>"
