# epubsana for Sigil — the plan window and the result window
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""The two windows a repair shows, and nothing else.

Qt is reached through `release_dialog`'s helpers, so the bindings it accepts
(PySide6, then PyQt5) and the way a window is brought in front of Sigil are
written once in this plugin. Without a binding, `available()` is False and
the plugin behaves as in an Automate list: the `auto_safe` fixes only, no
window, the outcome printed.
"""

from . import release_dialog as _rd

TIER_LABEL = {"auto_safe": "safe", "confirm_needed": "check"}


def available():
    return _rd.available()


def _app(QtWidgets):
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(["epubsana"])
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


def ask_fixes(offered, unavailable, counts):
    """Let the user choose which fixes to apply.

    `offered` is a list of `Fix`; `unavailable` a list of `(Fix, reason)`,
    shown but not selectable; `counts` the book's findings before, as
    `Envelope.counts("before")`. Returns the chosen fixes' `index` values, or
    None when the user cancelled.
    """
    QtCore, QtGui, QtWidgets = _rd._qt()
    _app(QtWidgets)
    W = QtWidgets
    Qt = QtCore.Qt
    checked = _rd._enum(Qt, "CheckState", "Checked")
    unchecked = _rd._enum(Qt, "CheckState", "Unchecked")
    user_checkable = _rd._enum(Qt, "ItemFlag", "ItemIsUserCheckable")
    enabled = _rd._enum(Qt, "ItemFlag", "ItemIsEnabled")
    selectable = _rd._enum(Qt, "ItemFlag", "ItemIsSelectable")
    #: Where each row's fix is kept. A Python wrapper handed back by a signal
    #: need not be the object that was added, so rows carry their position.
    role = _rd._enum(Qt, "ItemDataRole", "UserRole")

    dialog = W.QDialog()
    dialog.setWindowTitle("epubsana for Sigil")
    dialog.resize(820, 520)
    layout = W.QVBoxLayout(dialog)

    layout.addWidget(W.QLabel(
        "epubsana found %d error(s) and %d fatal error(s) in the book, and can "
        "repair the ones below. Choose which to apply."
        % (counts.get("errors", 0), counts.get("fatals", 0))))
    note = W.QLabel(
        "<i>safe</i> fixes have exactly one correct, content-preserving "
        "repair and are ticked. <i>check</i> fixes are correct but make a "
        "visible change; look at what they do first. The changes stay in "
        "Sigil until you save, and taking a Checkpoint now lets you compare "
        "or go back.")
    note.setWordWrap(True)
    layout.addWidget(note)

    tree = W.QTreeWidget()
    tree.setHeaderLabels(["Fix", "Kind", "Files"])
    tree.setRootIsDecorated(False)
    tree.setColumnWidth(0, 560)
    tree.setColumnWidth(1, 60)
    items = []
    for fix in offered:
        files = fix.paths
        item = W.QTreeWidgetItem([
            fix.message, TIER_LABEL.get(fix.tier, fix.tier),
            str(len(files)) if len(files) != 1 else files[0].split("/")[-1]])
        item.setFlags(enabled | selectable | user_checkable)
        item.setCheckState(0, checked if fix.auto_safe else unchecked)
        item.setToolTip(0, "%s (%s)" % (fix.code, fix.fix_id))
        item.setData(0, role, len(items))
        items.append((item, fix))
        tree.addTopLevelItem(item)
    for fix, reason in unavailable:
        item = W.QTreeWidgetItem([fix.message, "n/a", reason])
        item.setFlags(_rd._enum(Qt, "ItemFlag", "NoItemFlags"))
        item.setToolTip(0, reason)
        tree.addTopLevelItem(item)
    layout.addWidget(tree, 3)

    details = W.QPlainTextEdit()
    details.setReadOnly(True)
    details.setPlaceholderText("Select a fix to see what it changes.")
    layout.addWidget(details, 2)

    def show(current, _previous=None):
        position = current.data(0, role) if current is not None else None
        fix = items[position][1] if isinstance(position, int) else None
        if fix is None:
            details.setPlainText("")
            return
        lines = ["%s  %s  (%s)" % (fix.code, fix.message, fix.fix_id), ""]
        lines += ["%s: %s" % (c.path, c.note) for c in fix.changes]
        details.setPlainText("\n".join(lines))

    tree.currentItemChanged.connect(show)

    buttons = W.QDialogButtonBox()
    apply_button = buttons.addButton("Apply", _rd._enum(
        W.QDialogButtonBox, "ButtonRole", "AcceptRole"))
    buttons.addButton(_rd._enum(W.QDialogButtonBox, "StandardButton",
                                "Cancel"))
    layout.addWidget(buttons)

    def chosen():
        return [f.index for i, f in items if i.checkState(0) == checked]

    def refresh(*_args):
        n = len(chosen())
        apply_button.setText("Apply %d fix(es)" % n if n else "Apply")
        apply_button.setEnabled(n > 0)

    tree.itemChanged.connect(refresh)
    refresh()
    apply_button.clicked.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    _on_top(QtCore, dialog)
    accepted = _exec(dialog) == _rd._enum(W.QDialog, "DialogCode", "Accepted")
    return chosen() if accepted else None


def show_result(title, text, details, ok):
    """Say what the repair did; `details` is one line each."""
    QtCore, QtGui, QtWidgets = _rd._qt()
    _app(QtWidgets)
    box_cls = QtWidgets.QMessageBox
    box = box_cls()
    box.setWindowTitle("epubsana for Sigil")
    box.setIcon(_rd._enum(box_cls, "Icon", "Information" if ok else "Warning"))
    box.setText(title)
    box.setInformativeText(text)
    if details:
        box.setDetailedText("\n".join(details))
    box.addButton(_rd._enum(box_cls, "StandardButton", "Ok"))
    _on_top(QtCore, box)
    _exec(box)
