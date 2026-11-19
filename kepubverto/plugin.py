#!/usr/bin/env python3
# kepubverto for Sigil — convert the open book to a KEPUB with kepubverto
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
#
# Sigil's plugin interface (`launcher.py`, `outputcontainer.py`) is
# BSD-licensed by Kevin B. Hendricks, Doug Massay and John Schember, and this
# plugin imports none of it: `bk` arrives as an argument. The GPL-3 above is a
# choice rather than an obligation.
"""An **output** plugin: it reads the book Sigil holds and writes a
`.kepub.epub` somewhere else. The book in Sigil is never changed, and its file
on disk is never overwritten.

Why output and not edit: kepubverto adds a span around every run of text. An
edit plugin would put that markup into the book being edited, and from then
on the user would be editing the KEPUB rather than the book. kepubverto has
no in-place mode for the same reason.

The flow:

1. Make sure a verified kepubverto binary is there (download, checksum,
   hourly update check). The same code as epubveri for Sigil's.
2. Ask where to save and how to hyphenate, in one window. In an Automate list
   there is no window: the KEPUB is written beside the book, and an existing
   file is never replaced.
3. Write the book Sigil holds, unsaved edits included, to a temporary `.epub`,
   and run kepubverto on it into the same temporary folder. Only a finished
   KEPUB is moved to where the user asked, so a failed run leaves nothing
   behind.
4. Say what happened, in a window (or on standard output in an Automate
   list), and offer a newer release of this plugin if there is one.
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
from client.envelope import EnvelopeError     # noqa: E402

#: The oldest kepubverto whose `--format json` report this plugin reads, the
#: same floor as kepubverto for calibre. Releases are always newer; this
#: catches a binary someone put in the plugin folder by hand.
MIN_CONVERTER_VERSION = (0, 3, 0)

#: Hourly, with a short timeout, and never allowed to stop a conversion. The
#: reasoning is epubveri for Sigil's and is written there in full.
_UPDATE_INTERVAL = timedelta(hours=1)
_STALE_AFTER = timedelta(days=30)
_CHECK_TIMEOUT = 5

#: Settings, written with their defaults on the first run so the JSON file
#: (Sigil has no settings screen) shows which choices exist.
_UPDATE_KEY = "autoupdate"
_HYPHENS_KEY = "hyphens"
_CSS_KEY = "css"
_FOLDER_KEY = "last_folder"
_DEFAULTS = ((_UPDATE_KEY, True), (_HYPHENS_KEY, "book"), (_CSS_KEY, []))

#: Only these mean yes for `autoupdate`. Everything else means no: the switch
#: governs someone's connection, so a typo must stop the network rather than
#: use it.
_ON_VALUES = frozenset(["yes", "true", "on", "1", "y"])

_HYPHEN_VALUES = tuple(v for v, _label in ui.HYPHENS)

#: The newer-release notice, as in epubveri for Sigil.
_LATEST_PLUGIN_KEY = "latest_plugin_version"
_IGNORED_PLUGIN_KEY = "ignored_plugin_version"
_NOTICE_SHOWN_KEY = "plugin_notice_shown"
_NOTICE_INTERVAL = timedelta(days=1)

#: What every message is signed with, so a line in an Automate log can be
#: traced to this plugin.
_NAME = "kepubverto"


# --------------------------------------------------------------------------
# Small helpers


def _plugin_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _plugin_version():
    """The version from `plugin.xml`, or None. Read at run time so it lives
    in one place."""
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
    """Is this run part of one of Sigil's Automate lists? Sigils older than
    the feature have no `using_automate`, and no lists."""
    try:
        return bool(bk.using_automate())
    except Exception:                                  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# Settings


def _settings(bk, prefs):
    """`{"autoupdate": bool, "hyphens": str|None, "css": [str]}`.

    Missing keys are written with their defaults. An unknown hyphenation word
    means "as the book says", which adds nothing to the book. `css` takes a
    list of strings or one string.
    """
    missing = False
    for key, default in _DEFAULTS:
        if prefs.get(key) is None:
            prefs[key] = default
            missing = True
    if missing:
        bk.savePrefs(prefs)

    update = prefs.get(_UPDATE_KEY)
    if not isinstance(update, bool):
        update = str(update).strip().lower() in _ON_VALUES

    hyphens = str(prefs.get(_HYPHENS_KEY) or "book").strip().lower()
    if hyphens not in _HYPHEN_VALUES:
        hyphens = "book"

    css = prefs.get(_CSS_KEY) or []
    if isinstance(css, str):
        css = [css]
    css = [c for c in css if isinstance(c, str) and c.strip()]
    return dict(autoupdate=update, hyphens=hyphens, css=css)


# --------------------------------------------------------------------------
# The binary


def _stale_note(prefs, allowed=True):
    age = _since(prefs.get("last_update_success"))
    if age is None or age < _STALE_AFTER:
        return None
    if not allowed:
        return "this kepubverto is %d days old; update checks are off" % age.days
    return ("this kepubverto is %d days old and could not be checked for "
            "updates" % age.days)


def _integrity_failure(path, prefs):
    """A sentence when the binary on disk is not the one that was verified,
    otherwise None. A missing stored hash is trusted once and recorded."""
    stored = prefs.get("binary_sha256")
    actual = bin_mod.sha256_of(path)
    if not stored:
        prefs["binary_sha256"] = actual
        return None
    if actual == stored:
        return None
    return ("the kepubverto binary has changed since it was verified "
            "(expected %s, found %s). It was not run. Delete it from the "
            "plugin folder and convert again to reinstall a verified copy."
            % (stored[:16], actual[:16]))


def _install_failure(exc):
    if isinstance(exc, bin_mod.DownloadError):
        return "kepubverto could not be installed: %s" % exc
    return ("kepubverto could not be downloaded. The first run needs an "
            "internet connection; after that the plugin works offline. (%s)"
            % exc)


def _update_note(before, after):
    old = bin_mod.parse_version(before)
    new = bin_mod.parse_version(after)
    fmt = lambda v: ".".join(str(n) for n in v) if v else None  # noqa: E731
    if old and new and old != new:
        return "updated kepubverto %s to %s" % (fmt(old), fmt(new))
    if new:
        return "reinstalled kepubverto %s" % fmt(new)
    return "updated kepubverto"


def _check_plugin_release(bk, prefs):
    """Record the newest released version of this plugin. Never raises; a
    failure keeps what was stored."""
    try:
        latest = plugin_release.latest_version(timeout=_CHECK_TIMEOUT)
    except Exception:                                  # noqa: BLE001
        return
    if latest:
        prefs[_LATEST_PLUGIN_KEY] = latest
        bk.savePrefs(prefs)


def _ensure_binary(bk, allowed):
    """`(path, note)`: the binary to run, installing or updating it.

    `path` is None when the binary on disk failed its integrity check; `note`
    then says why. Nothing about updating may stop a conversion.
    """
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
        return installed, "installed kepubverto"

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
        # Only once kepubverto's own check has answered, so an offline
        # machine makes one failed request an hour rather than two.
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
    """A sentence when the binary predates the report this plugin reads."""
    found = bin_mod.parse_version(runner.binary_version(path) or "")
    if found is None or found >= MIN_CONVERTER_VERSION:
        return None
    fmt = lambda v: ".".join(str(n) for n in v)  # noqa: E731
    return ("this plugin needs kepubverto %s or newer, and %s is %s. Delete "
            "it from the plugin folder to fetch the current release."
            % (fmt(MIN_CONVERTER_VERSION), path, fmt(found)))


# --------------------------------------------------------------------------
# The newer-release notice (as in epubveri for Sigil)


def _plugin_release_note(prefs):
    latest = prefs.get(_LATEST_PLUGIN_KEY)
    if not plugin_release.is_newer(latest, _plugin_version()):
        return None
    if prefs.get(_IGNORED_PLUGIN_KEY) == latest:
        return None
    return "kepubverto for Sigil %s is available: %s" % (
        latest, plugin_release.release_page(latest))


def _offer_plugin_release(bk):
    """Start the newer-release window, at most once a day, never in an
    Automate list. It opens from its own process once this one has exited
    (`client/release_dialog.py`). Never raises."""
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
# Where the KEPUB goes


def _book_path(bk):
    """The open book's file, or None for a book that was never saved."""
    try:
        path = bk.get_epub_filepath()
    except Exception:                                  # noqa: BLE001
        return None
    return os.path.abspath(path) if path else None


