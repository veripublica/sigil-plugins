# kepubverto for Sigil — the options window and the result window
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""The two windows a conversion shows, and nothing else.

Qt is reached through `release_dialog`'s helpers, so the bindings it accepts
(PySide6, then PyQt5) and the way a window is brought in front of Sigil are
written once in this plugin. When no binding is importable, `available()` is
False and the plugin works without windows: it writes beside the book, as in
an Automate list, and prints what happened.

Both windows open while Sigil's Plugin Runner window is up, because a
conversion needs its answer before it starts. They are kept on top and the
process is activated on macOS, which is what failed for the newer-release
window when it ran inside the plugin (Baris, 2026-11-19).
"""

import os

from . import release_dialog as _rd

#: Hyphenation choices, in the order the window lists them. The first value
#: is not passed to kepubverto at all: the book decides.
HYPHENS = (
    ("book", "As the book says"),
    ("auto", "On"),
    ("none", "Off"),
)


def available():
    return _rd.available()


def _app(QtWidgets):
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(["kepubverto"])
    _rd._bring_to_front()
    return app


def _on_top(QtCore, window):
    window.setWindowFlags(window.windowFlags()
                          | _rd._enum(QtCore.Qt, "WindowType",
                                      "WindowStaysOnTopHint"))
    window.raise_()
    window.activateWindow()


def _exec(window):
    run = getattr(window, "exec", None) or window.exec_
    return run()


def ask_options(default_path, hyphens, same_as_book):
    """Ask where to save and how to hyphenate.

    Returns `(path, hyphens)`, or None when the user cancelled. `same_as_book`
    is a function that says whether a path is the book open in Sigil; that
    path is refused here, because the book must never be overwritten.
    """
    QtCore, QtGui, QtWidgets = _rd._qt()
    _app(QtWidgets)
    W = QtWidgets

    dialog = W.QDialog()
    dialog.setWindowTitle("kepubverto for Sigil")
    layout = W.QVBoxLayout(dialog)
    layout.addWidget(W.QLabel(
        "Convert the book open in Sigil to a KEPUB for Kobo. "
        "The book in Sigil is not changed."))

    form = W.QFormLayout()
    row = W.QHBoxLayout()
    path_edit = W.QLineEdit(default_path)
    path_edit.setMinimumWidth(420)
    browse = W.QPushButton("Browse…")
    row.addWidget(path_edit)
    row.addWidget(browse)
    form.addRow("Save as:", row)

    combo = W.QComboBox()
    for value, label in HYPHENS:
        combo.addItem(label, value)
    index = [v for v, _l in HYPHENS].index(hyphens) if hyphens in dict(
        HYPHENS) else 0
    combo.setCurrentIndex(index)
    form.addRow("Hyphenation:", combo)
    layout.addLayout(form)

    buttons = W.QDialogButtonBox()
    convert = buttons.addButton("Convert", _rd._enum(
        W.QDialogButtonBox, "ButtonRole", "AcceptRole"))
    buttons.addButton(_rd._enum(W.QDialogButtonBox, "StandardButton",
                                "Cancel"))
    convert.setDefault(True)
    layout.addWidget(buttons)

    def pick():
        start = path_edit.text().strip() or default_path
        chosen = W.QFileDialog.getSaveFileName(
            dialog, "Save the KEPUB as", start,
            "KEPUB (*.kepub.epub);;EPUB (*.epub)")
        # PySide6 and PyQt5 both return (path, filter).
        chosen = chosen[0] if isinstance(chosen, tuple) else chosen
        if chosen:
            if not chosen.lower().endswith(".epub"):
                chosen += ".kepub.epub"
            path_edit.setText(chosen)
            # The file dialog already asked about replacing it.
            path_edit.setProperty("confirmed", chosen)

    def accept():
        path = os.path.abspath(os.path.expanduser(path_edit.text().strip()))
        if not path_edit.text().strip():
            return
        if same_as_book(path):
            W.QMessageBox.warning(
                dialog, "kepubverto for Sigil",
                "That is the book open in Sigil. Choose another name: the "
                "book itself is never overwritten.")
            return
        if not os.path.isdir(os.path.dirname(path)):
            W.QMessageBox.warning(
                dialog, "kepubverto for Sigil",
                "The folder %s does not exist." % os.path.dirname(path))
            return
        if os.path.exists(path) and path_edit.property("confirmed") != path:
            answer = W.QMessageBox.question(
                dialog, "kepubverto for Sigil",
                "%s already exists. Replace it?" % os.path.basename(path))
            if answer != _rd._enum(W.QMessageBox, "StandardButton", "Yes"):
                return
        path_edit.setText(path)
        dialog.accept()

    browse.clicked.connect(pick)
    convert.clicked.connect(accept)
    buttons.rejected.connect(dialog.reject)
    _on_top(QtCore, dialog)
    accepted = _exec(dialog) == _rd._enum(W.QDialog, "DialogCode", "Accepted")
    if not accepted:
        return None
    return path_edit.text(), combo.currentData()


def show_result(title, text, details, folder):
    """Say what the conversion did. `details` is shown below the text, one
    line each; `folder`, when given, gets a Show in folder button."""
    QtCore, QtGui, QtWidgets = _rd._qt()
    _app(QtWidgets)
    box_cls = QtWidgets.QMessageBox
    box = box_cls()
    box.setWindowTitle("kepubverto for Sigil")
    box.setIcon(_rd._enum(box_cls, "Icon", "Information" if folder
                          else "Warning"))
    box.setText(title)
    box.setInformativeText(text)
    if details:
        box.setDetailedText("\n".join(details))
    show = None
    if folder:
        show = box.addButton("Show in folder", _rd._enum(
            box_cls, "ButtonRole", "ActionRole"))
    box.addButton(_rd._enum(box_cls, "StandardButton", "Ok"))
    _on_top(QtCore, box)
    _exec(box)
    if show is not None and box.clickedButton() is show:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))
