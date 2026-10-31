import sqlite3
from datetime import datetime, timedelta, timezone


MIN_PICKUP = timedelta(minutes=15)
HOLD_DURATION = timedelta(minutes=5)


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    """Require timezone-aware dates and store UTC timestamps."""
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
            appointment_end REAL
        )
    """)

    return db


def create_listing(db, title, owner, start, end):
    title = title.strip()
    owner = owner.strip()

    if not title or not owner:
        raise ValueError("Title and owner are required.")

    start_ts = timestamp(start)
    end_ts = timestamp(end)

    if end_ts - start_ts < MIN_PICKUP.total_seconds():
        raise ValueError(
            "Pickup window must be at least 15 minutes."
        )

    cursor = db.execute("""
        INSERT INTO listings (
            title, owner, pickup_start, pickup_end
        )
        VALUES (?, ?, ?, ?)
    """, (title, owner, start_ts, end_ts))

    return cursor.lastrowid


def refresh_expired(db, now):
    now_ts = timestamp(now)

    db.execute("""
        UPDATE listings
        SET status = 'available',
            recipient = NULL,
            hold_until = NULL,
            appointment_start = NULL,
            appointment_end = NULL
        WHERE status = 'offered'
          AND hold_until <= ?
    """, (now_ts,))

    db.execute("""
        UPDATE listings
        SET status = 'expired'
        WHERE status = 'available'
          AND pickup_end < ?
    """, (
        now_ts + MIN_PICKUP.total_seconds(),
    ))


def get_listing(db, listing_id):
    row = db.execute(
        "SELECT * FROM listings WHERE id = ?",
        (listing_id,),
    ).fetchone()

    if row is None:
        raise ValueError("Listing not found.")

    return dict(row)


def request_item(
    db,
    listing_id,
    recipient,
    start,
    end,
    now,
):
    recipient = recipient.strip()

    if not recipient:
        raise ValueError("Recipient is required.")

    start_ts = timestamp(start)
    end_ts = timestamp(end)
    now_ts = timestamp(now)

    if end_ts <= start_ts:
        raise ValueError(
            "Availability end must be after start."
        )

    db.execute("BEGIN IMMEDIATE")

    try:
        refresh_expired(db, now)
        listing = get_listing(db, listing_id)

        if recipient == listing["owner"]:
            raise ValueError(
                "You cannot request your own item."
            )

        if listing["status"] != "available":
            raise ValueError(
                "This item is not available."
            )

        hold_until = (
            now_ts + HOLD_DURATION.total_seconds()
        )

        overlap_start = max(
            listing["pickup_start"],
            start_ts,
            hold_until,
        )

        overlap_end = min(
            listing["pickup_end"],
            end_ts,
        )

        if (
            overlap_end - overlap_start
            < MIN_PICKUP.total_seconds()
        ):
            raise ValueError(
                "No compatible 15-minute pickup window."
            )

        appointment_end = (
            overlap_start + MIN_PICKUP.total_seconds()
        )

        db.execute("""
            UPDATE listings
            SET status = 'offered',
                recipient = ?,
                hold_until = ?,
                appointment_start = ?,
                appointment_end = ?
            WHERE id = ?
        """, (
            recipient,
            hold_until,
            overlap_start,
            appointment_end,
            listing_id,
        ))

        result = get_listing(db, listing_id)
        db.commit()
        return result

    except Exception:
        db.rollback()
        raise


def _change_status(
    db,
    listing_id,
    actor,
    now,
    action,
):
    """Apply one lifecycle change inside a write transaction."""
    actor = actor.strip()
    now_ts = timestamp(now)

    if not actor:
        raise ValueError("Actor is required.")

    db.execute("BEGIN IMMEDIATE")

    try:
        refresh_expired(db, now)
        listing = get_listing(db, listing_id)

        if action == "confirm":
            if listing["status"] != "offered":
                raise ValueError(
                    "No active offer to confirm."
                )

            if actor != listing["recipient"]:
                raise ValueError(
                    "Only the recipient can confirm."
                )

            new_status = "reserved"

        elif action == "cancel":
            if listing["status"] not in (
                "offered",
                "reserved",
            ):
                raise ValueError(
                    "No active offer or reservation to cancel."
                )

            if actor not in (
                listing["owner"],
                listing["recipient"],
            ):
                raise ValueError(
                    "Only the owner or recipient can cancel."
                )

            new_status = "available"

        elif action == "collect":
            if listing["status"] != "reserved":
                raise ValueError(
                    "Only a confirmed reservation can be collected."
                )

            if actor != listing["owner"]:
                raise ValueError(
                    "Only the owner can confirm collection."
                )

            if now_ts < listing["appointment_start"]:
                raise ValueError(
                    "Collection cannot be recorded before pickup starts."
                )

            new_status = "collected"

        else:
            raise ValueError("Unknown action.")

        if action == "cancel":
            db.execute("""
                UPDATE listings
                SET status = ?,
                    recipient = NULL,
                    hold_until = NULL,
                    appointment_start = NULL,
                    appointment_end = NULL
                WHERE id = ?
            """, (new_status, listing_id))

            refresh_expired(db, now)

        else:
            db.execute("""
                UPDATE listings
                SET status = ?,
                    hold_until = NULL
                WHERE id = ?
            """, (new_status, listing_id))

        result = get_listing(db, listing_id)
        db.commit()
        return result

    except Exception:
        db.rollback()
        raise


def confirm_offer(db, listing_id, recipient, now):
    return _change_status(
        db,
        listing_id,
        recipient,
        now,
        "confirm",
    )


def cancel_reservation(db, listing_id, actor, now):
    return _change_status(
        db,
        listing_id,
        actor,
        now,
        "cancel",
    )


def mark_collected(db, listing_id, owner, now):
    return _change_status(
        db,
        listing_id,
        owner,
        now,
        "collect",
    )