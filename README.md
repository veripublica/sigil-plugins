# sigil-plugins

These are the Sigil plugins for my EPUB tools. If you edit books in
[Sigil](https://sigil-ebook.com/), a plugin here lets you run one of the tools
on the book you have open, without leaving the editor.

epubveri for Sigil checks the book against the EPUB specification with
[epubveri](https://github.com/veripublica/epubveri) and puts what it finds in
Sigil's validation panel, where a click takes you to the line. kepubverto for
Sigil saves a copy of the book as a KEPUB for Kobo readers with
[kepubverto](https://github.com/veripublica/kepubverto). Neither changes the
book you are editing. epubsana for Sigil repairs the book with
[epubsana](https://github.com/veripublica/epubsana): you choose the fixes,
and Sigil takes the repair only after it has been checked.

To install one, download its zip from
[Releases](https://github.com/veripublica/sigil-plugins/releases) and add it
in Sigil with Plugins, Manage Plugins, Add Plugin. Please keep the file name
as it is, because Sigil reads the plugin's name from it. On first use a
plugin downloads its tool itself, checks it, and keeps it up to date. When a
new version of the plugin is out, it tells you.

After a run, the first line in the panel tells you the verdict, for example:

```
epubveri 0.47.0 (plugin 0.3.6) — NOT VALID (2 error(s), 0 warning(s))
```

Each plugin's own README ([epubveri](epubveri/README.md),
[kepubverto](kepubverto/README.md), [epubsana](epubsana/README.md))
explains its settings, and
[AGENTS.md](AGENTS.md) has the technical detail. You can report problems in
[Issues](https://github.com/veripublica/sigil-plugins/issues), and for
epubveri also in its
[MobileRead thread](https://www.mobileread.com/forums/showthread.php?t=374939).

The plugins are GPL-3.0-only ([LICENSE](LICENSE)). The tools they run are
licensed separately. A plugin only runs its tool as a separate program and
ships none of it.
