# kepubverto for Sigil — tests
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Drive `plugin.run(bk)` against a fake Sigil output container.

The windows are replaced throughout (`ui.ask_options`, `ui.show_result`):
what they look like, and whether they open in front of Sigil, can only be
judged in Sigil. `test_in_sigil.py` runs the Automate path through Sigil's own
launcher.

Set KEPUBVERTO_BINARY to a kepubverto binary for the tests that convert a
real book; without it (and without one next to the plugin) they skip.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(PLUGIN_DIR)
sys.path.insert(0, PLUGIN_DIR)

import plugin  # noqa: E402
from client import binary as bin_mod  # noqa: E402
from client import plugin_release  # noqa: E402
from client import release_dialog  # noqa: E402
from client import runner  # noqa: E402
from client import ui  # noqa: E402


OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">urn:uuid:12345678-1234-1234-1234-123456789abc</dc:identifier>
    <dc:title>T</dc:title><dc:language>en</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="Text/ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="Text/ch2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch1"/><itemref idref="ch2"/></spine>
</package>"""

NAV = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" '
       'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>T</title></head><body>'
       '<nav epub:type="toc"><ol><li><a href="Text/ch1.xhtml">Ch1</a></li></ol></nav>'
       '</body></html>')
CH1 = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">'
       '<head><title>One</title></head>'
       '<body><p>First sentence. Second sentence.</p><p>Another.</p></body></html>')
#: Not well-formed: kepubverto leaves it as it was and says so (RSC-016).
CH2 = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">'
       '<head><title>Two</title></head><body><p>Broken<p></body></html>')
CONTAINER = ('<?xml version="1.0"?>\n<container version="1.0" '
             'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
             '<rootfile full-path="OEBPS/content.opf" '
             'media-type="application/oebps-package+xml"/></rootfiles></container>')

FILES = {
    "mimetype": "application/epub+zip",
    "META-INF/container.xml": CONTAINER,
    "OEBPS/content.opf": OPF,
    "OEBPS/nav.xhtml": NAV,
    "OEBPS/Text/ch1.xhtml": CH1,
    "OEBPS/Text/ch2.xhtml": CH2,
}


def _now():
    return datetime.now(timezone.utc)


def _binary():
    path = os.environ.get("KEPUBVERTO_BINARY") or plugin._binary_path()
    return path if os.path.isfile(path) else None


class FakeBk(object):
    """The output-container methods the plugin uses, and nothing else."""

    def __init__(self, book_path, prefs=None, automate=False, files=None):
        # Seeded so the hourly update check is not due: no test may touch the
        # network.
        self.prefs = {"last_update_check": _now().isoformat()}
        self.prefs.update(prefs or {})
        self.book_path = book_path
        self.automate = automate
        self.files = files or FILES

    def getPrefs(self):
        return self.prefs

    def savePrefs(self, prefs):
        self.prefs = prefs

    def get_epub_filepath(self):
        return self.book_path

    def using_automate(self):
        return self.automate

    def copy_book_contents_to(self, destdir):
        for name, text in self.files.items():
            path = os.path.join(destdir, *name.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)


def quietly(fn, *args):
    """`(return value, stdout)`; the plugin prints its outcome line."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        value = fn(*args)
    return value, out.getvalue()


