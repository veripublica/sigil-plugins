# AGENTS.md — sigil-plugins

Detail for anyone, person or code agent, working in this repository. The
README is the short version for people; this file is the one to keep true at
every release.

## Scope

This repository holds the Sigil plugins for the veripublica EPUB tools, one
folder per tool. What is learned about Sigil once (plugin API, packaging,
settings, the results panel, Automate lists) serves every plugin here.

| Folder | Plugin | Tool it runs | Tag | MobileRead thread |
|---|---|---|---|---|
| `epubveri/` | epubveri for Sigil | [epubveri](https://github.com/veripublica/epubveri), an EPUB validator | `epubveri-vX.Y.Z` | 374939 |
| `kepubverto/` | kepubverto for Sigil | [kepubverto](https://github.com/veripublica/kepubverto), EPUB to KEPUB for Kobo | `kepubverto-vX.Y.Z` | 376360 |
| `epubsana/` | epubsana for Sigil | [epubsana](https://github.com/veripublica/epubsana), an EPUB repairer | `epubsana-vX.Y.Z` | not yet |

epubveri for Sigil moved here from
[epubveri-plugins](https://github.com/veripublica/epubveri-plugins) at 0.3.5.
Its releases up to 0.3.4 (tags `sigil-v…`) and its history stay there.
Each plugin's type follows what its tool does to the book: a validator is a
`validation` plugin, a converter that writes a new file is an `output`
plugin, and a tool that changes the book itself is an `edit` plugin.

What a plugin here does not do:

- **It does not contain the tool it runs.** It downloads the tool's binary
  from that tool's GitHub release, verifies it against the release's
  `SHA256SUMS.txt`, and runs it as a separate program. No binary is ever
  shipped in a plugin zip. The tools are AGPL-3.0-only or commercial; the
  plugins are GPL-3.0-only, and running a separate program keeps the two
  apart.
- **It never judges the book itself.** The verdict and findings are the
  tool's. A wrong finding belongs in the tool's issue tracker.
- **It does not install a new version of itself.** It says that one exists.
  Replacing the binary silently is safe because it is checksum-verified and
  separate; replacing the plugin's own Python while Sigil runs it is not.
- **It shares no code with the other plugins.** Each folder carries its own
  copy of what it needs, so auditing a plugin means reading one folder. A fix
  in one plugin's `client/` may have to be made in another by hand.

## epubveri for Sigil

### What it runs

A validation plugin (`<type>validation</type>`, `<autostart>true</autostart>`).
It writes the book Sigil holds to a temporary `.epub`, then runs:

```
epubveri --format json -u -i <book.epub> --advisory
```

It parses the JSON envelope and adds one row per finding to Sigil's
validation panel. The envelope is specified in the conventions repository's
[`FORMATS.md`](https://github.com/veripublica/conventions). That document is
the contract, not epubveri's current output.

- **Rows:** Each row has a full container-relative path and the line. Where the
  position can be translated, it also has a Code View offset (UTF-16 code units,
  CR stripped). The message starts with epubveri's own label: `ERROR`,
  `WARNING`, `USAGE` or `ADVISORY`.
- **Summary line:** It names both versions, for example
  `epubveri 0.47.0 (plugin 0.3.5) — NOT VALID (…)`. It is added as a row only
  when the book has other findings, because any row makes Sigil's Automate
  lists abort. On a clean book it is printed instead, and Sigil shows "No
  Problems Found".
- **Failures:** A failure is printed and the plugin returns non-zero. Sigil
  discards result rows on a non-zero return.

### Binary download and update

- **Asset:** `epubveri-<target triple>.tar.gz` (`.zip` on Windows), from
  `https://github.com/veripublica/epubveri/releases/latest/download/`.
  The plugin chooses one of:
  - `aarch64-apple-darwin`, `x86_64-apple-darwin`;
  - `aarch64-pc-windows-msvc`, `x86_64-pc-windows-msvc`;
  - `aarch64-unknown-linux-gnu`, `x86_64-unknown-linux-gnu`.
- **Install and verification:** The archive is checked against
  `SHA256SUMS.txt` and unpacked with path checks, then the binary is kept next
  to the plugin. The binary's own SHA-256 is stored at install and compared
  before every run, which takes about 1.8 ms for 2.8 MB. If it has changed, it
  is not run.
- **Update check:** At most once an hour, with a 5 s timeout, the plugin
  fetches `SHA256SUMS.txt` (842 bytes) and compares the asset's line with
  the stored hash. If they differ, it downloads and verifies the new archive,
  and the summary says so.
- **Nothing here may stop a validation.** A failed check keeps the existing
  binary and records the attempt.
- **Stale notice:** After 30 days without a successful check, the summary adds
  a one-line age note.

### Newer-plugin notice

- **Source:** `latest.json` at this repository's root, one entry per plugin:

  ```json
  { "epubveri": { "version": "0.3.5" } }
  ```

  It is read from
  `https://raw.githubusercontent.com/veripublica/sigil-plugins/main/latest.json`
  in the same hourly check, and only after epubveri's own check has answered.
  An offline machine therefore still makes one failed request an hour.
- **Why not `releases/latest`:** this repository releases several plugins, so
  GitHub's "latest release" is whichever plugin shipped last.
- **What is trusted:** only a plain `X.Y.Z` version is taken from the file.
  The link is built by the plugin
  (`https://github.com/veripublica/sigil-plugins/releases/tag/epubveri-vX.Y.Z`).
- **Summary line:** While a newer, non-ignored version exists, the summary
  ends with `[epubveri for Sigil X.Y.Z is available: <link>]`.
- **Window:** A window offers Download, Ignore this version and Not now.
  - It is started at most once a day, as a detached process
    (`client/release_dialog.py`), after the plugin has exited, so it opens
    once Sigil has shown the results.
  - It never opens inside an Automate list (`bk.using_automate()`), or when
    no Qt binding (PySide6, then PyQt5) is importable.
  - "Ignore this version" is written into the settings file by that process,
    in Sigil's own JSON format.

### Settings

Sigil has no settings screen for plugins. Settings live in
`<Sigil preferences>/plugins_prefs/epubveri/epubveri.json`, and the plugin
writes the user-facing keys with their defaults on first run:

| Key | Default | Meaning |
|---|---|---|
| `autoupdate` | `true` | Any network use: binary update and newer-plugin check. Only `true`, `yes`, `on`, `1` and `y` mean on; anything else means off. |
| `show_usage` | `true` | List `USAGE` rows |
| `show_advisory` | `true` | List `ADVISORY` rows |
| `show_summary` | `true` | Show the summary line |
| `sort` | `severity` | `severity`, `severity-low` or `document`; an unknown word means `severity` |

For the display switches, only `false`, `no`, `off`, `0` and `n` mean off;
anything else shows. A hidden category is still counted in the summary, with
"hidden by your settings". Filtering is on the display only: `-u --advisory`
are passed on every run.

Bookkeeping keys, written by the plugin:
- `installed_sha256`, `binary_sha256`;
- `last_update_check`, `last_update_success`;
- `latest_plugin_version`, `plugin_notice_shown`, `ignored_plugin_version`.

These names are part of the plugin's contract with existing installs; do not
rename them. The same holds for the plugin name `epubveri` in `plugin.xml`:
Sigil derives the settings folder from it.

### Packaging

`python3 epubveri/build.py` writes `dist/epubveri/epubveri_sigil_vX.Y.Z.zip`,
taking the version from `plugin.xml`.

- **The zip name matters.** Sigil takes the plugin folder name from
  everything before the first `_`. It then requires every entry to sit under
  that folder and `epubveri/plugin.xml` to exist. So the zip must be named
  `epubveri_…` and must not be renamed.
- **What is left out:** `tests/`, `build.py`, `icon.py`, `__pycache__`, and
  any `epubveri` or `epubveri.exe`.
- **What is added:** the root `LICENSE`.
- **Icons:** `plugin.svg` and `plugin.png` are written by `epubveri/icon.py`
  from one description of the mark, and tests check that both match it.

### Layout

```
LICENSE  README.md  AGENTS.md  latest.json
kepubverto/           see "kepubverto for Sigil"
epubsana/             see "epubsana for Sigil"
epubveri/
  plugin.xml          name, version, type, engine, oslist
  plugin.py           run(bk): binary, validation, panel rows, summary
  client/
    binary.py         download, checksum, unpack, update check
    runner.py         the epubveri command line
    envelope.py       the JSON envelope parser
    plugin_release.py latest.json and version comparison
    release_dialog.py the only Qt code; also runs as the detached window
  icon.py  plugin.svg  plugin.png
  build.py
  tests/
    test_plugin.py    plugin.run against a fake Sigil container
    test_in_sigil.py  Sigil's own launcher.py, headless
  README.md  CHANGELOG.md
```

### Tests

```sh
EPUBVERI_BINARY=$(which epubveri) python3 -m unittest discover -s epubveri/tests
```

- 101 tests at 0.3.5.
- Without `EPUBVERI_BINARY` (or an `epubveri` binary next to the plugin), the
  tests that need one skip.
- `test_in_sigil.py` drives Sigil's own `launcher.py` and skips when Sigil is
  not installed. Set `SIGIL_APP=…` for a non-default install; the macOS
  default is `/Applications/Sigil.app/Contents`.
- No test touches the network. They seed the hourly check as done, or replace
  the fetchers.
- A green suite is not proof. The window, its position and Sigil's panel can
  only be judged in Sigil. The last check was on Sigil 2.8.6 (macOS, bundled
  Python 3.14 with PySide6).

## kepubverto for Sigil

An output plugin (`<type>output</type>`, `<autostart>true</autostart>`). It
never changes the book in Sigil, and never writes over the book's own file
(`get_epub_filepath()`), whatever the user types.

### Flow

1. Ensure the binary, exactly as epubveri for Sigil does:
   - `kepubverto-<target triple>.tar.gz` or `.zip` from
     `https://github.com/veripublica/kepubverto/releases/latest/download/`;
   - checked against `SHA256SUMS.txt`, and re-checked before every run;
   - an hourly update check, which also reads `latest.json`;
   - kepubverto 0.3.0 or newer, the first with the JSON report read here.
2. Ask, in one window (`client/ui.py`), where to save and how to hyphenate.
   - The default is `<last folder or the book's folder>/<book stem>.kepub.epub`.
   - Choosing the open book's file is refused; an existing file is replaced
     only after a yes.
   - In an Automate list (`bk.using_automate()`), or when no Qt binding is
     importable, there is no window. The target is
     `<book folder>/<book stem>.kepub.epub`, and the step fails (prints the
     reason, returns non-zero) when that file exists, when the book was never
     saved, or when the target would be the book itself.
3. Write the book with `copy_book_contents_to` into a temporary folder,
   `mimetype` first and stored, and run:

   ```
   kepubverto -i current.epub -o out.kepub.epub --format json [--hyphens auto|none] [--css …]
   ```

   `-f` is never passed: the output is always a fresh path. Only a finished
   KEPUB is moved to the target; the temporary folder is always removed.
4. Report, from the envelope's `summary` and `items`:
   - converted and total documents, spans added;
   - each document left as it was, with its path, reason and code;
   - "already carries Kobo's markup" when nothing was converted and
     documents were already converted;
   - kepubverto's refusal (stderr, no envelope), for example of `--css`.

   The result goes to a window with Show in folder, and as one
   `kepubverto: …` line on standard output, which Sigil keeps in the Plugin
   Runner log. kepubverto's exit 1 (written, some documents left alone) is
   a success for Sigil; a refusal or an unreadable book is a failure.
5. The newer-plugin notice, as in epubveri for Sigil, under the key
   `kepubverto` in `latest.json`.

### Settings

`<Sigil preferences>/plugins_prefs/kepubverto/kepubverto.json`:

| Key | Default | Meaning |
|---|---|---|
| `autoupdate` | `true` | Any network use; only `true`, `yes`, `on`, `1` and `y` mean on |
| `hyphens` | `book` | `book` (pass nothing), `auto` or `none`; the window's last choice; an unknown word means `book` |
| `css` | `[]` | A list of strings, or one string, each passed as `--css` |
| `last_folder` | none | The folder last saved to |

The bookkeeping keys are epubveri for Sigil's, with the same names.

### Layout and tests

```
kepubverto/
  plugin.xml  plugin.py  icon.py  plugin.svg  plugin.png  build.py
  client/
    binary.py  plugin_release.py  release_dialog.py   copies of epubveri for Sigil's
    envelope.py  runner.py                            copies of kepubverto for calibre's
    ui.py                                             the options and result windows
  tests/
    test_plugin.py    plugin.run against a fake output container; windows replaced
    test_in_sigil.py  the Automate path through Sigil's own launcher.py
```

```sh
KEPUBVERTO_BINARY=/path/to/kepubverto python3 -m unittest discover -s kepubverto/tests
```

37 tests at 0.1.0. Without a binary, the conversion tests skip. The windows
can only be judged in Sigil.

The icon is epubveri for Sigil's sheet with kepubverto for calibre's k (KF
Libron Bold, OFL 1.1, kept as outline data) in place of the tick.

## epubsana for Sigil

An edit plugin (`<type>edit</type>`). epubsana repairs the book Sigil holds,
and the repair is written into Sigil whole, or not at all.

### Flow

1. Ensure the binary, as the other plugins do:
   - from `veripublica/epubsana` releases, verified, with an hourly update
     check that also reads `latest.json`;
   - epubsana 0.42.0 or newer.
2. `copy_book_contents_to` into a temporary folder, zipped with `mimetype`
   first and stored, then:

   ```
   epubsana -i before.epub --dry-run --format json
   ```

   The plan's items carry `data.index`, `fix_id`, `tier` and `changes`.
   `NOT_IN_SIGIL` in `plugin.py` lists the fixes shown greyed out, with the
   reason:
   - `fix.package_version`: Sigil's wrapper refuses a version change;
   - `fix.html_media_type`, `fix.image_media_type`,
     `fix.non_preferred_media_type`: Sigil has no call for media-type;
   - `fix.manifest_href_spaces`, `fix.mimetype_packaging`,
     `fix.empty_directory`: Sigil writes these itself.
3. The choice:
   - `client/ui.py` ticks `auto_safe` and leaves `confirm_needed` unticked;
   - in an Automate list (`bk.using_automate()`), or without Qt, the
     `auto_safe` fixes are chosen with no window.
4. Apply exactly the chosen fixes. epubsana re-validates and reverts a fix
   that raised any `(id, rule)` count.

   ```
   epubsana -i before.epub -o fixed.epub --apply <indices> --format json
   ```

5. `client/writeback.py` `plan()` compares the two books and maps every
   difference to a container call:
   - a changed manifest file: `writefile`;
   - a changed non-manifest file: `writeotherfile`;
   - a removed manifest item: `deletefile`;
   - the OPF, read on both sides by **Sigil's own `opf_parser.Opf_Parser`**:
     `setmetadataxml`, `setspine` / `setspine_epub3`, `setspine_ppd`,
     `setguide`, `setbindings_epub3`, `setpackagetag`, and
     `set_manifest_epub3_attributes` (EPUB 3 only).

   Any other difference raises `Unmappable` before a call is made: a new
   file, a moved file, a media-type or version change, or an EPUB 3
   attribute in EPUB 2.
6. `apply()`, then `copy_book_contents_to` again. `verify()` compares every
   file byte for byte and the OPF as Sigil models it. A second `--dry-run`
   on the read-back must give the repair's `*_after` counts.

   Any difference, or an exception from Sigil, returns non-zero.
   `launcher.py` then writes `<result>failed</result>` with an empty
   `<changes/>` and no OPF, so Sigil takes nothing from the run.
7. Report: the counts before and after, the applied and reverted fixes, and
   the files written. The book is left unsaved in Sigil.

### Facts about Sigil this rests on

Measured on Sigil 2.8.6 through its own `launcher.py`:

- `readfile` returns a plugin-written file from the out folder.
  `copy_book_contents_to` returns `build_opf()` once the OPF is modified. So
  the read-back is what Sigil will hold.
- Sigil's `Opf_Parser` reads `text/html` as `application/xhtml+xml`, and
  Sigil rewrites the OPF when it opens a book. So the media-type, href and
  container fixes either never come up or change nothing in Sigil.

### Settings

`<Sigil preferences>/plugins_prefs/epubsana/epubsana.json`: `autoupdate`
(default `true`; only `true`, `yes`, `on`, `1` and `y` mean on), and the
bookkeeping keys of the other plugins, with the same names.

### Layout and tests

```
epubsana/
  plugin.xml  plugin.py  icon.py  plugin.svg  plugin.png  build.py
  client/
    binary.py  plugin_release.py  release_dialog.py   copies of kepubverto for Sigil's
    envelope.py  runner.py                            epubsana's report, its two command lines
    writeback.py                                      the repair into Sigil, and its verification
    ui.py                                             the plan and result windows
  tests/
    test_plugin.py    envelope, commands, plan split, writeback against Sigil's Opf_Parser, run()
    test_in_sigil.py  the Automate path through Sigil's own launcher.py, edit type
```

```sh
EPUBSANA_BINARY=/path/to/epubsana python3 -m unittest discover -s epubsana/tests
```

30 tests at 0.1.0. Without Sigil, the `Opf_Parser` and launcher tests skip;
without a binary, the tests that run epubsana skip. The windows can only be
judged in Sigil.

The icon is epubveri for Sigil's sheet, with a plus in place of the tick,
drawn with the tick's stroke.

## Releasing

Each plugin is released on its own. There are no workflows; the tag and the
GitHub release are made by hand.

1. Bump the version in `<plugin>/plugin.xml` and in that plugin's entry in
   `latest.json`, in the same commit. A test fails if they differ.
2. In `<plugin>/CHANGELOG.md`, turn `## [Unreleased]` into
   `## [X.Y.Z] — YYYY-MM-DD`.
3. Run the tests, build, and check the zip with `unzip -l`. Write a one-line
   `SHA256SUMS.txt` for the zip.
4. Commit `Release <plugin title> X.Y.Z`, tag `<plugin>-vX.Y.Z`, push both.
5. Create the GitHub release **straight after the push**: `latest.json` on
   `main` is live as soon as it is pushed, and a notice must not point at a
   page that does not exist yet. The title is `<plugin title> X.Y.Z`, the
   notes are that version's CHANGELOG section, and the assets are the zip and
   `SHA256SUMS.txt`.
6. Download the assets and check them against `SHA256SUMS.txt`, and read
   `latest.json` from raw.githubusercontent.com.

## Conventions

- **Licence:** GPL-3.0-only. Every source file carries
  `SPDX-License-Identifier: GPL-3.0-only`.
- **Language:** English for code, docs, commits and release notes.
- **Comments:** Code comments explain *why*, with the evidence: the
  MobileRead post, the Sigil source line, the measurement. Keep that habit,
  and correct a comment when the fact behind it changes.
