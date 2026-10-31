import unittest
from datetime import datetime, timedelta, timezone

from core import (
    connect,
    create_listing,
    request_item,
    confirm_offer,
    cancel_reservation,
    mark_collected,
    get_listing,
)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")

        self.now = datetime(
            2026, 11, 1, 16, 0,
            tzinfo=timezone.utc,
        )
        self.start = self.now + timedelta(hours=1)
        self.end = self.start + timedelta(hours=3)

        self.item_id = create_listing(
            self.db,
            "Study desk",
            "Priya",
            self.start,
            self.end,
        )

        request_item(
            self.db,
            self.item_id,
            "Adi",
            self.start,
            self.end,
            self.now,
        )

    def tearDown(self):
        self.db.close()

    def confirm(self):
        return confirm_offer(
            self.db,
            self.item_id,
            "Adi",
            self.now + timedelta(minutes=1),
        )

    def test_recipient_can_confirm(self):
        result = self.confirm()
        self.assertEqual(result["status"], "reserved")

    def test_wrong_person_cannot_confirm(self):
        with self.assertRaisesRegex(ValueError, "recipient"):
            confirm_offer(
                self.db,
                self.item_id,
                "Neha",
                self.now + timedelta(minutes=1),
            )

    def test_confirmation_at_expiry_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "No active offer"):
            confirm_offer(
                self.db,
                self.item_id,
                "Adi",
                self.now + timedelta(minutes=5),
            )

    def test_cancel_reopens_item(self):
        self.confirm()

        result = cancel_reservation(
            self.db,
            self.item_id,
            "Adi",
            self.now + timedelta(minutes=2),
        )

        self.assertEqual(result["status"], "available")
        self.assertIsNone(result["recipient"])

    def test_late_cancellation_does_not_reopen_item(self):
        self.confirm()

        result = cancel_reservation(
            self.db,
            self.item_id,
            "Adi",
            self.end,
        )

        self.assertEqual(result["status"], "expired")

    def test_owner_can_confirm_collection(self):
        self.confirm()

        result = mark_collected(
            self.db,
            self.item_id,
            "Priya",
            self.start + timedelta(minutes=5),
        )

        self.assertEqual(result["status"], "collected")
        self.assertEqual(result["recipient"], "Adi")

    def test_recipient_cannot_confirm_collection(self):
        self.confirm()

        with self.assertRaisesRegex(ValueError, "owner"):
            mark_collected(
                self.db,
                self.item_id,
                "Adi",
                self.start,
            )

    def test_collection_before_pickup_is_rejected(self):
        self.confirm()

        with self.assertRaisesRegex(ValueError, "before pickup"):
            mark_collected(
                self.db,
                self.item_id,
                "Priya",
                self.now + timedelta(minutes=2),
            )

    def test_cancelled_offer_cannot_be_confirmed(self):
        cancel_reservation(
            self.db,
            self.item_id,
            "Adi",
            self.now + timedelta(minutes=1),
        )

        with self.assertRaises(ValueError):
            confirm_offer(
                self.db,
                self.item_id,
                "Adi",
                self.now + timedelta(minutes=2),
            )

        result = get_listing(self.db, self.item_id)
        self.assertEqual(result["status"], "available")


if __name__ == "__main__":
    unittest.main()