class _Windows(object):
    """Replace the two windows and the binary lookup for one test class."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kepubverto-test-")
        self.book = os.path.join(self.tmp, "My Book.epub")
        with open(self.book, "wb") as handle:
            handle.write(b"the book Sigil has open")
        self.shown = []
        self.asked = []
        self.answer = None
        self._orig = (ui.ask_options, ui.show_result, ui.available,
                      plugin._binary_path, release_dialog.launch,
                      release_dialog.available)

        def ask_options(default, hyphens, same_as_book):
            self.asked.append((default, hyphens, same_as_book))
            return self.answer
        ui.ask_options = ask_options
        ui.show_result = lambda *a: self.shown.append(a)
        ui.available = lambda: True
        release_dialog.launch = lambda *a: True
        release_dialog.available = lambda: False
        binary = _binary()
        if binary:
            plugin._binary_path = lambda: binary

    def tearDown(self):
        (ui.ask_options, ui.show_result, ui.available, plugin._binary_path,
         release_dialog.launch, release_dialog.available) = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def need_binary(self):
        if _binary() is None:
            self.skipTest("no kepubverto binary; set KEPUBVERTO_BINARY")


class NamingTests(unittest.TestCase):
    def test_the_kepub_is_named_after_the_book(self):
        self.assertEqual(plugin.kepub_name("/x/My Book.epub"),
                         "My Book.kepub.epub")
        self.assertEqual(plugin.kepub_name("/x/A.EPUB"), "A.kepub.epub")
        self.assertEqual(plugin.kepub_name("/x/B.kepub.epub"), "B.kepub.epub")
        self.assertEqual(plugin.kepub_name(None), "book.kepub.epub")

    def test_same_file_sees_through_spelling(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "a.epub")
            open(path, "w").close()
            self.assertTrue(plugin._same_file(
                path, os.path.join(tmp, ".", "a.epub")))
            self.assertFalse(plugin._same_file(path, path + "x"))
            self.assertFalse(plugin._same_file(path, None))
        finally:
            shutil.rmtree(tmp)


class SettingsTests(unittest.TestCase):
    def test_defaults_are_written_into_the_file(self):
        bk = FakeBk(None, {})
        settings = plugin._settings(bk, bk.prefs)
        self.assertEqual(settings, {"autoupdate": True, "hyphens": "book",
                                    "css": []})
        for key in ("autoupdate", "hyphens", "css"):
            self.assertIn(key, bk.prefs)

    def test_hand_typed_values(self):
        read = lambda p: plugin._settings(FakeBk(None, p), dict(p))  # noqa: E731
        self.assertFalse(read({"autoupdate": "hayır"})["autoupdate"],
                         "an unknown word must stop the network")
        self.assertTrue(read({"autoupdate": "yes"})["autoupdate"])
        self.assertEqual(read({"hyphens": "ON"})["hyphens"], "book",
                         "only the three words are understood")
        self.assertEqual(read({"hyphens": " Auto "})["hyphens"], "auto")
        self.assertEqual(read({"css": "p { margin: 0 }"})["css"],
                         ["p { margin: 0 }"])
        self.assertEqual(read({"css": ["", "  ", 4, "a { b: c }"]})["css"],
                         ["a { b: c }"])


class TargetTests(_Windows, unittest.TestCase):
    def test_the_default_is_beside_the_book(self):
        bk = FakeBk(self.book)
        self.assertEqual(plugin._default_target(bk, bk.prefs),
                         os.path.join(self.tmp, "My Book.kepub.epub"))

    def test_the_remembered_folder_wins_while_it_exists(self):
        other = os.path.join(self.tmp, "kobo")
        os.makedirs(other)
        bk = FakeBk(self.book, {"last_folder": other})
        self.assertEqual(plugin._default_target(bk, bk.prefs),
                         os.path.join(other, "My Book.kepub.epub"))
        bk = FakeBk(self.book, {"last_folder": os.path.join(self.tmp, "gone")})
        self.assertEqual(os.path.dirname(plugin._default_target(bk, bk.prefs)),
                         self.tmp)

    def test_an_unsaved_book_defaults_to_the_home_folder(self):
        bk = FakeBk("")
        self.assertEqual(plugin._default_target(bk, bk.prefs),
                         os.path.join(os.path.expanduser("~"),
                                      "book.kepub.epub"))


class AutomateTests(_Windows, unittest.TestCase):
    """In an Automate list there is no window: beside the book, never
    replacing anything."""

    def test_it_writes_beside_the_book_without_asking(self):
        self.need_binary()
        code, out = quietly(plugin.run, FakeBk(self.book, automate=True))
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(
            os.path.join(self.tmp, "My Book.kepub.epub")))
        self.assertEqual(self.asked, [])
        self.assertEqual(self.shown, [])
        self.assertIn("kepubverto:", out)

    def test_an_existing_kepub_is_not_replaced(self):
        target = os.path.join(self.tmp, "My Book.kepub.epub")
        with open(target, "wb") as handle:
            handle.write(b"older")
        code, out = quietly(plugin.run, FakeBk(self.book, automate=True))
        self.assertNotEqual(code, 0)
        self.assertIn("already exists and was not replaced", out)
        with open(target, "rb") as handle:
            self.assertEqual(handle.read(), b"older")

    def test_an_unsaved_book_has_nowhere_to_go(self):
        code, out = quietly(plugin.run, FakeBk("", automate=True))
        self.assertNotEqual(code, 0)
        self.assertIn("never been saved", out)

    def test_a_book_named_kepub_is_never_overwritten(self):
        book = os.path.join(self.tmp, "Done.kepub.epub")
        with open(book, "wb") as handle:
            handle.write(b"the open book")
        code, out = quietly(plugin.run, FakeBk(book, automate=True))
        self.assertNotEqual(code, 0)
        with open(book, "rb") as handle:
            self.assertEqual(handle.read(), b"the open book")

    def test_without_qt_it_behaves_as_in_an_automate_list(self):
        self.need_binary()
        ui.available = lambda: False
        code, out = quietly(plugin.run, FakeBk(self.book))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.asked, [])
        self.assertTrue(os.path.isfile(
            os.path.join(self.tmp, "My Book.kepub.epub")))


class WindowTests(_Windows, unittest.TestCase):
    def test_the_options_window_gets_the_default_and_the_hyphenation(self):
        bk = FakeBk(self.book, {"hyphens": "none"})
        code, _out = quietly(plugin.run, bk)
        self.assertEqual(code, 0, "cancelling is not a failure")
        default, hyphens, same_as_book = self.asked[0]
        self.assertEqual(default, os.path.join(self.tmp, "My Book.kepub.epub"))
        self.assertEqual(hyphens, "none")
        self.assertTrue(same_as_book(self.book),
                        "the window must be able to refuse the book itself")
        self.assertFalse(same_as_book(default))

    def test_cancel_writes_nothing_and_shows_nothing(self):
        code, out = quietly(plugin.run, FakeBk(self.book))
        self.assertEqual(code, 0)
        self.assertIn("cancelled", out)
        self.assertEqual(os.listdir(self.tmp), ["My Book.epub"])
        self.assertEqual(self.shown, [])

    def test_the_choice_is_converted_and_remembered(self):
        self.need_binary()
        out_dir = os.path.join(self.tmp, "kobo")
        os.makedirs(out_dir)
        target = os.path.join(out_dir, "Mine.kepub.epub")
        self.answer = (target, "auto")
        bk = FakeBk(self.book)
        code, out = quietly(plugin.run, bk)
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(target))
        self.assertEqual(bk.prefs["last_folder"], out_dir)
        self.assertEqual(bk.prefs["hyphens"], "auto")
        title, text, details, folder = self.shown[0]
        self.assertEqual(folder, out_dir)
        self.assertIn("left as they were", title,
                      "ch2.xhtml is not well-formed")
        self.assertIn("hyphenation on", text)
        self.assertTrue(any("ch2.xhtml" in d and "RSC-016" in d
                            for d in details), details)
        # The book Sigil holds is untouched.
        with open(self.book, "rb") as handle:
            self.assertEqual(handle.read(), b"the book Sigil has open")

    def test_the_kepub_is_a_real_kepub(self):
        self.need_binary()
        target = os.path.join(self.tmp, "x.kepub.epub")
        self.answer = (target, "book")
        quietly(plugin.run, FakeBk(self.book))
        with zipfile.ZipFile(target) as zf:
            self.assertEqual(zf.namelist()[0], "mimetype")
            self.assertEqual(zf.getinfo("mimetype").compress_type,
                             zipfile.ZIP_STORED)
            ch1 = zf.read("OEBPS/Text/ch1.xhtml").decode("utf-8")
            ch2 = zf.read("OEBPS/Text/ch2.xhtml").decode("utf-8")
        self.assertIn("koboSpan", ch1)
        self.assertEqual(ch2, CH2, "a document left alone is copied as it was")

    def test_an_existing_target_is_replaced_only_when_chosen(self):
        """The window asked; the plugin moves the finished file over it."""
        self.need_binary()
        target = os.path.join(self.tmp, "x.kepub.epub")
        with open(target, "wb") as handle:
            handle.write(b"older")
        self.answer = (target, "book")
        code, out = quietly(plugin.run, FakeBk(self.book))
        self.assertEqual(code, 0, out)
        with open(target, "rb") as handle:
            self.assertNotEqual(handle.read(), b"older")

    def test_a_refused_css_is_explained_and_writes_nothing(self):
        self.need_binary()
        target = os.path.join(self.tmp, "x.kepub.epub")
        self.answer = (target, "book")
        bk = FakeBk(self.book, {"css": ["@font-face { font-family: x }"]})
        code, out = quietly(plugin.run, bk)
        self.assertNotEqual(code, 0)
        self.assertFalse(os.path.exists(target))
        title, text, _details, folder = self.shown[0]
        self.assertIn("not converted", title)
        self.assertIn("refused", text)
        self.assertIsNone(folder)

    def test_converting_a_kepub_again_says_so(self):
        self.need_binary()
        first = os.path.join(self.tmp, "a.kepub.epub")
        self.answer = (first, "book")
        quietly(plugin.run, FakeBk(self.book))
        files = {}
        with zipfile.ZipFile(first) as zf:
            for name in zf.namelist():
                files[name] = zf.read(name).decode("utf-8")
        second = os.path.join(self.tmp, "b.kepub.epub")
        self.answer = (second, "book")
        self.shown = []
        quietly(plugin.run, FakeBk(self.book, files=files))
        self.assertIn("already carries Kobo's markup", self.shown[0][1])

    def test_no_temporary_folder_is_left_behind(self):
        self.need_binary()
        before = set(os.listdir(tempfile.gettempdir()))
        self.answer = (os.path.join(self.tmp, "x.kepub.epub"), "book")
        quietly(plugin.run, FakeBk(self.book))
        after = set(os.listdir(tempfile.gettempdir()))
        self.assertEqual([n for n in after - before
                          if n.startswith("kepubverto-sigil-")], [])


class CommandTests(unittest.TestCase):
    def test_as_the_book_says_passes_no_hyphens(self):
        cmd = runner.command("k", "in.epub", "out.kepub.epub", None, [])
        self.assertNotIn("--hyphens", cmd)
        cmd = runner.command("k", "in.epub", "out.kepub.epub", "none",
                             ["p { a: b }"])
        self.assertEqual(cmd[cmd.index("--hyphens") + 1], "none")
        self.assertEqual(cmd[cmd.index("--css") + 1], "p { a: b }")
        self.assertNotIn("-f", cmd, "the output is always a fresh path")


class BinaryTests(unittest.TestCase):
    """The parts of the update path that differ from epubveri for Sigil's."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fake = os.path.join(self.tmp, "kepubverto")
        with open(self.fake, "wb") as handle:
            handle.write(b"verified")
        self._orig = (plugin._binary_path, bin_mod.latest_checksums,
                      bin_mod.download_binary, runner.binary_version,
                      plugin_release.latest_version)
        plugin._binary_path = lambda: self.fake
        self.release_checks = 0

        def latest_version(timeout=None):
            self.release_checks += 1
            return "9.9.9"
        plugin_release.latest_version = latest_version

    def tearDown(self):
        (plugin._binary_path, bin_mod.latest_checksums,
         bin_mod.download_binary, runner.binary_version,
         plugin_release.latest_version) = self._orig
        shutil.rmtree(self.tmp)

    def test_the_asset_is_kepubvertos(self):
        name = bin_mod.asset_name()
        if name is not None:
            self.assertTrue(name.startswith("kepubverto-"), name)
        self.assertEqual(bin_mod.REPO, "veripublica/kepubverto")
        self.assertIn(bin_mod.binary_filename(),
                      ("kepubverto", "kepubverto.exe"))

    def test_a_replaced_binary_is_not_run(self):
        good = bin_mod.sha256_of(self.fake)
        bk = FakeBk(None, {"binary_sha256": good})
        with open(self.fake, "wb") as handle:
            handle.write(b"something else")
        path, note = plugin._ensure_binary(bk, True)
        self.assertIsNone(path)
        self.assertIn("has changed since it was verified", note)

    def test_the_hourly_check_also_records_the_plugin_release(self):
        bin_mod.latest_checksums = lambda timeout=None: {}
        bk = FakeBk(None, {"last_update_check": None,
                           "binary_sha256": bin_mod.sha256_of(self.fake)})
        plugin._ensure_binary(bk, True)
        self.assertEqual(bk.prefs["latest_plugin_version"], "9.9.9")

    def test_updates_off_asks_nothing(self):
        def boom(timeout=None):
            raise AssertionError("asked the network")
        bin_mod.latest_checksums = boom
        bk = FakeBk(None, {"last_update_check": None,
                           "binary_sha256": bin_mod.sha256_of(self.fake)})
        path, _note = plugin._ensure_binary(bk, False)
        self.assertEqual(path, self.fake)
        self.assertEqual(self.release_checks, 0)

    def test_an_old_binary_is_refused_with_a_reason(self):
        runner.binary_version = lambda b, timeout=15: "kepubverto 0.2.9"
        self.assertIn("needs kepubverto 0.3.0", plugin._too_old(self.fake))
        runner.binary_version = lambda b, timeout=15: "kepubverto 0.5.3+abc"
        self.assertIsNone(plugin._too_old(self.fake))


