# epubsana for Sigil — running the epubsana binary
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Invoke epubsana twice per repair: once to plan, once to apply.

`--dry-run` lists the proposals and changes nothing. `--apply <indices>`
applies exactly the listed ones and asks nothing, which is the mode epubsana
documents for a plugin that has already asked a person. Planning is
deterministic, so the same book gives the same indices both times; the second
run is always on the same `.epub` file as the first.

The output always goes to a fresh path inside a temporary folder, so `-f` is
never passed and the input is only ever read.
"""

import os
import subprocess

from .envelope import parse_envelope

#: A repair re-validates the book after applying, and bisects when a count
#: rises, so it can take longer than a conversion. Generous on purpose.
DEFAULT_TIMEOUT = 600


class RepairerNotFound(Exception):
    """No usable binary."""


def _no_window_kwargs():
    """Keep a console window from flashing on Windows."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


def plan_command(binary, epub_path):
    return [binary, "-i", epub_path, "--dry-run", "--format", "json"]


def apply_command(binary, epub_path, output_path, indices):
    """`indices` are epubsana's own 1-based plan positions."""
    return [binary, "-i", epub_path, "-o", output_path, "--apply",
            ",".join(str(i) for i in indices), "--format", "json"]


def _run(cmd, timeout):
    if not cmd[0] or not os.path.isfile(cmd[0]):
        raise RepairerNotFound(cmd[0] or "(no path)")
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout,
                          **_no_window_kwargs())
    return parse_envelope(proc.stdout, proc.stderr, proc.returncode)


def plan(binary, epub_path, timeout=DEFAULT_TIMEOUT):
    """The proposals for `epub_path`, as an `Envelope`."""
    return _run(plan_command(binary, epub_path), timeout)


def repair(binary, epub_path, output_path, indices, timeout=DEFAULT_TIMEOUT):
    """Apply `indices` and write `output_path`; an `Envelope`."""
    return _run(apply_command(binary, epub_path, output_path, indices),
                timeout)


def binary_version(binary, timeout=15):
    """`epubsana -V` output (`epubsana 0.42.0+b0e10fa`), or None."""
    try:
        proc = subprocess.run([binary, "-V"], capture_output=True,
                              timeout=timeout, **_no_window_kwargs())
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or b"").decode("utf-8", "replace").strip()
    return text or None
