import unittest
from datetime import timezone

from verify_demo_continuity import parse_timestamp


class ContinuityTimestampTests(unittest.TestCase):
    def test_postgres_and_iso_forms_match(self):
        postgres = parse_timestamp("2026-09-13 19:07:52.404388+00")
        iso = parse_timestamp("2026-09-13T19:07:52.404388+00:00")
        self.assertEqual(postgres, iso)
        self.assertEqual(iso.tzinfo, timezone.utc)

    def test_z_suffix_is_supported(self):
        self.assertEqual(
            parse_timestamp("2026-12-12T19:07:52.404388Z"),
            parse_timestamp("2026-12-12T19:07:52.404388+00:00"),
        )


if __name__ == "__main__":
    unittest.main()
