# epubsana for Sigil — client for the epubsana repairer
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""This plugin's client for the epubsana binary.

**It belongs to the Sigil plugin and to nothing else.** Every plugin in this
repository carries its own copy of what it needs, so someone auditing one
plugin reads one folder. `binary.py`, `plugin_release.py` and
`release_dialog.py` began as copies of kepubverto for Sigil's; `writeback.py`
is this plugin's own: it carries epubsana's repaired book back into Sigil.

It talks to epubsana as a **subprocess over its documented JSON envelope**,
and never links it. That keeps the licences apart (epubsana is
AGPL-3.0-only OR commercial; this plugin is GPL-3.0-only) and it is why no
binary is shipped inside the plugin zip.
"""
