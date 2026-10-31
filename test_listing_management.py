import unittest
from datetime import datetime, timedelta, timezone

from core import (
    connect,
    create_listing,
    get_listing,
    browse_listings,
    delete_listing,
    request_item,
)


class ListingManagementTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")

        self.now = datetime(
            2026, 11, 1, 16, 0,
            tzinfo=timezone.utc,
        )

        self.start = self.now + timedelta(hours=1)
        self.end = self.start + timedelta(hours=2)

        self.item_id = create_listing(
            self.db,
            "Desk",
            "Priya",
            self.start,
            self.end,
            "Demo Residence, main lobby",
        )

    def tearDown(self):
        self.db.close()

    def test_address_is_saved(self):
        item = get_listing(
            self.db,
            self.item_id,
        )

        self.assertEqual(
            item["pickup_address"],
            "Demo Residence, main lobby",
        )

    def test_empty_address_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "address",
        ):
            create_listing(
                self.db,
                "Chair",
                "Priya",
                self.start,
                self.end,
                "   ",
            )

    def test_expired_item_visible_to_everyone(self):
        later = self.end + timedelta(minutes=1)

        for actor in ("Adi", "Priya", "Neha"):
            with self.subTest(actor=actor):
                items = browse_listings(
                    self.db,
                    actor,
                    later,
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

    def test_non_owner_cannot_remove(self):
        with self.assertRaisesRegex(
            ValueError,
            "owner",
        ):
            delete_listing(
                self.db,
                self.item_id,
                "Adi",
            )

        item = get_listing(
            self.db,
            self.item_id,
        )

        self.assertEqual(
            item["status"],
            "available",
        )

    def test_removed_item_hidden_from_everyone(self):
        delete_listing(
            self.db,
            self.item_id,
            "Priya",
        )

        for actor in ("Priya", "Adi", "Neha"):
            with self.subTest(actor=actor):
                items = browse_listings(
                    self.db,
                    actor,
                    self.now,
                )

                self.assertEqual(items, [])

        # Soft deletion preserves the internal record.
        item = get_listing(
            self.db,
            self.item_id,
        )

        self.assertEqual(
            item["status"],
            "deleted",
        )

    def test_removed_item_cannot_be_requested(self):
        delete_listing(
            self.db,
            self.item_id,
            "Priya",
        )

        with self.assertRaisesRegex(
            ValueError,
            "not available",
        ):
            request_item(
                self.db,
                self.item_id,
                "Adi",
                self.start,
                self.end,
                self.now,
            )


if __name__ == "__main__":
    unittest.main()