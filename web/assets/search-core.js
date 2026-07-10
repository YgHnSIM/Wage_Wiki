(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.WageWikiSearch = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function normalise(value) {
    return String(value || "")
      .normalize("NFKC")
      .toLocaleLowerCase("ko-KR")
      .replace(/ㆍ/g, "·")
      .replace(/[\s·.,:;()\[\]{}'"/_-]+/g, "");
  }

  function queryParts(value) {
    const raw = String(value || "").trim();
    if (!raw) return [];
    const combined = normalise(raw);
    const tokens = raw.split(/\s+/).map(normalise).filter(Boolean);
    return Array.from(new Set([combined, ...tokens])).filter(Boolean);
  }

  function matchesQuery(record, value) {
    const raw = String(value || "").trim();
    if (!raw) return true;
    const compact = normalise(raw);
    const tokens = raw.split(/\s+/).map(normalise).filter(Boolean);
    return record.searchNormalised.includes(compact) || tokens.every((token) => record.searchNormalised.includes(token));
  }

  function score(record, parts) {
    if (!parts.length) return 0;
    const title = normalise(record.title);
    const id = normalise(record.id);
    const summary = normalise(record.summary);
    return parts.reduce((total, part) => {
      if (title === part) total += 240;
      else if (title.includes(part)) total += 120;
      if (id.includes(part)) total += 90;
      if (summary.includes(part)) total += 35;
      if (record.searchNormalised.includes(part)) total += 10;
      return total;
    }, 0);
  }

  return { normalise, queryParts, matchesQuery, score };
});
