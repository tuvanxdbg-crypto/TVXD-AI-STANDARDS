"""M03-C T3 probe: test cố ý fail để làm đỏ job `metadata`.

Chỉ tồn tại trên nhánh thử `claude/m03c-probe` (docs/M03_C_VERIFICATION_PLAN.md §4.3).
Không bao giờ merge.
"""
import unittest


class M03CProbe(unittest.TestCase):
    def test_deliberate_failure(self):
        self.fail("M03-C T3 probe: cố ý fail, không merge")


if __name__ == "__main__":
    unittest.main()
