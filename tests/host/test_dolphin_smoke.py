"""Tests for the Dolphin runner's command line (tools/dolphin_smoke.py).

The runner starts Dolphin with per-run configuration overrides into an
isolated user directory; nothing depends on the user's own Dolphin profile.
Every screenshot the project keeps must show only the POC's framebuffer,
so the on-screen-display overlay ("Video Info: …", "USBGecko: Listening on
TCP port …", backend messages) is disabled by an override on every run.
"""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import dolphin_smoke  # noqa: E402


def pairs(cmd):
    """(-C value) overrides of a runner command line, in order."""
    return [cmd[i + 1] for i in range(len(cmd) - 1) if cmd[i] == "-C"]


class DolphinCommand(unittest.TestCase):
    def setUp(self):
        self.cmd = dolphin_smoke.dolphin_cmd("/x/y.dol", "/tmp/userdir", [])
        self.overrides = pairs(self.cmd)

    def test_batch_exec_and_isolated_user_dir(self):
        self.assertIn("--batch", self.cmd)
        self.assertIn("--exec=/x/y.dol", self.cmd)
        self.assertIn("--user=/tmp/userdir", self.cmd)
        self.assertEqual(self.cmd[:3], ["flatpak", "run", dolphin_smoke.FLATPAK_ID])

    def test_osd_overlay_disabled_on_every_run(self):
        # Dolphin: [Interface] OnScreenDisplayMessages gates OSD::DrawMessages
        # (VideoCommon/OnScreenDisplay.cpp); false = no yellow overlay text.
        self.assertIn("Dolphin.Interface.OnScreenDisplayMessages=False", self.overrides)
        i = self.cmd.index("Dolphin.Interface.OnScreenDisplayMessages=False")
        self.assertEqual(self.cmd[i - 1], "-C")

    def test_only_the_expected_interface_keys_are_overridden(self):
        iface = sorted(o for o in self.overrides if o.startswith("Dolphin.Interface."))
        self.assertEqual(iface, ["Dolphin.Interface.OnScreenDisplayMessages=False",
                                 "Dolphin.Interface.UsePanicHandlers=False"])

    def test_gecko_slot_and_no_analytics(self):
        self.assertIn("Dolphin.Core.SlotB=%d" % dolphin_smoke.EXI_DEVICE_GECKO, self.overrides)
        self.assertIn("Dolphin.Analytics.Enabled=False", self.overrides)
        self.assertNotIn("Dolphin.Core.HSPDevice=2", self.overrides)   # only when a caller asks for it

    def test_extra_config_comes_last_so_it_can_override(self):
        cmd = dolphin_smoke.dolphin_cmd("/x/y.dol", "/tmp/userdir", ["Dolphin.Core.HSPDevice=2"])
        ov = pairs(cmd)
        self.assertEqual(ov[-1], "Dolphin.Core.HSPDevice=2")
        self.assertIn("Dolphin.Interface.OnScreenDisplayMessages=False", ov)


if __name__ == "__main__":
    unittest.main()
