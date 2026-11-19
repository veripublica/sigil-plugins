# kepubverto for Sigil — is there a newer release of this plugin?
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Find out whether a newer kepubverto for Sigil has been released.

**It tells; it never installs.** Replacing the kepubverto binary is safe to do
silently because the archive is checked against its release's checksums and
the binary is a separate program. Replacing this plugin's own Python while
Sigil is running it is neither, and it would bypass Sigil's own Add Plugin
step. So the most the plugin does is say that a newer release exists and
where it is: in the summary line, and in a window (`release_dialog.py`).

**Not `releases/latest`, which is the trick `binary.py` uses.** The
sigil-plugins repository holds the Sigil plugins for several tools, each
released on its own, so GitHub's "latest release" there is whichever plugin
shipped last. The API would have to page through every release (about 31 KB
of JSON, and rate-limited). Instead the repository keeps `latest.json` at its
root, one small entry per plugin, updated in each release commit, and it is
read from `raw.githubusercontent.com`.

**Only the version is taken from the network.** The link shown to the user is
built here from that version, so the file cannot point a reader anywhere but
this repository's own release page, and a version that is not plain
`X.Y.Z` is ignored.
"""

import json
import re

from .binary import _get, parse_version

REPO = "veripublica/sigil-plugins"

#: This plugin's key in `latest.json`, which is also its tag prefix.
PLUGIN = "kepubverto"

LATEST_URL = "https://raw.githubusercontent.com/%s/main/latest.json" % REPO

RELEASE_PAGE = "https://github.com/%s/releases/tag/%s-v%%s" % (REPO, PLUGIN)

_VERSION = re.compile(r"^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$")


def read_latest(text):
    """The version `latest.json` names for this plugin, or None.

    None for anything that is not the expected shape. The file is ours, but it
    arrives over the network, and an answer we cannot read must mean "nothing
    to say" rather than a guess.
    """
    try:
        data = json.loads(text)
    except ValueError:
        return None
    entry = data.get(PLUGIN) if isinstance(data, dict) else None
    version = entry.get("version") if isinstance(entry, dict) else None
    if isinstance(version, str) and _VERSION.match(version):
        return version
    return None


def latest_version(timeout):
    """Fetch `latest.json` and return this plugin's newest version, or None.

    Network errors are raised; the caller decides that they never matter.
    """
    return read_latest(_get(LATEST_URL, timeout).decode("utf-8", "replace"))


def is_newer(latest, current):
    """True only when both versions can be read and `latest` is greater.

    Compared as numbers, so 0.10.0 is newer than 0.9.9.
    """
    if not latest or not current:
        return False
    new = parse_version(latest)
    old = parse_version(current)
    return bool(new and old and new > old)


def release_page(version):
    return RELEASE_PAGE % version
