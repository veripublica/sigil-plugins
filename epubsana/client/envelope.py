# epubsana for Sigil — parsing epubsana's JSON envelope
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""The `--format json` envelope, as epubsana 0.42.0 documents it.

The envelope is the family's (conventions FORMATS.md). What is epubsana's own
is the input's `summary` and the meaning of its items:

  * `summary` has `fatals_before` / `fatals_after`, the same for errors,
    warnings, infos and usages, and `applied`, `skipped`, `proposed`,
    `reverted`. Severity has five values and a fatal is not an error, so both
    are read.
  * Each item is one fix: `outcome` (`proposed` on a dry run; `applied`,
    `skipped` or `reverted` after one), `code`, `rule`, `severity` (of the
    defect being repaired), `location`, `message`, and `data` with `index`
    (the selector `--apply` takes), `fix_id`, `tier` (`auto_safe` or
    `confirm_needed`) and `changes` (`path`, `note`).

**Parse stdout first, whatever the exit code.** Exit 1 only means the goal
(a valid book) was not met. Exit 2 carries an envelope when the book could
not be read; a usage error prints nothing on stdout, and then stderr is the
explanation.
"""

import json

SEVERITIES = ("fatals", "errors", "warnings", "infos", "usages")


class EnvelopeError(Exception):
    """stdout held no envelope. The message is epubsana's stderr."""


class Change(object):
    __slots__ = ("path", "note")

    def __init__(self, item):
        self.path = item.get("path", "")
        self.note = item.get("note", "")


class Fix(object):
    """One item: a proposed, applied, skipped or reverted fix."""

    __slots__ = ("index", "fix_id", "tier", "outcome", "code", "rule",
                 "severity", "location", "message", "changes")

    def __init__(self, item):
        data = item.get("data") or {}
        self.index = data.get("index")
        self.fix_id = data.get("fix_id", "")
        self.tier = data.get("tier", "")
        self.outcome = item.get("outcome", "")
        self.code = item.get("code", "")
        self.rule = item.get("rule", "")
        self.severity = item.get("severity", "")
        self.location = item.get("location")
        self.message = item.get("message", "")
        self.changes = [Change(c) for c in (data.get("changes") or [])]

    @property
    def auto_safe(self):
        return self.tier == "auto_safe"

    @property
    def paths(self):
        """The files this fix touches, in order, each once."""
        seen = []
        for change in self.changes:
            if change.path and change.path not in seen:
                seen.append(change.path)
        return seen

    def __repr__(self):
        return "<Fix %s %s %s>" % (self.index, self.fix_id, self.outcome)


class Envelope(object):
    """One run. One book per run, so `inputs[0]` is the book."""

    def __init__(self, doc):
        self.doc = doc
        self.tool_version = doc.get("tool_version", "")
        inputs = doc.get("inputs") or [{}]
        book = inputs[0]
        self.input_status = book.get("status", "")
        self.error = book.get("error")
        self.output = book.get("output")
        self.summary = book.get("summary") or {}
        self.fixes = [Fix(i) for i in (book.get("items") or [])
                      if i.get("type", "fix") == "fix"]

    @property
    def version(self):
        return self.tool_version.split("+")[0]

    @property
    def could_not_read(self):
        return self.input_status == "error"

    def count(self, key):
        try:
            return int(self.summary.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    def counts(self, when):
        """`{"fatals": n, "errors": n, …}` for `when` = "before" or "after"."""
        return dict((s, self.count("%s_%s" % (s, when))) for s in SEVERITIES)

    def outcome(self, name):
        return [f for f in self.fixes if f.outcome == name]


def parse_envelope(stdout, stderr=b"", returncode=0):
    """An `Envelope`, or `EnvelopeError` with epubsana's own words."""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    try:
        doc = json.loads(stdout)
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        raise EnvelopeError(
            stderr.strip()
            or "epubsana exited with %s and produced no output" % returncode)
    return Envelope(doc)