class ReleaseNoticeTests(unittest.TestCase):
    def test_the_readme_table_offers_this_version(self):
        """The root README's download table is how people find the zip, and
        it is bumped in the same release commit as plugin.xml and
        latest.json. A stale row sends people to an older release."""
        version = plugin._plugin_version()
        base = "https://github.com/veripublica/sigil-plugins/releases/"
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as h:
            readme = h.read()
        for wanted in ("[%s](%stag/%s-v%s)" % (version, base, 'kepubverto', version),
                       "%sdownload/%s-v%s/%s_sigil_v%s.zip"
                       % (base, 'kepubverto', version, 'kepubverto', version)):
            self.assertIn(wanted, readme)

    def test_latest_json_names_this_plugins_own_version(self):
        with open(os.path.join(ROOT, "latest.json"), encoding="utf-8") as h:
            self.assertEqual(plugin_release.read_latest(h.read()),
                             plugin._plugin_version())

    def test_the_link_is_this_plugins_release_page(self):
        self.assertEqual(
            plugin_release.release_page("0.2.0"),
            "https://github.com/veripublica/sigil-plugins/releases/tag/"
            "kepubverto-v0.2.0")

    def test_the_note_and_the_window(self):
        self.assertIsNone(plugin._plugin_release_note({}))
        self.assertIn("kepubverto for Sigil 99.0.0 is available",
                      plugin._plugin_release_note(
                          {"latest_plugin_version": "99.0.0"}))
        self.assertIsNone(plugin._plugin_release_note(
            {"latest_plugin_version": "99.0.0",
             "ignored_plugin_version": "99.0.0"}))

        launched = []
        orig = (release_dialog.launch, release_dialog.available)
        release_dialog.launch = lambda *a: launched.append(a) or True
        release_dialog.available = lambda: True
        try:
            plugin._offer_plugin_release(
                FakeBk(None, {"latest_plugin_version": "99.0.0"},
                       automate=True))
            self.assertEqual(launched, [], "never in an Automate list")
            bk = FakeBk(None, {"latest_plugin_version": "99.0.0"})
            plugin._offer_plugin_release(bk)
            self.assertEqual(len(launched), 1)
            self.assertIn("plugin_notice_shown", bk.prefs)
        finally:
            release_dialog.launch, release_dialog.available = orig

    def test_the_ignored_key_matches(self):
        self.assertEqual(release_dialog.IGNORED_KEY,
                         plugin._IGNORED_PLUGIN_KEY)

    def test_the_window_process_holds_none_of_sigils_pipes(self):
        seen = {}

        class FakePopen(object):
            def __init__(self, args, **kwargs):
                seen["kwargs"] = kwargs
        real = subprocess.Popen
        subprocess.Popen = FakePopen
        try:
            release_dialog.launch("1.0.0", "0.1.0", "https://x", None)
        finally:
            subprocess.Popen = real
        for stream in ("stdin", "stdout", "stderr"):
            self.assertIs(seen["kwargs"][stream], subprocess.DEVNULL)


