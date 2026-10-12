"""Tests for the frozen-vs-source base-directory decision.

Run with:  python -m unittest discover -s tests -v

WHY THIS EXISTS. The install blocker was recorded as "a frozen build looks for
its reference tables next to the exe, but they are not there". That is not what
this repo does: the reference tables are seeded and edited in the per-user
writable data directory in BOTH modes (README, "Reference Tables"). What is real
is the failure mode the note pointed at — if the tables cannot be created or
read, the app must say so, not die to a dead, empty window.

These tests pin the path decision and the loud failure, so either half cannot
change without a deliberate edit.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import reference_tables  # noqa: E402
from core.reference_tables import verify_reference_tables  # noqa: E402


class FrozenDataDirTest(unittest.TestCase):
    """`_frozen_data_dir` is pure and follows the platform convention."""

    HOME = Path('/Users/someone')

    def test_windows_uses_appdata(self):
        base = config._frozen_data_dir(
            platform='win32', environ={'APPDATA': r'C:\Users\x\AppData\Roaming'}, home=self.HOME)
        self.assertEqual(base, Path(r'C:\Users\x\AppData\Roaming') / 'WikidataBatchUploader')

    def test_windows_without_appdata_falls_back_to_home(self):
        base = config._frozen_data_dir(platform='win32', environ={}, home=self.HOME)
        self.assertEqual(base, self.HOME / '.wikidata_batch_uploader')

    def test_macos_uses_application_support(self):
        base = config._frozen_data_dir(platform='darwin', environ={}, home=self.HOME)
        self.assertEqual(base, self.HOME / 'Library' / 'Application Support' / 'WikidataBatchUploader')

    def test_linux_uses_xdg_data_home_when_set(self):
        base = config._frozen_data_dir(platform='linux', environ={'XDG_DATA_HOME': '/xdg'}, home=self.HOME)
        self.assertEqual(base, Path('/xdg') / 'WikidataBatchUploader')

    def test_linux_without_xdg_uses_local_share(self):
        base = config._frozen_data_dir(platform='linux', environ={}, home=self.HOME)
        self.assertEqual(base, self.HOME / '.local' / 'share' / 'WikidataBatchUploader')


class BaseDirDecisionTest(unittest.TestCase):
    """`get_base_dir` switches on `sys.frozen`, and reference tables sit under it."""

    def test_source_mode_uses_the_project_root(self):
        with mock.patch.object(config.sys, 'frozen', False, create=True):
            base = config.get_base_dir()
        self.assertEqual(base, Path(config.__file__).parent)

    def test_frozen_mode_uses_the_user_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(config.sys, 'frozen', True, create=True), \
             mock.patch.object(config, '_frozen_data_dir', return_value=Path(tmp) / 'nested'):
            base = config.get_base_dir()
            self.assertEqual(base, Path(tmp) / 'nested')
            self.assertTrue(base.is_dir())  # get_base_dir created it

    def test_reference_tables_dir_is_base_dir_over_reference_tables(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(config, 'get_base_dir', return_value=Path(tmp)):
            self.assertEqual(config.get_reference_tables_dir(), Path(tmp) / 'reference_tables')


class ReferenceTablesFailLoudTest(unittest.TestCase):
    """A broken reference table must raise a named error, not a silent stub."""

    def test_verification_passes_when_tables_seed_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            verify_reference_tables(tmp)  # must not raise

    def test_a_table_that_cannot_be_created_is_reported_with_the_path(self):
        with mock.patch.object(reference_tables, 'ensure_sample_reference_tables',
                               side_effect=PermissionError('read-only directory')):
            with self.assertRaises(RuntimeError) as ctx:
                verify_reference_tables('/tmp/nonexistent/refdir')
        message = str(ctx.exception)
        self.assertIn('/tmp/nonexistent/refdir', message)
        self.assertIn('read-only directory', message)

    def test_a_table_that_cannot_be_read_is_reported_not_swallowed(self):
        with mock.patch.object(
            reference_tables, 'load_wikidata_properties',
            side_effect=ValueError("wikidata_properties.xlsx must contain column 'property_id'"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                verify_reference_tables('/tmp/refdir')
        self.assertIn('property_id', str(ctx.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)
