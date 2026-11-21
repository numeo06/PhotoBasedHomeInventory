"""Contract tests shared by Person A and Person B.

These check the agreed shape of the detector interface. They must pass for
both the stub and the real detector. Run before every merge:
    python -m unittest discover tests
"""

import unittest

from services import detector

VALID_STATUSES = {"ok", "no_detections", "model_unavailable", "scan_error"}


class ScanContract(unittest.TestCase):
    def test_scan_shape(self):
        result = detector.scan(b"not an image")  # must never raise
        self.assertIn(result["status"], VALID_STATUSES)
        self.assertIsInstance(result["items"], list)
        for item in result["items"]:
            self.assertIsInstance(item["name"], str)
            self.assertIsInstance(item["score"], float)

    def test_scan_empty_bytes_does_not_raise(self):
        result = detector.scan(b"")
        self.assertIn(result["status"], VALID_STATUSES)

    def test_status_shape(self):
        status = detector.model_status()
        self.assertIsInstance(status["ready"], bool)
        self.assertIsInstance(status["detail"], str)


if __name__ == "__main__":
    unittest.main()
