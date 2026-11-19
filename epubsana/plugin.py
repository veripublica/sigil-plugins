#!/usr/bin/env python3
# epubsana for Sigil — repair the open book with epubsana
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
#
# Sigil's plugin interface (`launcher.py`, `bookcontainer.py`, `opf_parser.py`)
# is BSD-licensed by Kevin B. Hendricks, Doug Massay and John Schember. This
# plugin uses Sigil's own `Opf_Parser` at run time, from Sigil's install, so
# that the OPF is read exactly as Sigil reads it; nothing of Sigil's is copied
# here. The GPL-3 above is a choice rather than an obligation.
"""An **edit** plugin: epubsana repairs the book Sigil holds, and the repair
is written back into Sigil, or nothing is.

The flow, each step proven through Sigil's own launcher first:

1. Make sure a verified epubsana binary is there (download, checksum, hourly
   update check), as in the family's other Sigil plugins.
2. Write the book Sigil holds, unsaved edits included, to a temporary
   `.epub`, and ask epubsana for its plan (`--dry-run`). Fixes Sigil cannot
   take are listed but not offered (`NOT_IN_SIGIL`).
3. The user chooses (`auto_safe` ticked, `confirm_needed` not). In an
   Automate list, or without Qt, the `auto_safe` fixes are applied unasked.
4. epubsana applies exactly those (`--apply`), re-validates, and reverts a fix
   that made any finding more frequent.
5. `client/writeback.py` maps every difference to a call on Sigil's container,
   or refuses the whole repair before making one.
6. The book is read back out of Sigil and compared with epubsana's output,
   file by file and the OPF as Sigil models it, and epubsana counts its
   findings once more. Any difference makes the plugin return a failure, and
   Sigil then takes none of this run's changes.

The repaired book stays in Sigil, unsaved: the user saves it, or does not.
"""

import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client import binary as bin_mod          # noqa: E402
from client import plugin_release             # noqa: E402
from client import release_dialog             # noqa: E402
from client import runner                     # noqa: E402
from client import ui                         # noqa: E402
from client import writeback                  # noqa: E402
from client.envelope import EnvelopeError     # noqa: E402

#: The oldest epubsana whose plan indices, `--apply` and JSON items this
#: plugin was built and tested against.
MIN_REPAIRER_VERSION = (0, 42, 0)

#: Fixes that are never offered in Sigil, and why. The reasons are shown in
#: the plan window. `writeback.plan` would refuse them anyway; leaving them
#: out of the choice is kinder than refusing a repair the user asked for.
NOT_IN_SIGIL = {
    "fix.package_version":
        "Sigil does not let a plugin change the EPUB version",
    "fix.html_media_type":
        "Sigil has no way for a plugin to change a media-type",
    "fix.image_media_type":
        "Sigil has no way for a plugin to change a media-type",
    "fix.non_preferred_media_type":
        "Sigil has no way for a plugin to change a media-type",
    "fix.manifest_href_spaces":
        "Sigil writes the manifest's file names itself",
    "fix.mimetype_packaging":
        "Sigil writes the container itself when it saves",
    "fix.empty_directory":
        "Sigil writes the container itself when it saves",
}

_UPDATE_INTERVAL = timedelta(hours=1)
_STALE_AFTER = timedelta(days=30)
_CHECK_TIMEOUT = 5

_UPDATE_KEY = "autoupdate"
_ON_VALUES = frozenset(["yes", "true", "on", "1", "y"])

_LATEST_PLUGIN_KEY = "latest_plugin_version"
_IGNORED_PLUGIN_KEY = "ignored_plugin_version"
_NOTICE_SHOWN_KEY = "plugin_notice_shown"
_NOTICE_INTERVAL = timedelta(days=1)

_NAME = "epubsana"


# --------------------------------------------------------------------------
# Small helpers


def _plugin_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _plugin_version():
    import re
    try:
        with open(os.path.join(_plugin_dir(), "plugin.xml"),
                  encoding="utf-8") as handle:
            found = re.search(r"<version>([^<]+)</version>", handle.read())
    except Exception:                                  # noqa: BLE001
        return None
    return found.group(1).strip() if found else None


def _binary_path():
    return os.path.join(_plugin_dir(), bin_mod.binary_filename())


def _opf_parser():
    """Sigil's `Opf_Parser`, from the launcher's own folder on `sys.path`."""
    from opf_parser import Opf_Parser
    return Opf_Parser


