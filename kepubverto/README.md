# kepubverto for Sigil

Convert the book you have open in Sigil to a **KEPUB**, the Kobo variant of
EPUB, with [kepubverto](https://github.com/veripublica/kepubverto). The KEPUB
is saved as a separate `.kepub.epub` file. The book in Sigil is not changed,
and its file on disk is never overwritten.

kepubverto adds the markup a Kobo reader uses to track reading position, page
through a chapter quickly and show reading statistics, and nothing else. It
inserts that markup at byte offsets and leaves every other byte of a document
as it was, so a book that was valid before the conversion is still valid
after it.

## Installing

1. Download `kepubverto_sigil_vX.Y.Z.zip` from
   [Releases](https://github.com/veripublica/sigil-plugins/releases).
   **Do not rename it.** Sigil takes the folder name from the part of the
   file name before the first underscore.
2. In Sigil: **Plugins → Manage Plugins → Add Plugin**, choose the zip.
3. Run it from **Plugins → Output → kepubverto**.

**On first use it downloads the kepubverto binary** for your platform from
kepubverto's own releases and keeps it beside the plugin. The archive is
checked against that release's `SHA256SUMS.txt`, and the binary's checksum is
checked again before every run; a binary that has changed since it was
verified is not run. The plugin zip contains no binary.

## Using it

A window asks two things:

- **Save as**: where the KEPUB goes. It starts in the folder you used last,
  or beside the book, with the book's name and `.kepub.epub`. Choosing an
  existing file asks before replacing it. The book open in Sigil cannot be
  chosen.
- **Hyphenation**: *As the book says* adds nothing; *On* turns hyphenation on
  everywhere except headings, table cells and places where the book chose for
  itself; *Off* turns it off everywhere.

What is converted is the book as Sigil holds it, unsaved changes included.
Sigil rewrites some things when it opens a book, for example it encodes
spaces in file references as `%20`, so the KEPUB can differ slightly from what
converting the same file with kepubverto directly gives you.

When it is done, a second window says how many documents were converted and
how many spans were added, with **Show in folder**. A document kepubverto
could not convert, for example one that is not well-formed XML, is copied
into the KEPUB unchanged, and the window names it with kepubverto's reason.
Fixing it in Sigil and converting again converts it too. A book that already
carries Kobo's markup is copied as it is, and the window says so.

**In an Automate list** no window opens. The KEPUB is written beside the book
as `<book>.kepub.epub`. If that file already exists, nothing is replaced and
the step fails with that reason. A book that has never been saved has no
folder to write beside, so that step fails too.

## Settings

Sigil gives a plugin no settings screen, so the rest lives in
`<Sigil preferences>/plugins_prefs/kepubverto/kepubverto.json`, which the
plugin writes on its first run:

```json
{
  "autoupdate": true,
  "hyphens": "book",
  "css": []
}
```

| setting | meaning |
|---|---|
| `autoupdate` | `false`: nothing is ever requested over the network |
| `hyphens` | the window's last choice: `book`, `auto` or `none` |
| `css` | your own CSS, added after kepubverto's rules, as a list of strings |

kepubverto refuses CSS that refers to a file, has `@font-face`, or would add a
finding epubveri reports. The window then shows its reason, and nothing is
written.

## Keeping up to date

At most once an hour the plugin compares the kepubverto release's
`SHA256SUMS.txt` with what it installed, and fetches and verifies a newer
binary when there is one. It also reads this repository's `latest.json`. When
a newer version of the plugin is out, a window says so once Sigil has finished,
at most once a day, with **Download**, **Ignore this version** and **Not now**.
The plugin never installs a new version of itself. If the machine is offline,
the copy you have is used and nothing is said. After a month without a
successful check, the result mentions the binary's age.

## Reporting a problem

[Issues](https://github.com/veripublica/sigil-plugins/issues). A conversion
that went wrong belongs to [kepubverto](https://github.com/veripublica/kepubverto/issues);
the version line in the result window names both versions.

## Licence

GPL-3.0-only ([LICENSE](../LICENSE)). kepubverto itself is AGPL-3.0-only or a
commercial licence; the plugin runs it as a separate program and ships none
of it. The icon's k is drawn from the outline of KF Libron Bold by Nico
Verbruggen ([libron](https://github.com/nicoverbruggen/libron), SIL Open Font
License 1.1); no font is included.
