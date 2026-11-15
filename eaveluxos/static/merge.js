/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   What a settings save changed, and putting just that on top of the latest
   settings (4.0.1). A screen builds the whole settings document from what
   it last saw; when another save lands first, sending the whole document
   would undo it (or be refused). diff() finds the parts this save changed
   (nested objects part by part; a list counts as one value) and apply()
   puts them on a copy of the latest. Plain logic, tested with Node.
   Works as a plain <script> (window.Merge) and as a Node module (tests). */
(function (root) {
  'use strict';

  const DELETED = { deleted: true };          // marks a part this save removed
  const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const copy = v => v === undefined ? undefined : JSON.parse(JSON.stringify(v));

  function diff(base, next, path = [], out = []) {
    for (const k of new Set([...Object.keys(base || {}), ...Object.keys(next || {})])) {
      if (!path.length && k === '_rev') continue;
      const a = base ? base[k] : undefined, b = next ? next[k] : undefined;
      if (isObj(a) && isObj(b)) diff(a, b, [...path, k], out);
      else if (JSON.stringify(a) !== JSON.stringify(b)) out.push([[...path, k], b === undefined ? DELETED : copy(b)]);
    }
    return out;
  }

  function apply(doc, changes) {
    for (const [path, v] of changes) {
      let o = doc;
      for (const k of path.slice(0, -1)) { if (!isObj(o[k])) o[k] = {}; o = o[k]; }
      const last = path[path.length - 1];
      if (v === DELETED) delete o[last]; else o[last] = copy(v);
    }
    return doc;
  }

  const api = { diff, apply, DELETED };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Merge = api;
})(typeof window !== 'undefined' ? window : globalThis);