def _now():
    return datetime.now(timezone.utc)


def _since(stamp):
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return _now() - when


def _in_automation(bk):
    try:
        return bool(bk.using_automate())
    except Exception:                                  # noqa: BLE001
        return False


def _updates_allowed(bk, prefs):
    """`autoupdate`, written with its default on the first run. Only a clear
    yes means yes: the switch governs someone's connection."""
    value = prefs.get(_UPDATE_KEY)
    if value is None:
        prefs[_UPDATE_KEY] = True
        bk.savePrefs(prefs)
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _ON_VALUES


# --------------------------------------------------------------------------
# The binary (as in the family's other Sigil plugins)


def _stale_note(prefs, allowed=True):
    age = _since(prefs.get("last_update_success"))
    if age is None or age < _STALE_AFTER:
        return None
    if not allowed:
        return "this epubsana is %d days old; update checks are off" % age.days
    return ("this epubsana is %d days old and could not be checked for "
            "updates" % age.days)


def _integrity_failure(path, prefs):
    stored = prefs.get("binary_sha256")
    actual = bin_mod.sha256_of(path)
    if not stored:
        prefs["binary_sha256"] = actual
        return None
    if actual == stored:
        return None
    return ("the epubsana binary has changed since it was verified "
            "(expected %s, found %s). It was not run. Delete it from the "
            "plugin folder and run the plugin again to reinstall a verified "
            "copy." % (stored[:16], actual[:16]))


def _install_failure(exc):
    if isinstance(exc, bin_mod.DownloadError):
        return "epubsana could not be installed: %s" % exc
    return ("epubsana could not be downloaded. The first run needs an "
            "internet connection; after that the plugin works offline. (%s)"
            % exc)


def _update_note(before, after):
    old = bin_mod.parse_version(before)
    new = bin_mod.parse_version(after)
    fmt = lambda v: ".".join(str(n) for n in v) if v else None  # noqa: E731
    if old and new and old != new:
        return "updated epubsana %s to %s" % (fmt(old), fmt(new))
    if new:
        return "reinstalled epubsana %s" % fmt(new)
    return "updated epubsana"


def _check_plugin_release(bk, prefs):
    try:
        latest = plugin_release.latest_version(timeout=_CHECK_TIMEOUT)
    except Exception:                                  # noqa: BLE001
        return
    if latest:
        prefs[_LATEST_PLUGIN_KEY] = latest
        bk.savePrefs(prefs)


def _ensure_binary(bk, allowed):
    path = _binary_path()
    prefs = bk.getPrefs()

    def remember(archive_sha, binary_sha):
        prefs["installed_sha256"] = archive_sha
        prefs["binary_sha256"] = binary_sha
        prefs["last_update_check"] = _now().isoformat()
        prefs["last_update_success"] = prefs["last_update_check"]
        bk.savePrefs(prefs)

    if not os.path.isfile(path):
        installed, archive_sha, binary_sha = bin_mod.download_binary(
            _plugin_dir())
        remember(archive_sha, binary_sha)
        return installed, "installed epubsana"

    tampered = _integrity_failure(path, prefs)
    if tampered:
        return None, tampered
    if not allowed:
        return path, _stale_note(prefs, allowed=False)

    age = _since(prefs.get("last_update_check"))
    if age is not None and age < _UPDATE_INTERVAL:
        return path, None

    prefs["last_update_check"] = _now().isoformat()
    bk.savePrefs(prefs)
    try:
        sums = bin_mod.latest_checksums(timeout=_CHECK_TIMEOUT)
        wanted = sums.get(bin_mod.asset_name())
        prefs["last_update_success"] = prefs["last_update_check"]
        bk.savePrefs(prefs)
        _check_plugin_release(bk, prefs)
        if wanted and wanted != prefs.get("installed_sha256"):
            before = runner.binary_version(path) or ""
            _p, archive_sha, binary_sha = bin_mod.download_binary(
                _plugin_dir(), expected=wanted)
            remember(archive_sha, binary_sha)
            after = runner.binary_version(path) or ""
            return path, _update_note(before, after)
    except Exception:                                  # noqa: BLE001
        pass
    return path, _stale_note(prefs)


def _too_old(path):
    found = bin_mod.parse_version(runner.binary_version(path) or "")
    if found is None or found >= MIN_REPAIRER_VERSION:
        return None
    fmt = lambda v: ".".join(str(n) for n in v)  # noqa: E731
    return ("this plugin needs epubsana %s or newer, and %s is %s. Delete it "
            "from the plugin folder to fetch the current release."
            % (fmt(MIN_REPAIRER_VERSION), path, fmt(found)))


