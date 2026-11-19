# kepubverto for Sigil — tests through Sigil's own plugin launcher
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Run the plugin through the `launcher.py` of the installed Sigil, headless.

`test_plugin.py`'s container is our idea of Sigil's `OutputContainer`; this
file's is Sigil's. It runs the Automate path, the only one with no window:
`sigil.cfg` says `InAutomate`, so the plugin writes beside the book.

Skips without Sigil (set SIGIL_APP for a non-default install) or without a
kepubverto binary (KEPUBVERTO_BINARY, or one next to the plugin).

    python3 kepubverto/tests/test_in_sigil.py
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
import zipfile

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
    explicit = os.environ.get("KEPUBVERTO_BINARY")
    if explicit and os.path.isfile(explicit):
        return explicit
    candidate = os.path.join(PLUGIN_DIR, "kepubverto")
    return candidate if os.path.isfile(candidate) else None


def _why_skip():
    if not os.path.isfile(LAUNCHER):
        return "Sigil is not installed (no launcher.py at %s)" % LAUNCHER
    if _binary() is None:
        return ("no kepubverto binary; put one at kepubverto/kepubverto "
                "or set KEPUBVERTO_BINARY")
    return None


SKIP = _why_skip()


def _fixture():
    spec = importlib.util.spec_from_file_location(
        "kepubverto_sigil_fixture", os.path.join(TESTS_DIR, "test_plugin.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_in_sigil(existing=None):
    """Stage a plugin, a book and a Sigil config, run the launcher in
    Automate mode, and return `(proc, files beside the book, xml)`."""
    fixture = _fixture()
    tmp = tempfile.mkdtemp(prefix="sigil-launch-")
    try:
        root = os.path.join(tmp, "root")
        out = os.path.join(tmp, "out")
        target = os.path.join(tmp, "plugins", "kepubverto")
        usrsup = os.path.join(tmp, "usrsup")
        shelf = os.path.join(tmp, "shelf")
        for path in (root, out, target, usrsup, shelf):
            os.makedirs(path)
        for name, text in fixture.FILES.items():
            path = os.path.join(root, *name.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)

        for name in ("plugin.py", "plugin.xml"):
            shutil.copy2(os.path.join(PLUGIN_DIR, name), target)
        shutil.copytree(os.path.join(PLUGIN_DIR, "client"),
                        os.path.join(target, "client"))
        binary = os.path.join(target, "kepubverto")
        shutil.copy2(_binary(), binary)
        os.chmod(binary, 0o755)

        prefs_dir = os.path.join(tmp, "plugins_prefs", "kepubverto")
        os.makedirs(prefs_dir)
        # `autoupdate` off: a suite that reaches the network fails on a train.
        with open(os.path.join(prefs_dir, "kepubverto.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"autoupdate": False}, handle)

        book = os.path.join(shelf, "Shelf Book.epub")
        with open(book, "wb") as handle:
            handle.write(b"the file Sigil opened")
        if existing is not None:
            with open(os.path.join(shelf, "Shelf Book.kepub.epub"),
                      "wb") as handle:
                handle.write(existing)

        # Sigil's settings lines, in `launcher.py`'s order; the twelfth says
        # whether the run is part of an Automate list.
        with open(os.path.join(out, "sigil.cfg"), "w",
                  encoding="utf-8") as handle:
            handle.write("\n".join([
                "OEBPS/content.opf", os.path.join(SIGIL, "MacOS"), usrsup,
                "en", "en_US", "False", book,
                "light", "", "detect", "", "InAutomate", "", "", ""]))

        proc = subprocess.run(
            [_sigil_python(), LAUNCHER, root, out, "output",
             os.path.join(target, "plugin.py")],
            capture_output=True, text=True, timeout=180)
        written = {}
        for name in sorted(os.listdir(shelf)):
            with open(os.path.join(shelf, name), "rb") as handle:
                written[name] = handle.read()
        start = proc.stdout.find("<wrapper")
        end = proc.stdout.find("</wrapper>")
        xml = proc.stdout[start:end + len("</wrapper>")] if start >= 0 else ""
        return proc, written, xml
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipIf(SKIP, SKIP or "")
class LauncherTests(unittest.TestCase):

    def test_an_automate_run_writes_the_kepub_beside_the_book(self):
        proc, written, xml = run_in_sigil()
        self.assertEqual(proc.returncode, 0, proc.stderr[:2000])
        self.assertEqual(ET.fromstring(xml).findtext("result"), "success",
                         xml[:2000])
        self.assertEqual(sorted(written),
                         ["Shelf Book.epub", "Shelf Book.kepub.epub"])
        self.assertEqual(written["Shelf Book.epub"], b"the file Sigil opened",
                         "the book's own file must never be touched")
        path = tempfile.mkstemp(suffix=".epub")[1]
        try:
            with open(path, "wb") as handle:
                handle.write(written["Shelf Book.kepub.epub"])
            with zipfile.ZipFile(path) as zf:
                self.assertIn("koboSpan",
                              zf.read("OEBPS/Text/ch1.xhtml").decode("utf-8"))
        finally:
            os.unlink(path)
        # The outcome line reaches Sigil's log through `<msg>`.
        self.assertIn("kepubverto: Converted", xml)

    def test_an_existing_kepub_survives_an_automate_run(self):
        proc, written, xml = run_in_sigil(existing=b"older")
        self.assertEqual(written["Shelf Book.kepub.epub"], b"older")
        self.assertEqual(ET.fromstring(xml).findtext("result"), "failed",
                         xml[:2000])
        self.assertIn("already exists and was not replaced", xml)


if __name__ == "__main__":
    unittest.main(verbosity=2)