class PackageTests(unittest.TestCase):
    def test_the_zip_is_named_and_laid_out_for_sigil(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "kepubverto_build", os.path.join(PLUGIN_DIR, "build.py"))
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        tmp = tempfile.mkdtemp()
        real = build.DIST
        build.DIST = tmp
        try:
            path = build.build()
            name = os.path.basename(path)
            self.assertTrue(name.startswith("kepubverto_"), name)
            self.assertEqual(name, "kepubverto_sigil_v%s.zip"
                             % plugin._plugin_version())
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
        finally:
            build.DIST = real
            shutil.rmtree(tmp)
        self.assertTrue(all(n.startswith("kepubverto/") for n in names), names)
        for wanted in ("kepubverto/plugin.xml", "kepubverto/plugin.py",
                       "kepubverto/LICENSE", "kepubverto/client/ui.py"):
            self.assertIn(wanted, names)
        for name in names:
            self.assertNotIn("/tests/", name)
            self.assertNotIn("__pycache__", name)
            self.assertNotIn(name, ("kepubverto/kepubverto",
                                    "kepubverto/kepubverto.exe",
                                    "kepubverto/build.py",
                                    "kepubverto/icon.py"))

    def test_plugin_xml_says_output(self):
        with open(os.path.join(PLUGIN_DIR, "plugin.xml"),
                  encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("<type>output</type>", text)
        self.assertIn("<name>kepubverto</name>", text)


class IconTests(unittest.TestCase):
    def _icon(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "kepubverto_sigil_icon", os.path.join(PLUGIN_DIR, "icon.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_shipped_svg_is_the_one_icon_py_writes(self):
        with open(os.path.join(PLUGIN_DIR, "plugin.svg"),
                  encoding="utf-8") as handle:
            self.assertEqual(handle.read(), self._icon().SVG,
                             "plugin.svg was hand-edited; run icon.py")

    def test_the_shipped_png_is_the_one_icon_py_draws(self):
        icon = self._icon()
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            icon.write_png(path, 128)
            with open(path, "rb") as a, open(
                    os.path.join(PLUGIN_DIR, "plugin.png"), "rb") as b:
                self.assertEqual(a.read(), b.read(),
                                 "plugin.png does not match; run icon.py")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