# --------------------------------------------------------------------------
# The newer-release notice (as in the family's other Sigil plugins)


def _plugin_release_note(prefs):
    latest = prefs.get(_LATEST_PLUGIN_KEY)
    if not plugin_release.is_newer(latest, _plugin_version()):
        return None
    if prefs.get(_IGNORED_PLUGIN_KEY) == latest:
        return None
    return "epubsana for Sigil %s is available: %s" % (
        latest, plugin_release.release_page(latest))


def _offer_plugin_release(bk):
    prefs = bk.getPrefs()
    if _plugin_release_note(prefs) is None or _in_automation(bk):
        return
    age = _since(prefs.get(_NOTICE_SHOWN_KEY))
    if age is not None and age < _NOTICE_INTERVAL:
        return
    latest = prefs[_LATEST_PLUGIN_KEY]
    try:
        if not release_dialog.available():
            return
        started = release_dialog.launch(
            latest, _plugin_version(), plugin_release.release_page(latest),
            getattr(prefs, "file_path", None))
    except Exception:                                  # noqa: BLE001
        return
    if started:
        prefs[_NOTICE_SHOWN_KEY] = _now().isoformat()
        bk.savePrefs(prefs)


# --------------------------------------------------------------------------
# The repair


def _zip_dir(src, epub_path):
    """`src` as an `.epub`: `mimetype` first and stored, as OCF requires."""
    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        mimetype = os.path.join(src, "mimetype")
        if os.path.isfile(mimetype):
            zf.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        else:
            zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                        compress_type=zipfile.ZIP_STORED)
        for root, _dirs, files in os.walk(src):
            for name in sorted(files):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, src).replace(os.sep, "/")
                if rel != "mimetype":
                    zf.write(full, rel)


def _book_to_epub(bk, workdir, name):
    """`(folder, epub path)` for the book as Sigil holds it now."""
    folder = os.path.join(workdir, name)
    os.makedirs(folder)
    bk.copy_book_contents_to(folder)
    epub_path = os.path.join(workdir, name + ".epub")
    _zip_dir(folder, epub_path)
    return folder, epub_path


def split_plan(envelope):
    """`(offered, unavailable)`: the proposals Sigil can take, and the others
    with the reason, both in epubsana's order."""
    offered, unavailable = [], []
    for fix in envelope.fixes:
        if fix.outcome != "proposed" or fix.index is None:
            continue
        reason = NOT_IN_SIGIL.get(fix.fix_id)
        if reason:
            unavailable.append((fix, reason))
        else:
            offered.append(fix)
    return offered, unavailable


def _counts_line(before, after):
    def pair(key, label):
        return "%s %d → %d" % (label, before.get(key, 0), after.get(key, 0))
    return "%s, %s, %s." % (pair("fatals", "fatal errors"),
                            pair("errors", "errors"),
                            pair("warnings", "warnings"))


class Outcome(object):
    """What one run did, for the window and for standard output."""

    def __init__(self, ok, title, text, details=()):
        self.ok = ok
        self.title = title
        self.text = text
        self.details = list(details)

    def line(self):
        out = "%s: %s %s" % (_NAME, self.title, self.text)
        if self.details:
            out += " " + "; ".join(self.details)
        return out


def _failed(text, details=()):
    return Outcome(False, "Nothing was changed.", text, details)


