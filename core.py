import sqlite3
from datetime import datetime, timedelta, timezone


MIN_PICKUP = timedelta(minutes=15)
HOLD_DURATION = timedelta(minutes=5)


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Dates must include a timezone.")
    return value.timestamp()


def connect(path="handover.db"):
    db = sqlite3.connect(path, isolation_level=None)
    db.row_factory = sqlite3.Row

    db.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            owner TEXT NOT NULL,
            pickup_start REAL NOT NULL,
            pickup_end REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'available',
            recipient TEXT,
            hold_until REAL,
            appointment_start REAL,
            appointment_end REAL,
            pickup_address TEXT NOT NULL DEFAULT '',
            late_start REAL,
            late_end REAL
        )
    """)

    columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(listings)")
    }

    migrations = {
        "pickup_address": "TEXT NOT NULL DEFAULT ''",
        "late_start": "REAL",
        "late_end": "REAL",
    }

    for name, definition in migrations.items():
        if name not in columns:
            db.execute(
                f"ALTER TABLE listings ADD COLUMN {name} {definition}"
            )

    return db


def create_listing(
    db, title, owner, start, end,
    pickup_address="Demo Student Community Lobby",
):
    title = title.strip()
    owner = owner.strip()
    pickup_address = pickup_address.strip()

    if not title or not owner:
        raise ValueError("Title and owner are required.")
    if not pickup_address:
        raise ValueError("Pickup address is required.")

    start_ts = timestamp(start)
    end_ts = timestamp(end)

    if end_ts - start_ts < MIN_PICKUP.total_seconds():
        raise ValueError("Pickup window must be at least 15 minutes.")

    cursor = db.execute("""
        INSERT INTO listings (
            title, owner, pickup_start, pickup_end, pickup_address
        )
        VALUES (?, ?, ?, ?, ?)
    """, (title, owner, start_ts, end_ts, pickup_address))

    return cursor.lastrowid


def refresh_expired(db, now):
    now_ts = timestamp(now)

    # Confirmed original reservations expire at the owner's deadline.
    db.execute("""
        UPDATE listings
        SET status = 'expired', hold_until = NULL
        WHERE status = 'reserved' AND pickup_end <= ?
    """, (now_ts,))

    # Unconfirmed offers return to availability.
    db.execute("""
        UPDATE listings
        SET status = 'available',
            recipient = NULL,
            hold_until = NULL,
            appointment_start = NULL,
            appointment_end = NULL
        WHERE status = 'offered' AND hold_until <= ?
    """, (now_ts,))

    db.execute("""
        UPDATE listings
        SET status = 'expired'
        WHERE status = 'available' AND pickup_end < ?
    """, (now_ts + MIN_PICKUP.total_seconds(),))

    # An unapproved proposal lapses once its proposed start arrives.
    db.execute("""
        UPDATE listings
        SET status = 'expired'
        WHERE status = 'late_requested' AND late_start <= ?
    """, (now_ts,))

    # Approved late arrangements expire at their new deadline.
    db.execute("""
        UPDATE listings
        SET status = 'expired'
        WHERE status = 'late_reserved' AND late_end <= ?
    """, (now_ts,))


def get_listing(db, listing_id):
    row = db.execute(
        "SELECT * FROM listings WHERE id = ?",
        (listing_id,),
    ).fetchone()

    if row is None:
        raise ValueError("Listing not found.")

    return dict(row)


def browse_listings(db, actor, now):
    """Expired items remain visible; removed items do not."""
    refresh_expired(db, now)
    rows = db.execute("""
        SELECT * FROM listings
        WHERE status != 'deleted'
        ORDER BY id DESC
    """).fetchall()

    return [dict(row) for row in rows]


def request_item(db, listing_id, recipient, start, end, now):
    recipient = recipient.strip()
    if not recipient:
        raise ValueError("Recipient is required.")

    start_ts = timestamp(start)
    end_ts = timestamp(end)
    now_ts = timestamp(now)

    if end_ts <= start_ts:
        raise ValueError("Availability end must be after start.")

    db.execute("BEGIN IMMEDIATE")
    try:
        refresh_expired(db, now)
        item = get_listing(db, listing_id)

        if recipient == item["owner"]:
            raise ValueError("You cannot request your own item.")
        if item["status"] != "available":
            raise ValueError("This item is not available.")

        hold_until = now_ts + HOLD_DURATION.total_seconds()
        overlap_start = max(item["pickup_start"], start_ts, hold_until)
        overlap_end = min(item["pickup_end"], end_ts)

        if overlap_end - overlap_start < MIN_PICKUP.total_seconds():
            raise ValueError("No compatible 15-minute pickup window.")

        db.execute("""
            UPDATE listings
            SET status = 'offered',
                recipient = ?,
                hold_until = ?,
                appointment_start = ?,
                appointment_end = ?,
                late_start = NULL,
                late_end = NULL
            WHERE id = ?
        """, (
            recipient,
            hold_until,
            overlap_start,
            overlap_start + MIN_PICKUP.total_seconds(),
            listing_id,
        ))

        result = get_listing(db, listing_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def _change_status(db, listing_id, actor, now, action):
    actor = actor.strip()
    now_ts = timestamp(now)

    if not actor:
        raise ValueError("Actor is required.")

    db.execute("BEGIN IMMEDIATE")
    try:
        refresh_expired(db, now)
        item = get_listing(db, listing_id)
        status = item["status"]

        if action == "confirm":
            if status != "offered":
                raise ValueError("No active offer to confirm.")
            if actor != item["recipient"]:
                raise ValueError("Only the recipient can confirm.")

            db.execute("""
                UPDATE listings
                SET status = 'reserved', hold_until = NULL
                WHERE id = ?
            """, (listing_id,))

        elif action == "cancel":
            if status not in ("offered", "reserved", "late_reserved"):
                raise ValueError("No active offer or reservation to cancel.")
            if actor not in (item["owner"], item["recipient"]):
                raise ValueError(
                    "Only the owner or recipient can cancel."
                )

            new_status = (
                "expired" if status == "late_reserved" else "available"
            )

            db.execute("""
                UPDATE listings
                SET status = ?,
                    recipient = NULL,
                    hold_until = NULL,
                    appointment_start = NULL,
                    appointment_end = NULL,
                    late_start = NULL,
                    late_end = NULL
                WHERE id = ?
            """, (new_status, listing_id))

            refresh_expired(db, now)

        elif action == "collect":
            if status not in ("reserved", "late_reserved"):
                raise ValueError(
                    "Only a confirmed reservation can be collected."
                )
            if actor != item["owner"]:
                raise ValueError("Only the owner can confirm collection.")

            start = (
                item["late_start"]
                if status == "late_reserved"
                else item["appointment_start"]
            )
            if now_ts < start:
                raise ValueError(
                    "Collection cannot be recorded before pickup starts."
                )

            db.execute("""
                UPDATE listings
                SET status = 'collected', hold_until = NULL
                WHERE id = ?
            """, (listing_id,))

        else:
            raise ValueError("Unknown action.")

        result = get_listing(db, listing_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def confirm_offer(db, listing_id, recipient, now):
    return _change_status(db, listing_id, recipient, now, "confirm")


def cancel_reservation(db, listing_id, actor, now):
    return _change_status(db, listing_id, actor, now, "cancel")


def mark_collected(db, listing_id, owner, now):
    return _change_status(db, listing_id, owner, now, "collect")


def request_late_pickup(db, listing_id, recipient, start, end, now):
    start_ts = timestamp(start)
    end_ts = timestamp(end)
    now_ts = timestamp(now)

    if start_ts <= now_ts:
        raise ValueError("Late pickup must start after the current demo time.")
    if end_ts - start_ts < MIN_PICKUP.total_seconds():
        raise ValueError("Late pickup window must be at least 15 minutes.")

    db.execute("BEGIN IMMEDIATE")
    try:
        refresh_expired(db, now)
        item = get_listing(db, listing_id)

        if item["status"] != "expired":
            raise ValueError("Late pickup requires an expired reservation.")
        if (
            not item["recipient"]
            or recipient != item["recipient"]
            or item["appointment_start"] is None
        ):
            raise ValueError(
                "Only the original confirmed recipient can request late pickup."
            )
        if start_ts < item["pickup_end"]:
            raise ValueError(
                "Late pickup must start at or after the original pickup deadline."
            )

        db.execute("""
            UPDATE listings
            SET status = 'late_requested', late_start = ?, late_end = ?
            WHERE id = ?
        """, (start_ts, end_ts, listing_id))

        result = get_listing(db, listing_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def decide_late_pickup(db, listing_id, owner, approve, now):
    if not isinstance(approve, bool):
        raise ValueError("Approval must be True or False.")

    db.execute("BEGIN IMMEDIATE")
    try:
        refresh_expired(db, now)
        item = get_listing(db, listing_id)

        if owner != item["owner"]:
            raise ValueError("Only the owner can decide late pickup.")
        if item["status"] != "late_requested":
            raise ValueError("No active late pickup request.")

        if approve:
            db.execute("""
                UPDATE listings SET status = 'late_reserved'
                WHERE id = ?
            """, (listing_id,))
        else:
            # Rejection ends this arrangement. Owner may list the item anew.
            db.execute("""
                UPDATE listings
                SET status = 'expired',
                    recipient = NULL,
                    late_start = NULL,
                    late_end = NULL
                WHERE id = ?
            """, (listing_id,))

        result = get_listing(db, listing_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def delete_listing(db, listing_id, actor):
    if not actor.strip():
        raise ValueError("Owner is required.")

    db.execute("BEGIN IMMEDIATE")
    try:
        item = get_listing(db, listing_id)

        if actor != item["owner"]:
            raise ValueError("Only the owner can remove this listing.")
        if item["status"] == "deleted":
            raise ValueError("This listing has already been removed.")

        db.execute("""
            UPDATE listings
            SET status = 'deleted', hold_until = NULL
            WHERE id = ?
        """, (listing_id,))

        db.commit()
    except Exception:
        db.rollback()
        raise