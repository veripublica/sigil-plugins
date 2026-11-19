# sigil-plugins

These are the Sigil plugins for my EPUB tools. If you edit books in
[Sigil](https://sigil-ebook.com/), a plugin here lets you run one of the tools
on the book you have open, without leaving the editor.

## Download

| Plugin | What it does | Latest | Download |
|---|---|---|---|
| epubveri for Sigil | Checks the book against the EPUB specification and lists what it finds in Sigil's validation panel | [0.3.6](https://github.com/veripublica/sigil-plugins/releases/tag/epubveri-v0.3.6) | [epubveri_sigil_v0.3.6.zip](https://github.com/veripublica/sigil-plugins/releases/download/epubveri-v0.3.6/epubveri_sigil_v0.3.6.zip) |
| kepubverto for Sigil | Saves a copy of the book as a KEPUB for Kobo readers | [0.1.0](https://github.com/veripublica/sigil-plugins/releases/tag/kepubverto-v0.1.0) | [kepubverto_sigil_v0.1.0.zip](https://github.com/veripublica/sigil-plugins/releases/download/kepubverto-v0.1.0/kepubverto_sigil_v0.1.0.zip) |
| epubsana for Sigil | Repairs the book with the fixes you choose, checked before Sigil takes them | [0.1.0](https://github.com/veripublica/sigil-plugins/releases/tag/epubsana-v0.1.0) | [epubsana_sigil_v0.1.0.zip](https://github.com/veripublica/sigil-plugins/releases/download/epubsana-v0.1.0/epubsana_sigil_v0.1.0.zip) |

Download the zip and add it in Sigil with Plugins, Manage Plugins, Add Plugin.
Please keep the file name as it is, because Sigil reads the plugin's name from
it. On first use a plugin downloads its tool itself, checks it, and keeps it
up to date. When a new version of the plugin is out, it tells you, so you
only need this page once.

Earlier versions: [epubveri](https://github.com/veripublica/sigil-plugins/releases?q=epubveri&expanded=true),
[kepubverto](https://github.com/veripublica/sigil-plugins/releases?q=kepubverto&expanded=true),
[epubsana](https://github.com/veripublica/sigil-plugins/releases?q=epubsana&expanded=true).
The Releases page mixes all three plugins, and its "Latest" label marks
whichever plugin was released last, so the table above is the easier way in.

## More

epubveri and kepubverto do not change the book you are editing. epubsana
does, but only with the fixes you tick, and it does not save the book for
you.

Each plugin's own README ([epubveri](epubveri/README.md),
[kepubverto](kepubverto/README.md), [epubsana](epubsana/README.md)) explains
how it works and its settings, and [AGENTS.md](AGENTS.md) has the technical
detail. You can report problems in
[Issues](https://github.com/veripublica/sigil-plugins/issues), or in each
plugin's MobileRead thread:
[epubveri](https://www.mobileread.com/forums/showthread.php?t=374939),
[kepubverto](https://www.mobileread.com/forums/showthread.php?t=376360),
[epubsana](https://www.mobileread.com/forums/showthread.php?t=376361).

The plugins are GPL-3.0-only ([LICENSE](LICENSE)). The tools they run are
licensed separately. A plugin only runs its tool as a separate program and
ships none of it.
