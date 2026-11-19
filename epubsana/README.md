# epubsana for Sigil

Repair the book you have open in Sigil with
[epubsana](https://github.com/veripublica/epubsana). epubsana fixes the
defects epubveri reports where there is exactly one correct, content-preserving
repair, and leaves everything else alone. You choose which fixes to apply.

## Installing

1. Download `epubsana_sigil_vX.Y.Z.zip` from
   [Releases](https://github.com/veripublica/sigil-plugins/releases).
   **Do not rename it.** Sigil takes the folder name from the part of the
   file name before the first underscore.
2. In Sigil: **Plugins → Manage Plugins → Add Plugin**, choose the zip.
3. Run it from **Plugins → Edit → epubsana**.

**On first use it downloads the epubsana binary** for your platform from
epubsana's own releases and keeps it beside the plugin. The archive is checked
against that release's `SHA256SUMS.txt`, and the binary's checksum is checked
again before every run; a binary that has changed since it was verified is
not run. The plugin zip contains no binary.

## Using it

A window lists what epubsana can repair in the book as Sigil holds it, unsaved
changes included. Each line says what the fix does. Selecting it shows every
file it touches and what changes there.

- **safe** fixes have exactly one correct, content-preserving repair. They
  are ticked.
- **check** fixes are correct but make a visible change, such as dropping a
  repeated spine entry or renumbering the NCX. They are not ticked; look at
  what they do first.
- A few fixes are listed greyed out, with the reason. Sigil does not let a
  plugin make those changes, or Sigil already makes them itself when it opens
  or saves a book: the EPUB version, a file's media-type, the container.

When you choose **Apply**, three things happen:

1. epubsana applies exactly the fixes you ticked. It checks the book again
   afterwards, and takes back any fix that made another finding more frequent.
2. The plugin carries the repair into Sigil.
3. The plugin reads the book back out of Sigil and compares it with what
   epubsana wrote: every file, and the package document as Sigil sees it.

**If anything differs, or Sigil refuses a change, Sigil takes none of the
changes**, and the window says why. A repair is taken whole or not at all.

A second window then gives the errors and fatal errors before and after, and
lists the fixes that were applied or taken back.

**The repaired book is not saved.** Save it in Sigil to keep the changes, or
close it without saving to drop them. Taking a Checkpoint before you run the
plugin lets you compare the two versions, or go back to the earlier one.

**In an Automate list** no window opens. Only the *safe* fixes are applied,
with the same checks. If the checks fail, the step fails and nothing changes.

## Settings

Sigil gives a plugin no settings screen, so the one setting lives in
`<Sigil preferences>/plugins_prefs/epubsana/epubsana.json`:

```json
{ "autoupdate": true }
```

With `false`, nothing is ever requested over the network.

## Keeping up to date

At most once an hour the plugin compares the epubsana release's
`SHA256SUMS.txt` with what it installed, and fetches and verifies a newer
binary when there is one. It also reads this repository's `latest.json`. When
a newer version of the plugin is out, a window says so once Sigil has
finished, at most once a day, with **Download**, **Ignore this version** and
**Not now**. The plugin never installs a new version of itself.

## Reporting a problem

[Issues](https://github.com/veripublica/sigil-plugins/issues). A fix that did
the wrong thing belongs to [epubsana](https://github.com/veripublica/epubsana/issues);
a finding that looks wrong belongs to
[epubveri](https://github.com/veripublica/epubveri/issues). The result window
names the epubsana and plugin versions.

## Licence

GPL-3.0-only ([LICENSE](../LICENSE)). epubsana itself is AGPL-3.0-only or a
commercial licence; the plugin runs it as a separate program and ships none
of it.