def _repair(bk, binary, choose):
    """Plan, choose, repair, write back, verify. `choose(offered,
    unavailable, counts)` returns the indices to apply, or None to cancel."""
    workdir = tempfile.mkdtemp(prefix="epubsana-sigil-")
    try:
        before_dir, epub_path = _book_to_epub(bk, workdir, "before")
        try:
            planned = runner.plan(binary, epub_path)
        except EnvelopeError as exc:
            return _failed("epubsana could not plan a repair: %s" % exc)
        if planned.could_not_read:
            return _failed("epubsana could not read the book: %s"
                           % (planned.error or "no reason given"))
        offered, unavailable = split_plan(planned)
        counts = planned.counts("before")
        if not offered:
            text = ("epubsana has no repair Sigil can take for this book "
                    "(%d error(s), %d fatal error(s))."
                    % (counts["errors"], counts["fatals"]))
            details = ["%s: %s" % (f.message, r) for f, r in unavailable]
            return Outcome(True, "Nothing to repair.", text, details)

        chosen = choose(offered, unavailable, counts)
        if chosen is None:
            return Outcome(True, "Cancelled.", "Nothing was changed.")
        if not chosen:
            return Outcome(True, "Nothing to repair.",
                           "No fix was chosen; nothing was changed.")

        fixed = os.path.join(workdir, "fixed.epub")
        try:
            repaired = runner.repair(binary, epub_path, fixed, chosen)
        except EnvelopeError as exc:
            return _failed("epubsana refused: %s" % exc)
        if repaired.could_not_read:
            return _failed("epubsana could not repair the book: %s"
                           % (repaired.error or "no reason given"))
        applied = repaired.outcome("applied")
        reverted = repaired.outcome("reverted")
        if not applied or not os.path.isfile(fixed):
            details = ["reverted: %s" % f.message for f in reverted]
            return Outcome(True, "Nothing was changed.",
                           "None of the chosen fixes could be applied "
                           "without making another finding more frequent, "
                           "so epubsana kept none.", details)

        after_dir = os.path.join(workdir, "after")
        with zipfile.ZipFile(fixed) as zf:
            zf.extractall(after_dir)
        parser = _opf_parser()
        try:
            ops = writeback.plan(bk, before_dir, after_dir, parser)
        except writeback.Unmappable as exc:
            return _failed("the repair cannot be carried into Sigil whole: "
                           "%s." % exc)
        try:
            writeback.apply(ops)
        except Exception as exc:                       # noqa: BLE001
            return _failed("Sigil refused a change (%s: %s); this run's "
                           "changes are discarded." % (type(exc).__name__, exc))

        back_dir, back_epub = _book_to_epub(bk, workdir, "readback")
        problems = writeback.verify(bk, back_dir, after_dir, parser)
        if not problems:
            try:
                rechecked = runner.plan(binary, back_epub).counts("before")
            except EnvelopeError as exc:
                rechecked = None
                problems = ["the re-check could not run: %s" % exc]
            if rechecked is not None and rechecked != repaired.counts("after"):
                problems.append(
                    "the book Sigil now holds has %s, not %s"
                    % (rechecked, repaired.counts("after")))
        if problems:
            return _failed("Sigil's copy did not come out as epubsana wrote "
                           "it, so this run's changes are discarded.",
                           problems)

        title = ("Applied %d fix(es). Save the book in Sigil to keep them."
                 % len(applied))
        text = _counts_line(repaired.counts("before"),
                            repaired.counts("after"))
        text += " epubsana %s (plugin %s)." % (repaired.version,
                                              _plugin_version() or "?")
        details = ["applied: %s" % f.message for f in applied]
        details += ["reverted (it made another finding more frequent): %s"
                    % f.message for f in reverted]
        details += ["files changed: %s" % ", ".join(
            sorted(op.what for op in ops))]
        return Outcome(True, title, text, details)
    except Exception as exc:                           # noqa: BLE001
        return _failed("%s: %s" % (type(exc).__name__, exc))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _fail(message):
    print("%s: %s" % (_NAME, message))
    return -1


def run(bk):
    automate = _in_automation(bk)
    windows = not automate and ui.available()
    allowed = _updates_allowed(bk, bk.getPrefs())

    try:
        binary, note = _ensure_binary(bk, allowed)
    except Exception as exc:                           # noqa: BLE001
        message = _install_failure(exc)
        if windows:
            ui.show_result("Nothing was changed.", message, (), False)
        return _fail(message)
    if binary is None or _too_old(binary):
        message = note if binary is None else _too_old(binary)
        if windows:
            ui.show_result("Nothing was changed.", message, (), False)
        return _fail(message)

    if windows:
        choose = ui.ask_fixes
    else:
        def choose(offered, _unavailable, _counts):
            # An Automate list, or no Qt: the safe fixes, unasked.
            return [f.index for f in offered if f.auto_safe]

    outcome = _repair(bk, binary, choose)
    if note:
        outcome.text += " (%s)" % note
    print(outcome.line())
    if windows:
        ui.show_result(outcome.title, outcome.text, outcome.details,
                       outcome.ok)
    _offer_plugin_release(bk)
    return 0 if outcome.ok else -1


def main():
    print("This is a Sigil plugin; run it from Sigil's Plugins menu.")
    return -1


if __name__ == "__main__":
    sys.exit(main())
