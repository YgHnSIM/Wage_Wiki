(function () {
  "use strict";

  const searchCore = window.WageWikiSearch;
  if (!searchCore) throw new Error("Wage Wiki search core failed to load.");
  const { matchesQuery, queryParts, score } = searchCore;
  const explorer = document.querySelector(".explorer[data-index-url]");
  if (!explorer) return;

  const elements = {
    form: document.getElementById("search-form"),
    search: document.getElementById("search-input"),
    clearSearch: document.getElementById("clear-search"),
    status: document.getElementById("status-filter"),
    legal: document.getElementById("legal-filter"),
    date: document.getElementById("date-filter"),
    sort: document.getElementById("sort-filter"),
    effective: document.getElementById("effective-filter"),
    reset: document.getElementById("reset-filters"),
    showAll: document.getElementById("show-all"),
    results: document.getElementById("results"),
    statusText: document.getElementById("result-status"),
    empty: document.getElementById("empty-state"),
    loadMore: document.getElementById("load-more"),
    typeButtons: Array.from(document.querySelectorAll(".type-filter")),
  };

  const defaultDate = explorer.dataset.defaultDate;
  const pageSize = 18;
  let records = [];
  let filtered = [];
  let visible = pageSize;
  let activeType = "all";

  function currentState() {
    return {
      q: elements.search.value.trim(),
      type: activeType,
      status: elements.status.value,
      legal: elements.legal.value,
      date: elements.date.value || defaultDate,
      sort: elements.sort.value,
      effective: elements.effective.checked,
    };
  }

  function isEffective(record, date) {
    return record.effectiveFrom <= date && date <= record.effectiveTo;
  }

  function sortRecords(items, state, parts) {
    return items.sort((left, right) => {
      if (state.sort === "relevance" && parts.length) {
        const relevance = score(right, parts) - score(left, parts);
        if (relevance) return relevance;
      }
      if (state.sort === "title") {
        return left.title.localeCompare(right.title, "ko");
      }
      if (state.sort === "authority") {
        const leftAuthority = Number(left.authorityLevel || 99);
        const rightAuthority = Number(right.authorityLevel || 99);
        if (leftAuthority !== rightAuthority) return leftAuthority - rightAuthority;
      }
      return right.sortDate.localeCompare(left.sortDate) || left.title.localeCompare(right.title, "ko");
    });
  }

  function updateUrl(state) {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.type !== "all") params.set("type", state.type);
    if (state.status !== "verified") params.set("status", state.status);
    if (state.legal !== "current") params.set("legal", state.legal);
    if (state.date !== defaultDate) params.set("asof", state.date);
    if (state.sort !== "date") params.set("sort", state.sort);
    if (!state.effective) params.set("effective", "0");
    const query = params.toString();
    const anchor = query || window.location.hash === "#explore" ? "#explore" : "";
    const next = window.location.pathname + (query ? `?${query}` : "") + anchor;
    window.history.replaceState(null, "", next);
  }

  function setType(value) {
    activeType = elements.typeButtons.some((button) => button.dataset.type === value) ? value : "all";
    elements.typeButtons.forEach((button) => {
      const active = button.dataset.type === activeType;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function appendHighlighted(target, text, query) {
    const parts = String(query || "")
      .trim()
      .split(/\s+/)
      .filter((part) => part.length > 1)
      .sort((left, right) => right.length - left.length);
    if (!parts.length) {
      target.textContent = text;
      return;
    }
    const escaped = parts.map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const expression = new RegExp(`(${escaped.join("|")})`, "gi");
    let cursor = 0;
    for (const match of text.matchAll(expression)) {
      target.append(document.createTextNode(text.slice(cursor, match.index)));
      const mark = document.createElement("mark");
      mark.textContent = match[0];
      target.append(mark);
      cursor = match.index + match[0].length;
    }
    target.append(document.createTextNode(text.slice(cursor)));
  }

  function badge(value, label, kind) {
    const node = document.createElement("span");
    node.className = `badge badge--${kind}`;
    node.dataset.value = value;
    node.textContent = label;
    return node;
  }

  function renderCard(record, query) {
    const article = document.createElement("article");
    article.className = "result-card";

    const number = document.createElement("div");
    number.className = "result-card__number";
    number.setAttribute("aria-hidden", "true");
    number.textContent = record.number;

    const body = document.createElement("div");
    body.className = "result-card__body";

    const meta = document.createElement("div");
    meta.className = "result-card__meta";
    const type = document.createElement("span");
    type.textContent = record.typeLabel;
    const date = document.createElement("span");
    date.textContent = `${record.dateLabel} ${record.dateDisplay}`;
    meta.append(type, date);

    const heading = document.createElement("h3");
    const link = document.createElement("a");
    link.href = record.url;
    appendHighlighted(link, record.title, query);
    heading.append(link);

    const summary = document.createElement("p");
    appendHighlighted(summary, record.summary, query);

    const badges = document.createElement("div");
    badges.className = "badges";
    badges.append(
      badge(record.status, record.statusLabel, "editorial"),
      badge(record.legalStatus, record.legalStatusLabel, "legal")
    );

    body.append(meta, heading, summary, badges);
    article.append(number, body);
    return article;
  }

  function render() {
    const state = currentState();
    const parts = queryParts(state.q);
    filtered = records.filter((record) => {
      if (state.type !== "all" && record.type !== state.type) return false;
      if (state.status !== "all" && record.status !== state.status) return false;
      if (state.legal !== "all" && record.legalStatus !== state.legal) return false;
      if (state.effective && !isEffective(record, state.date)) return false;
      return matchesQuery(record, state.q);
    });
    sortRecords(filtered, state, parts);

    elements.results.replaceChildren();
    const fragment = document.createDocumentFragment();
    filtered.slice(0, visible).forEach((record) => fragment.append(renderCard(record, state.q)));
    elements.results.append(fragment);

    const shown = Math.min(filtered.length, visible);
    const prefix = state.q ? `“${state.q}” 검색 결과` : "조건에 맞는 문서";
    elements.statusText.textContent = `${prefix} ${filtered.length}개${filtered.length > shown ? ` · ${shown}개 표시` : ""}`;
    elements.empty.hidden = filtered.length !== 0;
    elements.loadMore.hidden = shown >= filtered.length;
    if (!elements.loadMore.hidden) {
      elements.loadMore.textContent = `더 보기 · ${filtered.length - shown}개 남음`;
    }
    updateUrl(state);
  }

  function refresh() {
    visible = pageSize;
    render();
  }

  function applyParams() {
    const params = new URLSearchParams(window.location.search);
    elements.search.value = params.get("q") || "";
    setType(params.get("type") || "all");
    elements.status.value = params.get("status") || "verified";
    if (!elements.status.value) elements.status.value = "verified";
    const selectedDate = params.get("asof") || defaultDate;
    elements.legal.value = params.get("legal") || (selectedDate !== defaultDate ? "all" : "current");
    if (!elements.legal.value) elements.legal.value = "current";
    elements.date.value = selectedDate;
    elements.sort.value = params.get("sort") || "date";
    if (!elements.sort.value) elements.sort.value = "date";
    const effectiveParam = params.get("effective");
    elements.effective.checked = effectiveParam !== "0" && !(elements.legal.value === "future" && effectiveParam === null);
  }

  function resetDefaults() {
    elements.search.value = "";
    elements.status.value = "verified";
    elements.legal.value = "current";
    elements.date.value = defaultDate;
    elements.sort.value = "date";
    elements.effective.checked = true;
    setType("all");
    refresh();
  }

  elements.form.addEventListener("submit", (event) => event.preventDefault());
  elements.search.addEventListener("input", refresh);
  elements.clearSearch.addEventListener("click", () => {
    elements.search.value = "";
    elements.search.focus();
    refresh();
  });
  [elements.status, elements.sort, elements.effective].forEach((control) => {
    control.addEventListener("change", refresh);
  });
  elements.legal.addEventListener("change", () => {
    if (elements.legal.value === "future") {
      elements.effective.checked = false;
    }
    refresh();
  });
  elements.date.addEventListener("change", () => {
    if (elements.date.value && elements.date.value !== defaultDate && elements.legal.value === "current") {
      elements.legal.value = "all";
    }
    refresh();
  });
  elements.typeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setType(button.dataset.type);
      refresh();
    });
  });
  elements.reset.addEventListener("click", resetDefaults);
  elements.showAll.addEventListener("click", () => {
    elements.status.value = "all";
    elements.legal.value = "all";
    elements.effective.checked = false;
    setType("all");
    refresh();
  });
  elements.loadMore.addEventListener("click", () => {
    visible += pageSize;
    render();
  });
  window.addEventListener("popstate", () => {
    applyParams();
    refresh();
  });
  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const editing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
    if (event.key === "/" && !editing) {
      event.preventDefault();
      elements.search.focus();
    }
  });

  applyParams();
  fetch(explorer.dataset.indexUrl, { credentials: "same-origin" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((data) => {
      if (!Array.isArray(data)) throw new Error("검색 인덱스 형식이 올바르지 않습니다.");
      records = data;
      refresh();
    })
    .catch(() => {
      elements.statusText.textContent = "검색 인덱스를 불러오지 못했습니다.";
      elements.loadMore.hidden = true;
    });
})();