def kepub_name(book_path):
    """`Book.epub` -> `Book.kepub.epub`. A book already named `.kepub.epub`
    keeps its stem, so the default would be the book itself; the caller
    refuses that."""
    base = os.path.basename(book_path) if book_path else "book.epub"
    stem = base
    for ext in (".kepub.epub", ".epub"):
        if stem.lower().endswith(ext):
            stem = stem[:-len(ext)]
            break
    return (stem or "book") + ".kepub.epub"


def _same_file(a, b):
    if not a or not b:
        return False
    if os.path.exists(a) and os.path.exists(b):
        try:
            return os.path.samefile(a, b)
        except OSError:
            pass
    return os.path.normcase(os.path.abspath(a)) == \
        os.path.normcase(os.path.abspath(b))


def _default_target(bk, prefs):
    """The remembered folder, else the book's, else the home folder; with the
    book's name."""
    book = _book_path(bk)
    folder = prefs.get(_FOLDER_KEY)
    if not (folder and os.path.isdir(folder)):
        folder = os.path.dirname(book) if book else os.path.expanduser("~")
    return os.path.join(folder, kepub_name(book))


# --------------------------------------------------------------------------
# Converting


def _build_epub(bk, destdir):
    """Write the book Sigil holds, unsaved edits included, to a real `.epub`.

    `copy_book_contents_to` gives the whole container, `mimetype` and
    `META-INF/` included. `mimetype` goes first and stored, as OCF requires.
    The same code as epubveri for Sigil's, where the OPF question is written
    up in full.
    """
    workdir = os.path.join(destdir, "book")
    os.makedirs(workdir)
    bk.copy_book_contents_to(workdir)
    epub_path = os.path.join(destdir, "current.epub")
    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        mimetype = os.path.join(workdir, "mimetype")
        if os.path.isfile(mimetype):
            zf.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        else:
            zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                        compress_type=zipfile.ZIP_STORED)
        for root, _dirs, files in os.walk(workdir):
            for name in sorted(files):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, workdir).replace(os.sep, "/")
                if rel == "mimetype":
                    continue
                zf.write(full, rel)
    return epub_path


