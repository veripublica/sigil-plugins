# epubsana for Sigil — tests
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""The plan, the choice, the write-back and its refusals.

`writeback` is tested against **Sigil's own `Opf_Parser`**, taken from the
installed Sigil; without Sigil those tests skip. The whole repair, written
into a real `BookContainer` and read back, runs in `test_in_sigil.py`
through Sigil's launcher. The windows are replaced here: what they look like
can only be judged in Sigil.

Set EPUBSANA_BINARY to an epubsana binary for the tests that run it.
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

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(PLUGIN_DIR)
sys.path.insert(0, PLUGIN_DIR)

SIGIL = os.environ.get("SIGIL_APP", "/Applications/Sigil.app/Contents")
LAUNCHER_DIR = os.path.join(SIGIL, "plugin_launchers", "python")
if os.path.isfile(os.path.join(LAUNCHER_DIR, "opf_parser.py")):
    sys.path.append(LAUNCHER_DIR)

import plugin  # noqa: E402
from client import envelope as env_mod  # noqa: E402
from client import plugin_release  # noqa: E402
from client import release_dialog  # noqa: E402
from client import runner  # noqa: E402
from client import ui  # noqa: E402
from client import writeback  # noqa: E402

try:
    from opf_parser import Opf_Parser  # noqa: E402
except ImportError:                    # no Sigil installed
    Opf_Parser = None


OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="uid">urn:uuid:12345678-1234-1234-1234-123456789abc</dc:identifier>
    <dc:title>Proto</dc:title><dc:language>en</dc:language>
    <dc:date></dc:date>
    <dc:publisher></dc:publisher>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="ch1" href="Text/ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="Text/ch2.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="Styles/s.css" media-type="text/css"/>
  </manifest>
  <spine toc="ncx"><itemref idref="ch1"/><itemref idref="ch2"/><itemref idref="ch1"/></spine>
  <guide><reference type="toc" title="Contents" href="Text/missing.xhtml"/></guide>
</package>"""
NCX = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:12345678-1234-1234-1234-123456789abc"/></head>
  <docTitle><text>Proto</text></docTitle>
  <navMap>
    <navPoint id="n1" playOrder="1"><navLabel><text>One</text></navLabel><content src="Text/ch1.xhtml"/></navPoint>
    <navPoint id="n2" playOrder="1"><navLabel><text>Two</text></navLabel><content src="Text/ch2.xhtml"/></navPoint>
  </navMap>
</ncx>"""
DOCTYPE = ('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
           '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">')
CH1 = ('<?xml version="1.0" encoding="utf-8"?>\n' + DOCTYPE +
       '\n<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title>'
       '<link href="../Styles/s.css" rel="stylesheet" type="text/css"/></head>'
       '<body><p>Caf&eacute; and a break<br clear="all"/>here.</p></body></html>')
#: No DOCTYPE, so `&nbsp;` is undeclared: a fatal error and the one
#: `auto_safe` fix in this book (fix.html_entities).
CH2 = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">'
       '<head><title></title></head><body><h1>Second chapter</h1><p lang="">Text</p>'
       '<p dir="LTR">Left&nbsp;to right</p></body></html>')
CSS = "p { margin: 0 }\n"
CONTAINER = ('<?xml version="1.0"?>\n<container version="1.0" '
             'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
             '<rootfile full-path="OEBPS/content.opf" '
             'media-type="application/oebps-package+xml"/></rootfiles></container>')

FILES = {
    "mimetype": "application/epub+zip",
    "META-INF/container.xml": CONTAINER,
    "OEBPS/content.opf": OPF,
    "OEBPS/toc.ncx": NCX,
    "OEBPS/Text/ch1.xhtml": CH1,
    "OEBPS/Text/ch2.xhtml": CH2,
    "OEBPS/Styles/s.css": CSS,
}

IDS = {"OEBPS/toc.ncx": "ncx", "OEBPS/Text/ch1.xhtml": "ch1",
       "OEBPS/Text/ch2.xhtml": "ch2", "OEBPS/Styles/s.css": "css"}


def _binary():
    path = os.environ.get("EPUBSANA_BINARY") or plugin._binary_path()
    return path if os.path.isfile(path) else None


def write_tree(root, files):
    for name, text in files.items():
        path = os.path.join(root, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)


class RecordingBk(object):
    """Enough of Sigil's edit container to plan against, recording calls."""

    def __init__(self, prefs=None, automate=False):
        self.prefs = dict(prefs or {})
        self.automate = automate
        self.calls = []

    def getPrefs(self):
        return self.prefs

    def savePrefs(self, prefs):
        self.prefs = prefs

    def using_automate(self):
        return self.automate

    def get_opfbookpath(self):
        return "OEBPS/content.opf"

    def bookpath_to_id(self, path):
        return IDS.get(path)

    def copy_book_contents_to(self, destdir):
        write_tree(destdir, FILES)

    def __getattr__(self, name):
        if name.startswith(("set", "write", "delete")):
            return lambda *a: self.calls.append((name,) + a)
        raise AttributeError(name)


