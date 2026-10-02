"""The rule the 2026-10-01 incident bought: the GUI thread never reads the keychain directly.

WHY THIS EXISTS. `ui/settings_dialog.py` and `ui/mapping_panel.py` called
`credential_storage.load_morpheus_token()` on the Qt GUI thread. On macOS that read goes through
Python `keyring` to `/usr/bin/security`, which raises an authorisation prompt; the window rendered
half-built, clicks did nothing, and the Connect dialog that would have started the device login
never ran. A pure-function test cannot see which thread a call is on, and this suite cannot build a
QDialog, so the thing that can be checked here is the shape of the code: every GUI module must hand
the read to `ui.keychain_read.KeychainRead` instead of calling it.

That is deliberately narrow. It catches `credential_storage.load_x(...)` inside `ui/`, not an
indirect read buried in a core function -- those are called from worker threads already, and a
source scan claiming more than it can prove is exactly the "a check that never ran reads as a check
that passed" trap.

Standard-library only, like the rest of this suite.
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# A direct call: the loader name followed by "(". Passing the function itself to KeychainRead
# (no parentheses) is the correct, GUI-safe form.
_DIRECT_CALL = re.compile(r'credential_storage\.load_\w+\s*\(')


class NoDirectKeychainReadInGuiTest(unittest.TestCase):
    def test_every_ui_module_goes_through_the_keychain_helper(self):
        ui_dir = REPO / 'ui'
        self.assertTrue(ui_dir.is_dir(), 'the ui package moved; this guard needs updating')
        offenders = []
        for path in sorted(ui_dir.glob('*.py')):
            text = path.read_text(encoding='utf-8')
            for number, line in enumerate(text.splitlines(), 1):
                code = line.split('#', 1)[0]
                if _DIRECT_CALL.search(code):
                    offenders.append(f'{path.name}:{number}: {line.strip()}')
        self.assertEqual(
            offenders, [],
            'credential_storage.load_* must be read through ui.keychain_read.KeychainRead, off the '
            'GUI thread:\n' + '\n'.join(offenders),
        )

    def test_the_guard_would_actually_catch_a_direct_call(self):
        # Negative-tested, because a regex that matches nothing looks exactly like a clean repo.
        self.assertTrue(_DIRECT_CALL.search('token = credential_storage.load_morpheus_token()'))
        self.assertTrue(_DIRECT_CALL.search('creds = credential_storage.load_credentials( )'))
        self.assertFalse(_DIRECT_CALL.search(
            'read = KeychainRead(credential_storage.load_morpheus_token, parent=self)'))
        self.assertFalse(_DIRECT_CALL.search(
            'self._read = KeychainRead(credential_storage.load_credentials, parent=self)'))


if __name__ == '__main__':
    unittest.main()
