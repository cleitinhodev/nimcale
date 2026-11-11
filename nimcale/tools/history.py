# SPDX-License-Identifier: GPL-3.0-or-later
"""Undo / redo of model parameters, imported images and sculpt strokes (snapshot based)."""


class Snapshot:
    __slots__ = ("params", "sculpt", "tex", "hm", "label")

    def __init__(self, params, sculpt, tex, hm, label=""):
        self.params = params.copy()
        self.sculpt = sculpt          # arrays are never modified in place after a snapshot (copy-on-write)
        self.tex = tex
        self.hm = hm
        self.label = label

    def same(self, other):
        return (other is not None and self.params.key() == other.params.key() and self.sculpt is other.sculpt
                and self.tex is other.tex and self.hm is other.hm)


class History:
    def __init__(self, limit=80):
        self.limit = limit
        self.undo_stack = []
        self.redo_stack = []

    def clear(self):
        self.undo_stack.clear()
        self.redo_stack.clear()

    def push(self, snap):
        if self.undo_stack and self.undo_stack[-1].same(snap):
            return
        self.undo_stack.append(snap)
        if len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def can_undo(self):
        return bool(self.undo_stack)

    def can_redo(self):
        return bool(self.redo_stack)

    def undo(self, current):
        if not self.undo_stack:
            return None
        s = self.undo_stack.pop()
        self.redo_stack.append(current)
        return s

    def redo(self, current):
        if not self.redo_stack:
            return None
        s = self.redo_stack.pop()
        self.undo_stack.append(current)
        return s
