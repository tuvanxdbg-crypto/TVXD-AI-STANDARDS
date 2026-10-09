"""M03-A deliberate red control (docs/M03_GITHUB_GOVERNANCE.md §6): this test fails on purpose so that the CI jobs
linux and windows go red once. It is reverted in the next commit."""
import unittest


class CiRedControl(unittest.TestCase):
    def test_deliberate_failure(self):
        self.fail("M03-A deliberate red control: linux and windows must go red; reverted in the next commit")


if __name__ == "__main__":
    unittest.main()
