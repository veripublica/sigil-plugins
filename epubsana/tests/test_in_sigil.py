# epubsana for Sigil — tests through Sigil's own plugin launcher
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Run the plugin as an edit plugin through the installed Sigil's
`launcher.py`, headless, in Automate mode (the only mode with no window).

This is the test that matters most for this plugin: the repair is written
into Sigil's real `BookContainer`, read back out of it and verified, and the
launcher's result says what Sigil would take.

Skips without Sigil (SIGIL_APP for a non-default install) or without an
epubsana binary (EPUBSANA_BINARY, or one next to the plugin).
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)

SIGIL = os.environ.get("SIGIL_APP", "/Applications/Sigil.app/Contents")
LAUNCHER = os.path.join(SIGIL, "plugin_launchers", "python", "launcher.py")


def _sigil_python():
    versions = os.path.join(SIGIL, "Frameworks", "Python.framework", "Versions")
    if os.path.isdir(versions):
        for name in sorted(os.listdir(versions), reverse=True):
            if name == "Current":
                continue
            candidate = os.path.join(versions, name, "bin", "python3")
            if os.path.isfile(candidate):
                return candidate
    return sys.executable


def _binary():
    explicit = os.environ.get("EPUBSANA_BINARY")
    if explicit and os.path.isfile(explicit):
        return explicit
    candidate = os.path.join(PLUGIN_DIR, "epubsana")
    return candidate if os.path.isfile(candidate) else None


def _why_skip():
    if not os.path.isfile(LAUNCHER):
        return "Sigil is not installed (no launcher.py at %s)" % LAUNCHER
    if _binary() is None:
        return ("no epubsana binary; put one at epubsana/epubsana or set "
                "EPUBSANA_BINARY")
    return None


SKIP = _why_skip()


def _fixture():
    spec = importlib.util.spec_from_file_location(
        "epubsana_sigil_fixture", os.path.join(TESTS_DIR, "test_plugin.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Run(object):
    def __init__(self, proc, out_files):
        self.proc = proc
        self.out_files = out_files
        start = proc.stdout.find("<wrapper")
        end = proc.stdout.find("</wrapper>")
        self.xml = proc.stdout[start:end + len("</wrapper>")] \
            if start >= 0 else ""

    @property
    def result(self):
        return ET.fromstring(self.xml).findtext("result")

    @property
    def modified(self):
        return sorted(e.get("href") for e in ET.fromstring(self.xml).iter()
                      if e.tag in ("modified", "added", "deleted"))


def run_in_sigil(files):
    tmp = tempfile.mkdtemp(prefix="sigil-edit-")
    try:
        root = os.path.join(tmp, "root")
        out = os.path.join(tmp, "out")
        target = os.path.join(tmp, "plugins", "epubsana")
        usrsup = os.path.join(tmp, "usrsup")
        for path in (root, out, target, usrsup):
            os.makedirs(path)
        _fixture().write_tree(root, files)

        for name in ("plugin.py", "plugin.xml"):
            shutil.copy2(os.path.join(PLUGIN_DIR, name), target)
        shutil.copytree(os.path.join(PLUGIN_DIR, "client"),
                        os.path.join(target, "client"))
        binary = os.path.join(target, "epubsana")
        shutil.copy2(_binary(), binary)
        os.chmod(binary, 0o755)

        prefs_dir = os.path.join(tmp, "plugins_prefs", "epubsana")
        os.makedirs(prefs_dir)
        with open(os.path.join(prefs_dir, "epubsana.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"autoupdate": False}, handle)

        with open(os.path.join(out, "sigil.cfg"), "w",
                  encoding="utf-8") as handle:
            handle.write("\n".join([
                "OEBPS/content.opf", os.path.join(SIGIL, "MacOS"), usrsup,
                "en", "en_US", "False", os.path.join(tmp, "book.epub"),
                "light", "", "detect", "", "InAutomate", "", "", ""]))

        proc = subprocess.run(
            [_sigil_python(), LAUNCHER, root, out, "edit",
             os.path.join(target, "plugin.py")],
            capture_output=True, text=True, timeout=600)
        out_files = {}
        for base, _dirs, names in os.walk(out):
            for name in names:
                full = os.path.join(base, name)
                rel = os.path.relpath(full, out).replace(os.sep, "/")
                with open(full, "rb") as handle:
                    out_files[rel] = handle.read()
        return Run(proc, out_files)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipIf(SKIP, SKIP or "")
class LauncherTests(unittest.TestCase):

    def test_an_automate_run_applies_only_the_safe_fix(self):
        run = run_in_sigil(_fixture().FILES)
        self.assertEqual(run.proc.returncode, 0, run.proc.stderr[:2000])
        self.assertEqual(run.result, "success", run.xml[:3000])
        # fix.html_entities touches ch2 alone; the confirm_needed fixes in
        # the OPF and the NCX are not applied, so the OPF is not modified.
        self.assertEqual(run.modified, ["OEBPS/Text/ch2.xhtml"], run.xml)
        ch2 = run.out_files["OEBPS/Text/ch2.xhtml"].decode("utf-8")
        self.assertNotIn("&nbsp;", ch2)
        self.assertIn("Left to right", ch2)
        self.assertIn("Applied 1 fix(es)", run.xml)

    def test_a_book_without_a_safe_fix_is_left_alone(self):
        files = dict(_fixture().FILES)
        # Without the entity ch2 parses, and its `dir="LTR"` is then a second
        # auto_safe fix (fix.dir_case); both go.
        files["OEBPS/Text/ch2.xhtml"] = files["OEBPS/Text/ch2.xhtml"].replace(
            "&nbsp;", " ").replace('dir="LTR"', 'dir="ltr"')
        run = run_in_sigil(files)
        self.assertEqual(run.result, "success", run.xml[:3000])
        self.assertEqual(run.modified, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
