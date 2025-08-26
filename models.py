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

    # Timestamp (DB-side default)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<Invoice id={self.id} trailer_id={self.trailer_id} created_at={self.created_at}>"
