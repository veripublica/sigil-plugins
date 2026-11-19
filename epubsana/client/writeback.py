# epubsana for Sigil — carrying a repaired book back into Sigil
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Turn "the book epubsana wrote" into calls on Sigil's edit container.

epubsana works on a packaged `.epub` and hands back another one. Sigil's edit
plugin interface cannot take a book; it takes per-file writes and a handful of
OPF setters. This module finds every difference between the two books and
maps each to one of those calls, **or refuses the whole repair**:

* A manifest file whose bytes changed: `writefile(id, bytes)`.
* A file outside the manifest (`META-INF/…`): `writeotherfile(href, bytes)`.
* A manifest item that disappeared: `deletefile(id)`, which also drops its
  spine entries.
* The OPF, compared through **Sigil's own `Opf_Parser`** on both sides, so
  every value is already in the shape Sigil's setters take: metadata
  (`setmetadataxml`), spine (`setspine` / `setspine_epub3`), page progression
  (`setspine_ppd`), guide (`setguide`), bindings (`setbindings_epub3`), the
  package tag (`setpackagetag`), and an item's EPUB 3 `properties`,
  `fallback` or `media-overlay` (`set_manifest_epub3_attributes`).

Anything else is `Unmappable`: a new file, a changed `href`, `media-type` or
package `version` (Sigil's wrapper refuses the last one outright), or an
EPUB 3 manifest attribute in an EPUB 2 book. `plan` raises before a single
call is made, so a repair Sigil cannot take whole is not taken at all.

`mimetype` and directory entries are Sigil's to write when it saves.

`verify` then reads the book back out of Sigil and compares it with
epubsana's output: every file byte for byte, and the OPF as Sigil models it.
The plugin returns a failure when they differ, and Sigil then discards every
change this run made.
"""

import os


class Unmappable(Exception):
    """A difference Sigil's edit interface has no call for."""


class Op(object):
    """One call on the container, described for the report."""

    __slots__ = ("what", "call")

    def __init__(self, what, call):
        self.what = what
        self.call = call

    def __repr__(self):
        return "<Op %s>" % self.what


def _files(root):
    """`{bookpath: absolute path}` for every regular file under `root`."""
    out = {}
    for base, _dirs, names in os.walk(root):
        for name in names:
            full = os.path.join(base, name)
            out[os.path.relpath(full, root).replace(os.sep, "/")] = full
    return out


def _read(path):
    with open(path, "rb") as handle:
        return handle.read()


class OpfModel(object):
    """The parts of an OPF Sigil models, read by Sigil's own parser."""

    def __init__(self, parser_cls, opf_path, opf_bookpath):
        op = parser_cls(opf_path, opf_bookpath)
        self.version = op.get_epub_version()
        self.package_tag = op.get_package_tag()
        self.metadataxml = op.get_metadataxml()
        self.href = dict(op.get_manifest_id_to_href_dict())
        self.mime = dict(op.get_manifest_id_to_mime_dict())
        self.bookpath = dict(op.get_manifest_id_to_bookpath_dict())
        self.properties = dict(op.get_manifest_id_to_properties_dict())
        self.fallback = dict(op.get_manifest_id_to_fallback_dict())
        self.overlay = dict(op.get_manifest_id_to_overlay_dict())
        self.spine = [tuple(s) for s in op.get_spine()]
        self.ppd = op.get_spine_ppd()
        self.guide = [tuple(g) for g in op.get_guide()]
        self.bindings = [tuple(b) for b in op.get_bindings()]

    def key(self):
        """Everything compared, as one value."""
        return (self.version, self.package_tag, self.metadataxml,
                sorted(self.href.items()), sorted(self.mime.items()),
                sorted(self.properties.items()), sorted(self.fallback.items()),
                sorted(self.overlay.items()), self.spine, self.ppd,
                self.guide, self.bindings)


def _opf_ops(bk, before, after):
    """The setter calls that turn the model `before` into `after`."""
    ops = []
    epub3 = not str(before.version).startswith("2")

    if after.version != before.version:
        raise Unmappable("the package version changes (%s to %s); Sigil does "
                         "not let a plugin change it"
                         % (before.version, after.version))

    added = sorted(set(after.href) - set(before.href))
    if added:
        raise Unmappable("the manifest gains %s" % ", ".join(added))
    for mid in sorted(set(after.href) & set(before.href)):
        if after.bookpath.get(mid) != before.bookpath.get(mid):
            raise Unmappable("manifest item %s moves to %s"
                             % (mid, after.bookpath.get(mid)))
        if after.mime.get(mid) != before.mime.get(mid):
            raise Unmappable("manifest item %s changes media-type to %s; "
                             "Sigil has no call for that"
                             % (mid, after.mime.get(mid)))
        attrs = [(after.properties.get(mid), before.properties.get(mid)),
                 (after.fallback.get(mid), before.fallback.get(mid)),
                 (after.overlay.get(mid), before.overlay.get(mid))]
        if any(a != b for a, b in attrs):
            if not epub3:
                raise Unmappable("manifest item %s changes an EPUB 3 "
                                 "attribute in an EPUB 2 book" % mid)
            props, fb, ov = (after.properties.get(mid),
                             after.fallback.get(mid), after.overlay.get(mid))
            ops.append(Op("manifest attributes of %s" % mid,
                          lambda m=mid, p=props, f=fb, o=ov:
                          bk.set_manifest_epub3_attributes(m, p, f, o)))
    for mid in sorted(set(before.href) - set(after.href)):
        ops.append(Op("remove %s (%s)" % (mid, before.bookpath.get(mid)),
                      lambda m=mid: bk.deletefile(m)))

    if after.spine != before.spine:
        # Sigil's deletefile already drops the spine entries of a removed
        # item; the setter then states the order epubsana wrote.
        if epub3:
            spine = [(s[0], s[1], s[2] if len(s) > 2 else None)
                     for s in after.spine]
            ops.append(Op("spine", lambda s=spine: bk.setspine_epub3(s)))
        else:
            spine = [(s[0], s[1]) for s in after.spine]
            ops.append(Op("spine", lambda s=spine: bk.setspine(s)))
    if after.ppd != before.ppd:
        ops.append(Op("page progression", lambda p=after.ppd:
                      bk.setspine_ppd(p)))
    if after.guide != before.guide:
        ops.append(Op("guide", lambda g=after.guide: bk.setguide(list(g))))
    if after.bindings != before.bindings:
        ops.append(Op("bindings", lambda b=after.bindings:
                      bk.setbindings_epub3(list(b))))
    if after.metadataxml != before.metadataxml:
        ops.append(Op("metadata", lambda m=after.metadataxml:
                      bk.setmetadataxml(m)))
    if after.package_tag != before.package_tag:
        ops.append(Op("package tag", lambda t=after.package_tag:
                      bk.setpackagetag(t)))
    return ops


def plan(bk, before_dir, after_dir, parser_cls):
    """The calls that make Sigil's book equal epubsana's output.

    `before_dir` is the book as handed to epubsana (`copy_book_contents_to`),
    `after_dir` the repaired book unpacked. Raises `Unmappable` before any
    call is made.
    """
    opf = bk.get_opfbookpath()
    before = _files(before_dir)
    after = _files(after_dir)
    ops = []

    gained = sorted(set(after) - set(before) - {"mimetype"})
    if gained:
        raise Unmappable("the repair adds %s" % ", ".join(gained))

    for path in sorted(before):
        if path in ("mimetype", opf):
            continue
        mid = bk.bookpath_to_id(path)
        if path not in after:
            if mid is None:
                raise Unmappable("the repair removes %s, which is not in "
                                 "the manifest" % path)
            continue                      # deletefile, from the OPF diff
        old, new = _read(before[path]), _read(after[path])
        if old == new:
            continue
        if mid is not None:
            ops.append(Op("write %s" % path,
                          lambda m=mid, d=new: bk.writefile(m, d)))
        else:
            ops.append(Op("write %s" % path,
                          lambda p=path, d=new: bk.writeotherfile(p, d)))

    if opf not in after:
        raise Unmappable("the repaired book has no %s" % opf)
    ops.extend(_opf_ops(bk,
                        OpfModel(parser_cls, before[opf], opf),
                        OpfModel(parser_cls, after[opf], opf)))
    return ops


def apply(ops):
    for op in ops:
        op.call()


def verify(bk, readback_dir, after_dir, parser_cls):
    """Differences between the book as Sigil now holds it and epubsana's
    output, as sentences; an empty list when there are none."""
    opf = bk.get_opfbookpath()
    now = _files(readback_dir)
    want = _files(after_dir)
    problems = []
    for path in sorted(set(now) | set(want)):
        if path in ("mimetype", opf):
            continue
        if path not in now:
            problems.append("%s is missing from Sigil's copy" % path)
        elif path not in want:
            problems.append("%s is in Sigil's copy but not in the repair"
                            % path)
        elif _read(now[path]) != _read(want[path]):
            problems.append("%s differs from the repair" % path)
    if opf in now and opf in want:
        if OpfModel(parser_cls, now[opf], opf).key() != \
                OpfModel(parser_cls, want[opf], opf).key():
            problems.append("%s, as Sigil models it, differs from the "
                            "repair" % opf)
    else:
        problems.append("%s is missing" % opf)
    return problems
