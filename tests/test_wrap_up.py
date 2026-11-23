"""Guards the wrap-up skill's workspace checks."""
import os, unittest

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'skills', 'wrap-up', 'SKILL.md')


class WrapUpSkillTests(unittest.TestCase):
    def test_checks_remote_divergence(self):
        # Local-only checks missed a remote commit pushed from another machine; the push was then rejected.
        with open(SKILL) as f: text = f.read()
        self.assertIn('git fetch', text)
        self.assertIn('git status -sb', text)


if __name__ == '__main__':
    unittest.main()
