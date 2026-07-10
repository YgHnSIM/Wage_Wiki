(function () {
  "use strict";

  const explorer = document.querySelector(".explorer[data-index-url]");
  if (!explorer) return;

  const elements = {
    results: document.getElementById("results"),
    statusText: document.getElementById("result-status"),
    empty: document.getElementById("empty-state"),
    loadMore: document.getElementById("load-more"),
    typeButtons: Array.from(document.querySelectorAll(".type-filter")),
  };

  const pageSize = 18;
  let records = [];
  let filtered = [];
  let visible = pageSize;
  let activeType = "all";

  function sortRecords(items) {
    return items.sort((left, right) => right.sortDate.localeCompare(left.sortDate));
  }

  function updateUrl() {
    const params = new URLSearchParams();
    if (activeType !== "all") params.set("type", activeType);
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

  function activeTypeLabel() {
    const activeButton = elements.typeButtons.find((button) => button.dataset.type === activeType);
    return activeButton ? activeButton.dataset.label : "전체 문서";
  }

  function badge(value, label, kind) {
    const node = document.createElement("span");
    node.className = `badge badge--${kind}`;
    node.dataset.value = value;
    node.textContent = label;
    return node;
  }

  function renderCard(record) {
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
    link.textContent = record.title;
    heading.append(link);

    const summary = document.createElement("p");
    summary.textContent = record.summary;

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
    filtered = records.filter((record) => activeType === "all" || record.type === activeType);
    sortRecords(filtered);

    elements.results.replaceChildren();
    const fragment = document.createDocumentFragment();
    filtered.slice(0, visible).forEach((record) => fragment.append(renderCard(record)));
    elements.results.append(fragment);

    const shown = Math.min(filtered.length, visible);
    elements.statusText.textContent = `${activeTypeLabel()} ${filtered.length}개${filtered.length > shown ? ` · ${shown}개 표시` : ""}`;
    elements.empty.hidden = filtered.length !== 0;
    elements.loadMore.hidden = shown >= filtered.length;
    if (!elements.loadMore.hidden) {
      elements.loadMore.textContent = `더 보기 · ${filtered.length - shown}개 남음`;
    }
    updateUrl();
  }

  function refresh() {
    visible = pageSize;
    render();
  }

  function applyParams() {
    const params = new URLSearchParams(window.location.search);
    setType(params.get("type") || "all");
  }

  elements.typeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setType(button.dataset.type);
      refresh();
    });
  });
  elements.loadMore.addEventListener("click", () => {
    visible += pageSize;
    render();
  });
  window.addEventListener("popstate", () => {
    applyParams();
    refresh();
  });

  applyParams();
  fetch(explorer.dataset.indexUrl, { credentials: "same-origin" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((data) => {
      if (!Array.isArray(data)) throw new Error("문서 데이터 형식이 올바르지 않습니다.");
      records = data;
      refresh();
    })
    .catch(() => {
      elements.statusText.textContent = "문서 데이터를 불러오지 못했습니다.";
      elements.loadMore.hidden = true;
    });
})();
