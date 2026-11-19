# epubsana for Sigil — the "a newer plugin is out" window
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Ask the user, in a window of its own, what to do about a newer release.

The only Qt code in the plugin, kept in one file so that everything else runs
without it. Sigil's bundled Python on macOS and Windows carries PySide6; a
Linux Sigil runs the system Python, which may have PySide6, PyQt5 or neither.
With neither, `available()` is False and the plugin falls back to the summary
line, which is how it said it before this window existed.

**The window opens after the plugin has exited, from a process of its own.**
While a plugin runs, Sigil shows its Plugin Runner window, and Sigil shows the
results only once the plugin's process has ended. A window opened by the
plugin itself therefore sat behind the runner window and held up the results
(Baris, 2026-11-19). So `launch` starts this file as a detached process and
returns at once. The plugin exits, Sigil shows its results, and only then does
this process open the window and bring it to the front.

That process outlives the plugin, so it cannot hand an answer back. It records
"Ignore this version" itself, in the plugin's settings file, the way Sigil
writes that file.
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
import webbrowser

DOWNLOAD = "download"
IGNORE = "ignore"
LATER = "later"

#: The key the plugin reads; kept in step with `plugin._IGNORED_PLUGIN_KEY`
#: by a test.
IGNORED_KEY = "ignored_plugin_version"

#: How long to wait for the plugin's process to end before opening anyway.
_WAIT_LIMIT = 30.0

#: After the plugin has exited, Sigil still has to read its results and close
#: the runner window. A short pause lets the window open after that.
_SETTLE = 0.7

_BINDINGS = ("PySide6", "PyQt5")


def available():
    """Can a window be shown here? Checked without importing Qt, which would
    cost the validation a noticeable fraction of a second."""
    for name in _BINDINGS:
        try:
            if importlib.util.find_spec(name) is not None:
                return True
        except (ImportError, ValueError):
            continue
    return False


def launch(latest, current, url, prefs_path):
    """Start the window in a detached process and return True, or False if it
    could not be started.

    The child's standard streams go nowhere. Sigil reads the plugin's output
    through pipes, and a child holding them open would keep Sigil waiting for
    the plugin to finish.
    """
    if not sys.executable:
        return False
    args = [sys.executable, os.path.abspath(__file__),
            str(os.getpid()), latest, current or "", url, prefs_path or ""]
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)
    return True


def _alive(pid):
    if os.name == "nt":
        import ctypes
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return False
        try:
            # WAIT_TIMEOUT (0x102) means it is still running.
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x102
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_exit(pid):
    deadline = time.monotonic() + _WAIT_LIMIT
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    time.sleep(_SETTLE)


def _bring_to_front():
    """On macOS a new process does not become the active application, so its
    window opens behind Sigil's. Ask AppKit to activate it. Elsewhere the
    always-on-top flag is enough."""
    if sys.platform != "darwin":
        return
    try:
        import ctypes
        objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.dylib")
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.restype = ctypes.c_void_p
        send = objc.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        app = send(objc.objc_getClass(b"NSApplication"),
                   objc.sel_registerName(b"sharedApplication"))
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        send(app, objc.sel_registerName(b"activateIgnoringOtherApps:"), True)
    except Exception:                                  # noqa: BLE001
        pass


def _qt():
    """`(QtCore, QtGui, QtWidgets)` from whichever binding is installed, or
    None."""
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        return QtCore, QtGui, QtWidgets
    except ImportError:
        pass
    try:
        from PyQt5 import QtCore, QtGui, QtWidgets
        return QtCore, QtGui, QtWidgets
    except ImportError:
        return None


def _enum(owner, scope, name):
    """`QMessageBox.ButtonRole.AcceptRole` in PySide6 and PyQt6,
    `QMessageBox.AcceptRole` in PyQt5."""
    scoped = getattr(owner, scope, None)
    if scoped is not None and hasattr(scoped, name):
        return getattr(scoped, name)
    return getattr(owner, name)


def ask(latest, current, url):
    """Show the window and return DOWNLOAD, IGNORE or LATER.

    None when no Qt binding is available, so that nothing was asked.
    DOWNLOAD has already opened `url` in the browser by the time it returns.
    `latest` and `current` are plain X.Y.Z strings and `url` is built by the
    plugin, never taken from the network, so none of them needs escaping.
    """
    qt = _qt()
    if qt is None:
        return None
    QtCore, QtGui, QtWidgets = qt
    box_cls = QtWidgets.QMessageBox

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv[:1] or ["epubsana"])
    _bring_to_front()

    box = box_cls()
    box.setWindowTitle("epubsana for Sigil")
    box.setIcon(_enum(box_cls, "Icon", "Information"))
    box.setText("epubsana for Sigil %s is available." % latest)
    box.setInformativeText(
        "You have %s. The new version is on its release page:\n%s\n\n"
        "Download it and add the zip in Sigil with Plugins, Manage Plugins, "
        "Add Plugin." % (current or "an older version", url))
    download = box.addButton("Download",
                             _enum(box_cls, "ButtonRole", "AcceptRole"))
    ignore = box.addButton("Ignore this version",
                           _enum(box_cls, "ButtonRole", "DestructiveRole"))
    later = box.addButton("Not now",
                          _enum(box_cls, "ButtonRole", "RejectRole"))
    box.setDefaultButton(download)
    box.setEscapeButton(later)
    box.setWindowFlags(box.windowFlags()
                       | _enum(QtCore.Qt, "WindowType", "WindowStaysOnTopHint"))
    box.raise_()
    box.activateWindow()
    # `exec` in PySide6 and PyQt6, `exec_` in PyQt5.
    run = getattr(box, "exec", None) or box.exec_
    run()

    clicked = box.clickedButton()
    if clicked is download:
        opened = QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
        if not opened:
            webbrowser.open(url)
        return DOWNLOAD
    if clicked is ignore:
        return IGNORE
    return LATER


def record_ignore(prefs_path, latest):
    """Write "ignore this release" into the plugin's settings file.

    Read fresh and replaced in one step, in Sigil's own format (`indent=2`,
    `ensure_ascii=False`), so the file stays the one a user edits by hand.
    A missing or unreadable file is left alone: the window then simply comes
    back tomorrow.
    """
    if not prefs_path or not os.path.isfile(prefs_path):
        return False
    try:
        with open(prefs_path, encoding="utf-8") as handle:
            prefs = json.load(handle)
    except (OSError, ValueError):
        return False
    if not isinstance(prefs, dict):
        return False
    prefs[IGNORED_KEY] = latest
    tmp = prefs_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(prefs, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, prefs_path)
    return True


def main(argv):
    """`release_dialog.py <plugin pid> <latest> <current> <url> <prefs path>`"""
    try:
        pid, latest, current, url, prefs_path = argv
        pid = int(pid)
    except ValueError:
        return 2
    _wait_for_exit(pid)
    if ask(latest, current, url) == IGNORE:
        record_ignore(prefs_path, latest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