def item(index, fix_id, tier, outcome="proposed", paths=("a.xhtml",)):
    return {"type": "fix", "outcome": outcome, "code": "RSC-005",
            "rule": "r", "severity": "error", "location": paths[0],
            "message": "do %s" % fix_id,
            "data": {"index": index, "fix_id": fix_id, "tier": tier,
                     "changes": [{"path": p, "note": "n"} for p in paths]}}


def envelope(items, **summary):
    return env_mod.Envelope({"tool": "epubsana", "tool_version": "0.42.0+x",
                             "inputs": [{"status": "problems",
                                         "summary": summary,
                                         "items": items}]})


class EnvelopeTests(unittest.TestCase):
    def test_counts_before_and_after_keep_fatals_apart(self):
        e = envelope([], fatals_before=2, errors_before=5, errors_after=1)
        self.assertEqual(e.counts("before")["fatals"], 2)
        self.assertEqual(e.counts("before")["errors"], 5)
        self.assertEqual(e.counts("after")["errors"], 1)
        self.assertEqual(e.counts("after")["fatals"], 0)

    def test_fix_fields(self):
        e = envelope([item(3, "fix.x", "auto_safe",
                           paths=("b.xhtml", "a.xhtml", "b.xhtml"))])
        fix = e.fixes[0]
        self.assertEqual((fix.index, fix.fix_id, fix.outcome), (3, "fix.x",
                                                                "proposed"))
        self.assertTrue(fix.auto_safe)
        self.assertEqual(fix.paths, ["b.xhtml", "a.xhtml"])

    def test_no_envelope_raises_with_stderr(self):
        with self.assertRaises(env_mod.EnvelopeError) as cm:
            env_mod.parse_envelope(b"", b"error: no such file\n", 2)
        self.assertIn("no such file", str(cm.exception))


class CommandTests(unittest.TestCase):
    def test_the_two_command_lines(self):
        self.assertEqual(runner.plan_command("s", "in.epub"),
                         ["s", "-i", "in.epub", "--dry-run", "--format",
                          "json"])
        cmd = runner.apply_command("s", "in.epub", "out.epub", [1, 4])
        self.assertEqual(cmd[cmd.index("--apply") + 1], "1,4")
        self.assertNotIn("-f", cmd)
        self.assertNotIn("-y", cmd, "--apply asks nothing; -y would apply all")


class PlanSplitTests(unittest.TestCase):
    def test_fixes_sigil_cannot_take_are_shown_but_not_offered(self):
        e = envelope([item(1, "fix.html_entities", "auto_safe"),
                      item(2, "fix.package_version", "confirm_needed"),
                      item(3, "fix.html_media_type", "confirm_needed"),
                      item(4, "fix.ncx_play_order", "confirm_needed")])
        offered, unavailable = plugin.split_plan(e)
        self.assertEqual([f.index for f in offered], [1, 4])
        self.assertEqual([f.index for f, _r in unavailable], [2, 3])
        self.assertIn("version", unavailable[0][1])

    def test_only_proposals_are_offered(self):
        e = envelope([item(1, "fix.a", "auto_safe", outcome="applied")])
        self.assertEqual(plugin.split_plan(e), ([], []))


