from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from notebooklm_combo import cli


class InstallationTests(unittest.TestCase):
    def test_skill_is_installed_from_package_and_existing_skill_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['install-skill', '--destination', folder]), 0)
            path = Path(folder) / 'chinese-content-to-notebooklm/SKILL.md'
            self.assertIn('name: chinese-content-to-notebooklm', path.read_text(encoding='utf-8'))
            path.write_text('my existing skill', encoding='utf-8')
            self.assertEqual(cli.main(['install-skill', '--destination', folder]), 1)
            self.assertEqual(path.read_text(encoding='utf-8'), 'my existing skill')
            self.assertEqual(cli.main(['install-skill', '--destination', folder, '--force']), 0)
            self.assertIn('name: chinese-content-to-notebooklm', path.read_text(encoding='utf-8'))
