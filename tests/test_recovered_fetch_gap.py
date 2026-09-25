"""Regression tests for missed fetch windows detected after recovery."""
import unittest

from cw.pipeline import recovered_fetch_gap


class RecoveredFetchGapTests(unittest.TestCase):
    def test_first_success_has_no_previous_window(self):
        self.assertIsNone(recovered_fetch_gap(None, "2026-09-25T08:10:55Z", 3))

    def test_exact_boundary_is_not_a_gap(self):
        self.assertIsNone(recovered_fetch_gap("2026-09-25T05:10:55Z", "2026-09-25T08:10:55Z", 3))

    def test_short_interval_is_not_a_gap(self):
        self.assertIsNone(recovered_fetch_gap("2026-09-25T06:10:55Z", "2026-09-25T08:10:55Z", 3))

    def test_recovered_gdelt_gap_is_detected(self):
        self.assertEqual(recovered_fetch_gap("2026-09-25T04:54:44Z", "2026-09-25T08:10:55Z", 3), 11771)

    def test_source_specific_limit(self):
        self.assertIsNone(recovered_fetch_gap("2026-09-25T04:54:44Z", "2026-09-25T08:10:55Z", 6))


if __name__ == "__main__":
    unittest.main()
