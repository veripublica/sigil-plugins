# Changelog — epubsana for Sigil

This plugin is versioned independently of epubsana and of the other plugins
in this repository. The version Sigil shows comes from `plugin.xml`.

## [0.1.0] — 2026-11-19

- First release. An edit plugin: epubsana repairs the book open in Sigil, with
  the fixes you choose. Safe fixes are ticked; fixes that make a visible
  change are not.
- The repair is carried into Sigil whole or not at all. The book is read back
  out of Sigil and compared with epubsana's output before Sigil takes any
  change. The book is not saved for you.
- Fixes Sigil cannot take, or makes itself (the EPUB version, media-types, the
  container), are listed but not offered.
- In an Automate list, only the safe fixes are applied, with the same checks.
- Downloads and verifies epubsana 0.42.0 or newer on first use, keeps it
  current, and tells you when a newer version of the plugin is out.