class Outcome(object):
    """What one conversion did, in the words the windows and the log use."""

    def __init__(self, ok, title, text, details=(), path=None):
        self.ok = ok
        self.title = title
        self.text = text
        self.details = list(details)
        self.path = path

    def line(self):
        """One line for standard output (the Plugin Runner, an Automate log)."""
        out = "%s: %s %s" % (_NAME, self.title, self.text)
        if self.details:
            out += " " + "; ".join(self.details)
        return out


def _describe(envelope, target, hyphens, css):
    """Turn kepubverto's report into an `Outcome`."""
    version = "kepubverto %s (plugin %s)" % (envelope.version,
                                             _plugin_version() or "?")
    if envelope.could_not_convert:
        return Outcome(False, "The book was not converted.",
                       "kepubverto could not read or write it: %s. %s"
                       % (envelope.error or "no reason given", version))
    done = envelope.count("converted")
    total = envelope.count("documents")
    left = envelope.findings
    name = os.path.basename(target)
    if envelope.already_kepub:
        text = ("The book already carries Kobo's markup, so nothing was "
                "added; %s is a copy of it." % name)
    else:
        text = ("%d of %d document(s) converted, %d span(s) added. Saved as %s."
                % (done, total, envelope.count("spans"), name))
    options = []
    if hyphens != "book":
        options.append("hyphenation %s" % dict(ui.HYPHENS)[hyphens].lower())
    if css:
        options.append("your CSS")
    if options:
        text += " With %s." % " and ".join(options)
    text += " %s." % version
    details = []
    title = "Converted."
    if left:
        title = "Converted, but %d document(s) were left as they were." \
            % len(left)
        details = ["%s: %s (%s)" % (f.location or "(book)", f.message, f.code)
                   for f in left]
    return Outcome(True, title, text, details, target)