@unittest.skipIf(Opf_Parser is None, "Sigil is not installed")
class WritebackTests(unittest.TestCase):
    """`plan` against two folders, read by Sigil's own parser."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.before = os.path.join(self.tmp, "before")
        self.after = os.path.join(self.tmp, "after")
        write_tree(self.before, FILES)
        write_tree(self.after, FILES)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, path, old, new):
        full = os.path.join(self.after, *path.split("/"))
        with open(full, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn(old, text)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text.replace(old, new))

    def plan(self):
        bk = RecordingBk()
        ops = writeback.plan(bk, self.before, self.after, Opf_Parser)
        writeback.apply(ops)
        return bk.calls

    def test_nothing_changed_means_no_call(self):
        self.assertEqual(self.plan(), [])

    def test_a_changed_document_is_written_by_id(self):
        self.edit("OEBPS/Text/ch2.xhtml", "&nbsp;", " ")
        calls = self.plan()
        self.assertEqual([c[:2] for c in calls], [("writefile", "ch2")])
        self.assertIn(" ".encode("utf-8"), calls[0][2])

    def test_opf_changes_go_through_the_setters(self):
        self.edit("OEBPS/content.opf", "<dc:date></dc:date>", "")
        self.edit("OEBPS/content.opf",
                  '<itemref idref="ch2"/><itemref idref="ch1"/>',
                  '<itemref idref="ch2"/>')
        self.edit("OEBPS/content.opf",
                  '<guide><reference type="toc" title="Contents" '
                  'href="Text/missing.xhtml"/></guide>', "")
        names = [c[0] for c in self.plan()]
        self.assertEqual(sorted(names), ["setguide", "setmetadataxml",
                                         "setspine"])

    def test_a_removed_manifest_item_is_deleted(self):
        self.edit("OEBPS/content.opf",
                  '<item id="css" href="Styles/s.css" media-type="text/css"/>',
                  "")
        os.remove(os.path.join(self.after, "OEBPS", "Styles", "s.css"))
        self.assertIn(("deletefile", "css"), self.plan())

    def test_refusals_happen_before_any_call(self):
        cases = [
            ("a version change", "OEBPS/content.opf", 'version="2.0"',
             'version="3.0"'),
            ("a media-type change", "OEBPS/content.opf",
             'href="Styles/s.css" media-type="text/css"',
             'href="Styles/s.css" media-type="text/plain"'),
            ("a moved file", "OEBPS/content.opf", 'href="Styles/s.css"',
             'href="Styles/t.css"'),
            ("a new manifest item", "OEBPS/content.opf", "</manifest>",
             '<item id="x" href="x.css" media-type="text/css"/></manifest>'),
        ]
        for label, path, old, new in cases:
            write_tree(self.after, FILES)
            # Also change a document, so a partial apply would show.
            self.edit("OEBPS/Text/ch2.xhtml", "&nbsp;", " ")
            self.edit(path, old, new)
            bk = RecordingBk()
            with self.assertRaises(writeback.Unmappable, msg=label):
                writeback.plan(bk, self.before, self.after, Opf_Parser)
            self.assertEqual(bk.calls, [], label)

    def test_a_new_file_is_refused(self):
        write_tree(self.after, {"OEBPS/extra.xhtml": "<x/>"})
        with self.assertRaises(writeback.Unmappable):
            writeback.plan(RecordingBk(), self.before, self.after, Opf_Parser)

    def test_verify_names_every_difference(self):
        bk = RecordingBk()
        self.assertEqual(writeback.verify(bk, self.before, self.after,
                                          Opf_Parser), [])
        self.edit("OEBPS/Text/ch1.xhtml", "Caf", "Kaf")
        self.edit("OEBPS/content.opf", "<dc:date></dc:date>", "")
        problems = writeback.verify(bk, self.before, self.after, Opf_Parser)
        self.assertEqual(len(problems), 2, problems)


class RunTests(unittest.TestCase):
    """`run` with the repair and the windows replaced."""

    def setUp(self):
        self._orig = (plugin._ensure_binary, plugin._too_old, plugin._repair,
                      ui.available, ui.show_result, ui.ask_fixes,
                      release_dialog.available)
        plugin._ensure_binary = lambda bk, allowed: ("/bin/epubsana", None)
        plugin._too_old = lambda path: None
        release_dialog.available = lambda: False
        self.shown = []
        ui.show_result = lambda *a: self.shown.append(a)
        ui.available = lambda: True
        self.choose = None

        def fake_repair(bk, binary, choose):
            offered = envelope([item(1, "fix.a", "auto_safe"),
                                item(2, "fix.b", "confirm_needed")]).fixes
            self.choose = choose(offered, [], {"errors": 2, "fatals": 0})
            if self.choose is None:
                return plugin.Outcome(True, "Cancelled.", "Nothing was changed.")
            return plugin.Outcome(True, "Applied.", "ok")
        plugin._repair = fake_repair

    def tearDown(self):
        (plugin._ensure_binary, plugin._too_old, plugin._repair,
         ui.available, ui.show_result, ui.ask_fixes,
         release_dialog.available) = self._orig

    def quietly(self, bk):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = plugin.run(bk)
        return code, out.getvalue()

    def test_an_automate_list_applies_the_safe_fixes_unasked(self):
        ui.ask_fixes = lambda *a: self.fail("asked in an Automate list")
        code, out = self.quietly(RecordingBk(automate=True))
        self.assertEqual(code, 0)
        self.assertEqual(self.choose, [1])
        self.assertEqual(self.shown, [])
        self.assertIn("epubsana:", out)

    def test_without_qt_it_behaves_as_in_an_automate_list(self):
        ui.available = lambda: False
        ui.ask_fixes = lambda *a: self.fail("asked without Qt")
        self.quietly(RecordingBk())
        self.assertEqual(self.choose, [1])

    def test_the_window_decides_otherwise(self):
        ui.ask_fixes = lambda offered, unavailable, counts: [2]
        code, _out = self.quietly(RecordingBk())
        self.assertEqual(code, 0)
        self.assertEqual(self.choose, [2])
        self.assertEqual(len(self.shown), 1)

    def test_cancel_is_not_a_failure(self):
        ui.ask_fixes = lambda *a: None
        code, _out = self.quietly(RecordingBk())
        self.assertEqual(code, 0)

    def test_a_failed_repair_returns_non_zero_so_sigil_takes_nothing(self):
        plugin._repair = lambda bk, b, c: plugin._failed("verify said no")
        code, out = self.quietly(RecordingBk(automate=True))
        self.assertNotEqual(code, 0)
        self.assertIn("Nothing was changed.", out)

    def test_a_replaced_binary_stops_everything(self):
        plugin._ensure_binary = lambda bk, a: (None, "has changed since it "
                                                     "was verified")
        code, out = self.quietly(RecordingBk(automate=True))
        self.assertNotEqual(code, 0)
        self.assertIn("has changed", out)


class RealPlanTests(unittest.TestCase):
    """epubsana itself, on the test book: the plan this plugin relies on."""

    def setUp(self):
        if _binary() is None:
            self.skipTest("no epubsana binary; set EPUBSANA_BINARY")
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_the_plan_has_indices_tiers_and_files(self):
        folder, epub = plugin._book_to_epub(RecordingBk(), self.tmp, "b")
        planned = runner.plan(_binary(), epub)
        offered, _unavailable = plugin.split_plan(planned)
        self.assertTrue(offered)
        ids = [f.fix_id for f in offered]
        self.assertIn("fix.html_entities", ids)
        safe = [f for f in offered if f.auto_safe]
        self.assertEqual([f.fix_id for f in safe], ["fix.html_entities"])
        for fix in offered:
            self.assertIsInstance(fix.index, int)
            self.assertTrue(fix.paths)

    def test_the_minimum_version_is_met(self):
        self.assertIsNone(plugin._too_old(_binary()))


class ReleaseNoticeTests(unittest.TestCase):
    def test_the_link_is_this_plugins_release_page(self):
        self.assertEqual(
            plugin_release.release_page("0.2.0"),
            "https://github.com/veripublica/sigil-plugins/releases/tag/"
            "epubsana-v0.2.0")

    def test_latest_json_entry_when_released(self):
        """`latest.json` gains this plugin's entry in its release commit;
        until then the entry may be absent, never wrong."""
        with open(os.path.join(ROOT, "latest.json"), encoding="utf-8") as h:
            found = plugin_release.read_latest(h.read())
        self.assertIn(found, (None, plugin._plugin_version()))

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
            "epubsana_build", os.path.join(PLUGIN_DIR, "build.py"))
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        tmp = tempfile.mkdtemp()
        real = build.DIST
        build.DIST = tmp
        try:
            path = build.build()
            name = os.path.basename(path)
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
        finally:
            build.DIST = real
            shutil.rmtree(tmp)
        self.assertEqual(name, "epubsana_sigil_v%s.zip"
                         % plugin._plugin_version())
        self.assertTrue(all(n.startswith("epubsana/") for n in names), names)
        for wanted in ("epubsana/plugin.xml", "epubsana/plugin.py",
                       "epubsana/LICENSE", "epubsana/client/writeback.py",
                       "epubsana/client/ui.py"):
            self.assertIn(wanted, names)
        for n in names:
            self.assertNotIn("/tests/", n)
            self.assertNotIn("__pycache__", n)
            self.assertNotIn(n, ("epubsana/epubsana", "epubsana/epubsana.exe",
                                 "epubsana/build.py", "epubsana/icon.py"))

    def test_plugin_xml_says_edit(self):
        with open(os.path.join(PLUGIN_DIR, "plugin.xml"),
                  encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("<type>edit</type>", text)
        self.assertIn("<name>epubsana</name>", text)


class IconTests(unittest.TestCase):
    def _icon(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "epubsana_sigil_icon", os.path.join(PLUGIN_DIR, "icon.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_shipped_svg_and_png_are_what_icon_py_writes(self):
        icon = self._icon()
        with open(os.path.join(PLUGIN_DIR, "plugin.svg"),
                  encoding="utf-8") as handle:
            self.assertEqual(handle.read(), icon.SVG)
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            icon.write_png(path, 128)
            with open(path, "rb") as a, open(
                    os.path.join(PLUGIN_DIR, "plugin.png"), "rb") as b:
                self.assertEqual(a.read(), b.read())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
