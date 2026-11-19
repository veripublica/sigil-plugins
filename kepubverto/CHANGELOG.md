# Changelog — kepubverto for Sigil

This plugin is versioned independently of kepubverto and of the other plugins
in this repository. The version Sigil shows comes from `plugin.xml`.

## [0.1.0] — 2026-11-19

- First release. An output plugin: it converts the book open in Sigil to a
  `.kepub.epub` with kepubverto and saves it where you choose, with the
  hyphenation you choose. The book in Sigil, and its file, are not changed.
- In an Automate list it writes beside the book and never replaces a file.
- Downloads and verifies kepubverto on first use, keeps it current, and tells
  you when a newer version of the plugin is out.
