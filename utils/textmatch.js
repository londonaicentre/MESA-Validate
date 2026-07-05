/* textmatch.js - shared text matching for jump-to-source (packet + Streamlit pane) */
(function (global) {
  "use strict";

  function isExcerptField(fieldName, value) {
    if (typeof value !== "string" || value.trim().length === 0) return false;
    if (/_desc$|_name_desc$|_summary$/.test(fieldName)) return true;
    return value.trim().length >= 12;
  }

  function exactRanges(docText, query) {
    var ranges = [];
    var hay = docText.toLowerCase();
    var needle = query.toLowerCase().trim();
    if (!needle) return ranges;
    var from = 0, idx;
    while ((idx = hay.indexOf(needle, from)) !== -1) {
      ranges.push({ start: idx, end: idx + needle.length });
      from = idx + needle.length;
    }
    return ranges;
  }

  /* Collapse whitespace runs but remember original offsets. */
  function normalizedRanges(docText, query) {
    var chars = [], map = [];
    var prevSpace = false;
    for (var i = 0; i < docText.length; i++) {
      var ch = docText[i];
      if (/\s/.test(ch)) {
        if (!prevSpace) { chars.push(" "); map.push(i); }
        prevSpace = true;
      } else {
        chars.push(ch.toLowerCase()); map.push(i);
        prevSpace = false;
      }
    }
    var normDoc = chars.join("");
    var normQuery = query.toLowerCase().trim().replace(/\s+/g, " ");
    if (!normQuery) return [];
    var ranges = [], from = 0, idx;
    while ((idx = normDoc.indexOf(normQuery, from)) !== -1) {
      ranges.push({ start: map[idx], end: map[idx + normQuery.length - 1] + 1 });
      from = idx + normQuery.length;
    }
    return ranges;
  }

  function tokenize(text) {
    var tokens = [], re = /[a-z0-9]+/gi, m;
    while ((m = re.exec(text)) !== null) {
      tokens.push({ text: m[0].toLowerCase(), start: m.index, end: m.index + m[0].length });
    }
    return tokens;
  }

  /* Best window of doc tokens covering >=60% of query tokens. */
  function fuzzyRange(docText, query) {
    var queryTokens = tokenize(query).map(function (t) { return t.text; });
    if (queryTokens.length === 0) return null;
    var docTokens = tokenize(docText);
    if (docTokens.length === 0) return null;
    var windowSize = Math.max(queryTokens.length, 3);
    var best = null;
    for (var i = 0; i < docTokens.length; i++) {
      var window = docTokens.slice(i, i + windowSize);
      var windowSet = {};
      window.forEach(function (t) { windowSet[t.text] = true; });
      var hits = 0;
      queryTokens.forEach(function (q) { if (windowSet[q]) hits++; });
      if (best === null || hits > best.hits) {
        best = { hits: hits, start: window[0].start, end: window[window.length - 1].end };
      }
    }
    if (!best || best.hits < Math.ceil(queryTokens.length * 0.6)) return null;
    return { start: best.start, end: best.end };
  }

  function findMatches(docText, query) {
    var ranges = exactRanges(docText, query);
    if (ranges.length) return { strategy: "exact", ranges: ranges };
    ranges = normalizedRanges(docText, query);
    if (ranges.length) return { strategy: "normalized", ranges: ranges };
    var fuzzy = fuzzyRange(docText, query);
    if (fuzzy) return { strategy: "fuzzy", ranges: [fuzzy] };
    return { strategy: null, ranges: [] };
  }

  global.TextMatch = {
    findMatches: findMatches,
    isExcerptField: isExcerptField,
  };
})(typeof window !== "undefined" ? window : globalThis);
