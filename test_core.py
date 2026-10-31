import unittest
from datetime import datetime, timedelta, timezone

from core import (
    connect,
    create_listing,
    get_listing,
    refresh_expired,
    request_item,
)


class HandoverTests(unittest.TestCase):
    def setUp(self):
        # Each test gets a clean, temporary in-memory database.
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

    def tearDown(self):
        self.db.close()

    def request(self, recipient="Adi", start=None, end=None, now=None):
        return request_item(
            self.db,
            self.item_id,
            recipient,
            start or self.start,
            end or self.end,
            now or self.now,
        )

    def test_compatible_request_creates_offer(self):
        result = self.request()

        self.assertEqual(result["status"], "offered")
        self.assertEqual(result["recipient"], "Adi")

    def test_incompatible_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "No compatible"):
            self.request(
                start=self.end + timedelta(days=1),
                end=self.end + timedelta(days=1, hours=1),
            )

    def test_second_student_cannot_claim_held_item(self):
        self.request()

        with self.assertRaisesRegex(ValueError, "not available"):
            self.request(recipient="Neha")

    def test_offer_expires_at_deadline(self):
        self.request()

        refresh_expired(
            self.db,
            self.now + timedelta(minutes=5),
        )

        result = get_listing(self.db, self.item_id)
        self.assertEqual(result["status"], "available")
        self.assertIsNone(result["recipient"])

    def test_another_student_can_claim_expired_offer(self):
        self.request()

        result = self.request(
            recipient="Neha",
            now=self.now + timedelta(minutes=6),
        )

        self.assertEqual(result["recipient"], "Neha")

    def test_owner_cannot_request_own_item(self):
        with self.assertRaisesRegex(ValueError, "own item"):
            self.request(recipient="Priya")

    def test_short_overlap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "No compatible"):
            self.request(
                start=self.end - timedelta(minutes=10),
                end=self.end,
            )

    def test_invalid_availability_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "after start"):
            self.request(start=self.end, end=self.start)

    def test_failed_request_does_not_change_listing(self):
        with self.assertRaises(ValueError):
            self.request(
                start=self.end + timedelta(hours=1),
                end=self.end + timedelta(hours=2),
            )

        result = get_listing(self.db, self.item_id)
        self.assertEqual(result["status"], "available")


if __name__ == "__main__":
    unittest.main()