def _convert(bk, binary, target, hyphens, css):
    """Convert into a temporary folder and move the result to `target`.

    `target` may exist only when the user agreed to replace it; in an Automate
    list the caller has already refused that.
    """
    tmpdir = tempfile.mkdtemp(prefix="kepubverto-sigil-")
    try:
        epub_path = _build_epub(bk, tmpdir)
        out = os.path.join(tmpdir, "out.kepub.epub")
        try:
            envelope = runner.run_kepubverto(
                binary, epub_path, out,
                hyphens=None if hyphens == "book" else hyphens, css=css)
        except EnvelopeError as exc:
            # A refusal: kepubverto's own sentence, e.g. about `--css`.
            return Outcome(False, "The book was not converted.",
                           "kepubverto refused: %s" % exc)
        outcome = _describe(envelope, target, hyphens, css)
        if outcome.ok:
            if not os.path.isfile(out):
                return Outcome(False, "The book was not converted.",
                               "kepubverto reported success but wrote no "
                               "file.")
            shutil.move(out, target)
        return outcome
    except Exception as exc:                           # noqa: BLE001
        return Outcome(False, "The book was not converted.",
                       "%s: %s" % (type(exc).__name__, exc))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _fail(message):
    """Print why nothing was written and return the code Sigil expects. A
    message printed is kept in the Plugin Runner's log on both paths."""
    print("%s: %s" % (_NAME, message))
    return -1


def run(bk):
    automate = _in_automation(bk)
    windows = not automate and ui.available()
    prefs = bk.getPrefs()
    settings = _settings(bk, prefs)

    try:
        binary, note = _ensure_binary(bk, settings["autoupdate"])
    except Exception as exc:                           # noqa: BLE001
        message = _install_failure(exc)
        if windows:
            ui.show_result("The book was not converted.", message, (), None)
        return _fail(message)
    if binary is None:
        if windows:
            ui.show_result("The book was not converted.", note, (), None)
        return _fail(note)
    old = _too_old(binary)
    if old:
        if windows:
            ui.show_result("The book was not converted.", old, (), None)
        return _fail(old)

    prefs = bk.getPrefs()
    book = _book_path(bk)
    hyphens = settings["hyphens"]
    if windows:
        chosen = ui.ask_options(_default_target(bk, prefs), hyphens,
                                lambda p: _same_file(p, book))
        if chosen is None:
            print("%s: cancelled; nothing was written." % _NAME)
            return 0
        target, hyphens = chosen
        prefs = bk.getPrefs()
        prefs[_FOLDER_KEY] = os.path.dirname(target)
        prefs[_HYPHENS_KEY] = hyphens
        bk.savePrefs(prefs)
    else:
        # An Automate list, or no Qt: beside the book, never replacing.
        if not book:
            return _fail("the book has never been saved, so there is no "
                         "folder to write the KEPUB beside. Save it first.")
        target = os.path.join(os.path.dirname(book), kepub_name(book))
        if _same_file(target, book):
            return _fail("the book is itself named .kepub.epub, so its "
                         "KEPUB would overwrite it. Nothing was written.")
        if os.path.exists(target):
            return _fail("%s already exists and was not replaced."
                         % target)

    outcome = _convert(bk, binary, target, hyphens, settings["css"])
    if note:
        outcome.text += " (%s)" % note
    print(outcome.line())
    if windows:
        ui.show_result(outcome.title, outcome.text, outcome.details,
                       os.path.dirname(target) if outcome.ok else None)
    _offer_plugin_release(bk)
    return 0 if outcome.ok else -1


def main():
    print("This is a Sigil plugin; run it from Sigil's Plugins menu.")
    return -1


if __name__ == "__main__":
    sys.exit(main())
