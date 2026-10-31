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
    browse_listings,
    request_late_pickup,
    decide_late_pickup,
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

    def expire_reservation(self):
        self.confirm()
        browse_listings(
            self.db,
            "Adi",
            self.end,
        )

    def propose_late(self):
        return request_late_pickup(
            self.db,
            self.item_id,
            "Adi",
            self.end + timedelta(hours=1),
            self.end + timedelta(hours=2),
            self.end,
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
        with self.assertRaisesRegex(
            ValueError,
            "No active offer",
        ):
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

    def test_owner_can_confirm_collection(self):
        self.confirm()

        result = mark_collected(
            self.db,
            self.item_id,
            "Priya",
            self.start,
        )

        self.assertEqual(result["status"], "collected")

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

        with self.assertRaisesRegex(
            ValueError,
            "before pickup",
        ):
            mark_collected(
                self.db,
                self.item_id,
                "Priya",
                self.now + timedelta(minutes=2),
            )

    def test_expired_item_visible_to_everyone(self):
        self.expire_reservation()

        for actor in ("Adi", "Priya", "Neha"):
            with self.subTest(actor=actor):
                items = browse_listings(
                    self.db,
                    actor,
                    self.end,
                )

                self.assertEqual(len(items), 1)
                self.assertEqual(
                    items[0]["id"],
                    self.item_id,
                )
                self.assertEqual(
                    items[0]["status"],
                    "expired",
                )

    def test_collection_requires_late_approval_after_expiry(self):
        self.expire_reservation()

        with self.assertRaisesRegex(
            ValueError,
            "confirmed reservation",
        ):
            mark_collected(
                self.db,
                self.item_id,
                "Priya",
                self.end,
            )

    def test_original_recipient_can_request_late_pickup(self):
        self.expire_reservation()

        result = self.propose_late()

        self.assertEqual(
            result["status"],
            "late_requested",
        )
        self.assertEqual(result["recipient"], "Adi")

    def test_other_student_cannot_request_late_pickup(self):
        self.expire_reservation()

        with self.assertRaisesRegex(
            ValueError,
            "original",
        ):
            request_late_pickup(
                self.db,
                self.item_id,
                "Neha",
                self.end + timedelta(hours=1),
                self.end + timedelta(hours=2),
                self.end,
            )

    def test_only_owner_can_approve_late_pickup(self):
        self.expire_reservation()
        self.propose_late()

        with self.assertRaisesRegex(ValueError, "owner"):
            decide_late_pickup(
                self.db,
                self.item_id,
                "Adi",
                True,
                self.end,
            )

    def test_approved_late_pickup_can_be_collected(self):
        self.expire_reservation()
        self.propose_late()

        approved = decide_late_pickup(
            self.db,
            self.item_id,
            "Priya",
            True,
            self.end,
        )

        self.assertEqual(
            approved["status"],
            "late_reserved",
        )

        collected = mark_collected(
            self.db,
            self.item_id,
            "Priya",
            self.end + timedelta(hours=1),
        )

        self.assertEqual(
            collected["status"],
            "collected",
        )

    def test_rejection_ends_arrangement(self):
        self.expire_reservation()
        self.propose_late()

        result = decide_late_pickup(
            self.db,
            self.item_id,
            "Priya",
            False,
            self.end,
        )

        self.assertEqual(result["status"], "expired")
        self.assertIsNone(result["recipient"])
        self.assertIsNone(result["late_start"])
        self.assertIsNone(result["late_end"])

    def test_pending_request_lapses_at_proposed_start(self):
        self.expire_reservation()
        self.propose_late()

        proposed_start = self.end + timedelta(hours=1)

        # Persist the time-based expiration before attempting approval.
        browse_listings(
            self.db,
            "Priya",
            proposed_start,
        )

        self.assertEqual(
            get_listing(self.db, self.item_id)["status"],
            "expired",
        )

        with self.assertRaisesRegex(
            ValueError,
            "No active late",
        ):
            decide_late_pickup(
                self.db,
                self.item_id,
                "Priya",
                True,
                proposed_start,
            )

    def test_approved_late_window_also_expires(self):
        self.expire_reservation()
        self.propose_late()

        decide_late_pickup(
            self.db,
            self.item_id,
            "Priya",
            True,
            self.end,
        )

        browse_listings(
            self.db,
            "Priya",
            self.end + timedelta(hours=2),
        )

        self.assertEqual(
            get_listing(self.db, self.item_id)["status"],
            "expired",
        )


if __name__ == "__main__":
    unittest.main()