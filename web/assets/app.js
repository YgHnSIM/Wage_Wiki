(function () {
  "use strict";

  const TYPE_ORDER = ["law", "case", "interpretation", "fact_pattern", "discussion", "guide", "rule", "concept", "history"];
  const SORT_MODES = new Set(["latest", "oldest", "title", "type"]);
  const ARCHIVE_SORT_MODES = new Set(["latest", "oldest", "title"]);
  const ARCHIVE_SORT_LABELS = {
    latest: "최신 적용일순",
    oldest: "오래된 적용일순",
    title: "가나다순",
  };

  function initDocumentMeta() {
    const details = Array.from(document.querySelectorAll(".document-meta__more"));
    if (!details.length) return;
    const mobile = window.matchMedia("(max-width: 760px)");
    const sync = () => details.forEach((item) => {
      item.open = !mobile.matches;
    });
    sync();
    mobile.addEventListener("change", sync);
  }

  function initDocumentIndex() {
    const links = Array.from(document.querySelectorAll('.document-index a[href^="#"]'));
    if (!links.length) return;
    const pairs = links
      .map((link) => ({ link, heading: document.getElementById(decodeURIComponent(link.hash.slice(1))) }))
      .filter((item) => item.heading);
    if (!pairs.length) return;

    let scheduled = false;
    function update() {
      scheduled = false;
      let current = pairs[0];
      pairs.forEach((item) => {
        if (item.heading.getBoundingClientRect().top <= 140) current = item;
      });
      pairs.forEach((item) => {
        if (item === current) item.link.setAttribute("aria-current", "location");
        else item.link.removeAttribute("aria-current");
      });
    }
    window.addEventListener("scroll", () => {
      if (!scheduled) {
        scheduled = true;
        window.requestAnimationFrame(update);
      }
    }, { passive: true });
    update();
  }

  function initTypeArchive() {
    const listing = document.querySelector(".type-archive__listing[data-archive-sort]");
    if (!listing) return;

    const results = document.getElementById("archive-results");
    const sortSelect = document.getElementById("archive-sort");
    const status = document.getElementById("archive-sort-status");
    const announcer = document.getElementById("archive-sort-announcer");
    if (!(results instanceof HTMLElement) || !(sortSelect instanceof HTMLSelectElement) || !(status instanceof HTMLElement)) return;

    const cards = Array.from(results.querySelectorAll(":scope > .archive-card"));
    if (!cards.length) return;

    sortSelect.setAttribute("aria-controls", results.id);
    const initialOrder = new Map(cards.map((card, index) => [card, index]));

    function normalizedSort(value) {
      return ARCHIVE_SORT_MODES.has(value) ? value : "latest";
    }

    function compareTitles(left, right) {
      const difference = (left.dataset.sortTitle || "").localeCompare(right.dataset.sortTitle || "", "ko-KR");
      return difference || initialOrder.get(left) - initialOrder.get(right);
    }

    function orderedCards(sortMode) {
      // The generator has already serialized the no-JavaScript baseline as newest first.
      if (sortMode === "latest") return cards.slice();
      return cards.slice().sort((left, right) => {
        if (sortMode === "title") return compareTitles(left, right);

        const dateDifference = (left.dataset.sortDate || "").localeCompare(right.dataset.sortDate || "");
        if (dateDifference) return dateDifference;
        return compareTitles(left, right);
      });
    }

    function updateUrl(sortMode, historyMode) {
      const url = new URL(window.location.href);
      if (sortMode === "latest") url.searchParams.delete("sort");
      else url.searchParams.set("sort", sortMode);
      window.history[historyMode](null, "", `${url.pathname}${url.search}${url.hash}`);
    }

    function render(sortMode, { historyMode = "", announce = false } = {}) {
      const normalized = normalizedSort(sortMode);
      results.replaceChildren(...orderedCards(normalized));
      sortSelect.value = normalized;
      status.textContent = `${cards.length}개 문서`;
      if (announce && announcer instanceof HTMLElement) {
        announcer.textContent = "";
        window.requestAnimationFrame(() => {
          announcer.textContent = `${cards.length}개 문서 · ${ARCHIVE_SORT_LABELS[normalized]}`;
        });
      }
      if (historyMode) updateUrl(normalized, historyMode);
    }

    sortSelect.addEventListener("change", () => {
      render(sortSelect.value, { historyMode: "pushState", announce: true });
    });

    function applyLocationSort({ announce = false } = {}) {
      const requestedSort = new URLSearchParams(window.location.search).get("sort");
      const historyMode = requestedSort !== null && !ARCHIVE_SORT_MODES.has(requestedSort)
        ? "replaceState"
        : "";
      render(requestedSort, { historyMode, announce });
    }

    window.addEventListener("popstate", () => applyLocationSort({ announce: true }));
    applyLocationSort();
  }

  function initExplorer() {
    const explorer = document.querySelector(".explorer[data-index-url]");
    if (!explorer) return;

    const elements = {
      form: document.getElementById("search-form"),
      search: document.getElementById("search-input"),
      clearSearch: document.getElementById("clear-search"),
      results: document.getElementById("results"),
      statusText: document.getElementById("result-status"),
      empty: document.getElementById("empty-state"),
      emptyTitle: document.getElementById("empty-title"),
      emptyDescription: document.getElementById("empty-description"),
      pagination: document.getElementById("pagination"),
      pagePrev: document.getElementById("page-prev"),
      pageStatus: document.getElementById("page-status"),
      pageNext: document.getElementById("page-next"),
      typeButtons: Array.from(document.querySelectorAll(".type-filter")),
      sortSelect: document.getElementById("sort-select"),
      announcer: document.getElementById("results-announcer"),
    };

    if (!(elements.form instanceof HTMLFormElement)
      || !(elements.search instanceof HTMLInputElement)
      || !(elements.clearSearch instanceof HTMLButtonElement)
      || !(elements.results instanceof HTMLElement)
      || !(elements.statusText instanceof HTMLElement)
      || !(elements.empty instanceof HTMLElement)
      || !(elements.emptyTitle instanceof HTMLElement)
      || !(elements.emptyDescription instanceof HTMLElement)
      || !(elements.pagination instanceof HTMLElement)
      || !(elements.pagePrev instanceof HTMLButtonElement)
      || !(elements.pageStatus instanceof HTMLElement)
      || !(elements.pageNext instanceof HTMLButtonElement)
      || !(elements.sortSelect instanceof HTMLSelectElement)) return;

    const mobile = window.matchMedia("(max-width: 760px)");
    const staticFallbackCards = Array.from(elements.results.children);
    let pageSize = mobile.matches ? 6 : 10;
    let records = [];
    let filtered = [];
    let currentPage = 1;
    let activeType = "all";
    let activeSort = "latest";
    let query = "";
    let dataState = "loading";
    let announcementTimer = null;
    let announcementToken = 0;

    function isReady() {
      return dataState === "ready";
    }

    function setBusy(isBusy) {
      explorer.setAttribute("aria-busy", String(isBusy));
    }

    function setDataControlsDisabled(disabled) {
      const controls = [
        elements.search,
        elements.clearSearch,
        elements.sortSelect,
        elements.pagePrev,
        elements.pageNext,
        ...elements.typeButtons,
      ];
      controls.forEach((control) => {
        if (control instanceof HTMLButtonElement || control instanceof HTMLInputElement || control instanceof HTMLSelectElement) {
          control.disabled = disabled;
        }
      });
      if (disabled) elements.pagination.hidden = true;
    }

    function announce(text, { debounce = false } = {}) {
      if (!(elements.announcer instanceof HTMLElement)) return;
      if (announcementTimer !== null) window.clearTimeout(announcementTimer);
      const token = ++announcementToken;
      announcementTimer = window.setTimeout(() => {
        announcementTimer = null;
        if (token !== announcementToken) return;
        elements.announcer.textContent = "";
        window.requestAnimationFrame(() => {
          if (token === announcementToken) elements.announcer.textContent = text;
        });
      }, debounce ? 250 : 0);
    }

    function normalizeText(value) {
      return String(value || "")
        .normalize("NFKC")
        .toLocaleLowerCase("ko-KR")
        .replace(/[·ㆍ]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
    }

    function queryTerms() {
      return normalizeText(query).split(" ").filter(Boolean);
    }

    function relevance(record, terms) {
      if (!terms.length) return 0;
      const title = normalizeText(record.title);
      const aliases = normalizeText((record.aliases || []).join(" "));
      const caseNumber = normalizeText(record.caseNumber);
      const summary = normalizeText(record.summary);
      const searchText = normalizeText(record.searchText);
      if (!terms.every((term) => searchText.includes(term))) return -1;

      return terms.reduce((score, term) => {
        if (caseNumber === term) score += 100;
        else if (caseNumber.includes(term)) score += 70;
        if (title === term) score += 80;
        else if (title.startsWith(term)) score += 55;
        else if (title.includes(term)) score += 40;
        if (aliases.includes(term)) score += 30;
        if (summary.includes(term)) score += 12;
        if (searchText.includes(term)) score += 3;
        return score;
      }, 0);
    }

    function parsePage(value) {
      if (!/^[1-9]\d*$/.test(value || "")) return 1;
      const parsed = Number(value);
      return Number.isSafeInteger(parsed) ? parsed : 1;
    }

    function writeUrl({ mode = "replace", moveToResults = false } = {}) {
      const params = new URLSearchParams();
      if (query) params.set("q", query);
      if (activeType !== "all") params.set("type", activeType);
      if (activeSort !== "latest") params.set("sort", activeSort);
      if (currentPage > 1) params.set("page", String(currentPage));
      const encoded = params.toString();
      const hash = moveToResults ? "#explore" : window.location.hash;
      const next = window.location.pathname + (encoded ? `?${encoded}` : "") + hash;
      const current = window.location.pathname + window.location.search + window.location.hash;
      if (next === current) return;
      window.history[mode === "push" ? "pushState" : "replaceState"](null, "", next);
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
      if (activeType === "all") return "전체 문서";
      const activeButton = elements.typeButtons.find((button) => button.dataset.type === activeType);
      return activeButton ? activeButton.dataset.label : "전체 문서";
    }

    function setSort(value) {
      activeSort = SORT_MODES.has(value) ? value : "latest";
      elements.sortSelect.value = activeSort;
    }

    function badge(value, label, kind) {
      const node = document.createElement("span");
      node.className = `badge badge--${kind}`;
      node.dataset.value = value;
      node.textContent = label;
      return node;
    }

    function stableCardKey(record, headingTag) {
      const source = `${headingTag}|${record.number || ""}|${record.url || ""}`;
      let hash = 2166136261;
      for (let index = 0; index < source.length; index += 1) {
        hash ^= source.charCodeAt(index);
        hash = Math.imul(hash, 16777619);
      }
      return (hash >>> 0).toString(36);
    }

    function appendFolioNumber(container, rawNumber) {
      const number = String(rawNumber || "");
      const folio = document.createElement("span");
      folio.className = "folio-number";
      const separatorIndex = number.lastIndexOf("-");
      if (separatorIndex > 0 && separatorIndex < number.length - 1) {
        const prefix = document.createElement("span");
        prefix.className = "folio-prefix";
        prefix.textContent = number.slice(0, separatorIndex);
        const separator = document.createElement("span");
        separator.className = "folio-separator";
        separator.setAttribute("aria-hidden", "true");
        separator.textContent = "-";
        const sequence = document.createElement("span");
        sequence.className = "folio-sequence";
        sequence.textContent = number.slice(separatorIndex + 1);
        folio.append(prefix, separator, sequence);
      } else {
        const sequence = document.createElement("span");
        sequence.className = "folio-sequence";
        sequence.textContent = number;
        folio.append(sequence);
      }
      container.append(folio);
    }

    function renderCard(record, headingTag) {
      const article = document.createElement("article");
      article.className = "result-card";

      const key = stableCardKey(record, headingTag);
      const cardId = `result-card-${key}`;
      const numberId = `${cardId}-number`;
      const titleId = `${cardId}-title`;

      const link = document.createElement("a");
      link.className = "result-card__link";
      link.href = record.url;
      link.setAttribute("aria-labelledby", `${numberId} ${titleId}`);

      const accessibleNumber = document.createElement("span");
      accessibleNumber.className = "visually-hidden";
      accessibleNumber.id = numberId;
      accessibleNumber.textContent = `문서 번호 ${record.number}`;

      const number = document.createElement("span");
      number.className = "result-card__number";
      number.setAttribute("aria-hidden", "true");
      appendFolioNumber(number, record.number);

      const body = document.createElement("div");
      body.className = "result-card__body";

      const heading = document.createElement(headingTag);
      heading.id = titleId;
      heading.textContent = record.title;

      const summary = document.createElement("p");
      summary.textContent = record.summary;

      const metaRail = document.createElement("aside");
      metaRail.className = "result-card__meta-rail";

      const details = document.createElement("div");
      details.className = "meta-rail__details";
      const meta = document.createElement("div");
      meta.className = "result-card__meta";
      const type = document.createElement("span");
      type.textContent = record.typeLabel;
      const date = document.createElement("span");
      date.textContent = `${record.dateLabel} ${record.dateDisplay}`;
      meta.append(type, date);
      details.append(meta);

      const badges = document.createElement("div");
      badges.className = "badges";
      badges.append(
        badge(record.status, record.statusLabel, "editorial"),
        badge(record.legalStatus, record.legalStatusLabel, "legal")
      );

      body.append(heading, summary);
      metaRail.append(details, badges);
      link.append(accessibleNumber, number, body, metaRail);
      article.append(link);
      return article;
    }

    function selectRecords() {
      const terms = queryTerms();
      const matches = records
        .filter((record) => activeType === "all" || record.type === activeType)
        .map((record) => ({ record, score: relevance(record, terms) }))
        .filter((item) => item.score >= 0);

      matches.sort((left, right) => {
        if (activeSort === "oldest") {
          const dateDifference = left.record.sortDate.localeCompare(right.record.sortDate);
          if (dateDifference) return dateDifference;
        } else if (activeSort === "title") {
          const titleDifference = left.record.title.localeCompare(right.record.title, "ko-KR");
          if (titleDifference) return titleDifference;
        } else if (activeSort === "type") {
          const typeDifference = TYPE_ORDER.indexOf(left.record.type) - TYPE_ORDER.indexOf(right.record.type);
          if (typeDifference) return typeDifference;
          const titleDifference = left.record.title.localeCompare(right.record.title, "ko-KR");
          if (titleDifference) return titleDifference;
        } else {
          const dateDifference = right.record.sortDate.localeCompare(left.record.sortDate);
          if (dateDifference) return dateDifference;
        }
        return left.record.title.localeCompare(right.record.title, "ko-KR");
      });
      return matches.map((item) => item.record);
    }

    function renderSearchGroups(items, fragment) {
      TYPE_ORDER.forEach((type) => {
        const groupItems = items.filter((record) => record.type === type);
        if (!groupItems.length) return;
        const section = document.createElement("section");
        section.className = "result-group";
        const heading = document.createElement("h3");
        heading.id = `result-group-${type}`;
        heading.textContent = `${groupItems[0].typeLabel} ${groupItems.length}`;
        section.setAttribute("aria-labelledby", heading.id);
        const list = document.createElement("div");
        list.className = "result-group__items";
        groupItems.forEach((record) => list.append(renderCard(record, "h4")));
        section.append(heading, list);
        fragment.append(section);
      });
    }

    function resultStatusText(start, shown) {
      const queryLabel = query ? `“${query}” 검색 · ` : "";
      const shownLabel = filtered.length ? ` · ${start + 1}–${shown}개 표시` : "";
      return `${queryLabel}${activeTypeLabel()} ${filtered.length}개${shownLabel}`;
    }

    function render({ historyMode = "replace", moveToResults = false, announcement = "none" } = {}) {
      if (!isReady()) return;
      filtered = selectRecords();
      const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
      currentPage = Math.min(Math.max(currentPage, 1), totalPages);
      const start = (currentPage - 1) * pageSize;
      const shownRecords = filtered.slice(start, start + pageSize);
      elements.results.replaceChildren();
      const fragment = document.createDocumentFragment();
      if (query) renderSearchGroups(shownRecords, fragment);
      else shownRecords.forEach((record) => fragment.append(renderCard(record, "h3")));
      elements.results.append(fragment);

      const shown = start + shownRecords.length;
      const statusText = resultStatusText(start, shown);
      elements.statusText.textContent = statusText;
      elements.empty.hidden = filtered.length !== 0;
      elements.emptyTitle.textContent = query ? "검색 결과가 없습니다." : "선택한 유형에 문서가 없습니다.";
      elements.emptyDescription.textContent = query ? "검색어를 바꾸거나 다른 문서 유형을 선택해 보세요." : "다른 문서 유형을 선택해 보세요.";
      const hasMultiplePages = filtered.length > pageSize;
      elements.pagination.hidden = !hasMultiplePages;
      elements.pagePrev.disabled = currentPage === 1;
      elements.pageNext.disabled = currentPage === totalPages;
      elements.pageStatus.textContent = hasMultiplePages ? `${currentPage} / ${totalPages} 페이지` : "";
      elements.clearSearch.hidden = !query;
      writeUrl({ mode: historyMode, moveToResults });
      if (announcement === "immediate") announce(statusText);
      if (announcement === "debounced") announce(statusText, { debounce: true });
    }

    function refresh({ moveToResults = true, announcement = "immediate" } = {}) {
      if (!isReady()) return;
      currentPage = 1;
      render({ moveToResults, announcement });
    }

    function applyParams() {
      const params = new URLSearchParams(window.location.search);
      query = (params.get("q") || "").trim();
      elements.search.value = query;
      setType(params.get("type") || "all");
      setSort(params.get("sort") || "latest");
      currentPage = parsePage(params.get("page"));
      elements.clearSearch.hidden = !query;
    }

    elements.typeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (!isReady()) return;
        setType(button.dataset.type);
        refresh();
      });
    });
    elements.sortSelect.addEventListener("change", () => {
      if (!isReady()) return;
      setSort(elements.sortSelect.value);
      refresh();
    });
    elements.search.addEventListener("input", () => {
      if (!isReady()) return;
      query = elements.search.value.trim();
      refresh({ announcement: "debounced" });
    });
    elements.form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!isReady()) return;
      query = elements.search.value.trim();
      refresh();
    });
    elements.clearSearch.addEventListener("click", () => {
      if (!isReady()) return;
      elements.search.value = "";
      query = "";
      refresh();
      elements.search.focus();
    });
    function changePage(direction) {
      if (!isReady()) return;
      currentPage += direction;
      render({ historyMode: "push", moveToResults: true });
      window.requestAnimationFrame(() => {
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        elements.results.scrollIntoView({ block: "start", behavior: reducedMotion ? "auto" : "smooth" });
        elements.pageStatus.focus({ preventScroll: true });
      });
    }

    elements.pagePrev.addEventListener("click", () => {
      if (!elements.pagePrev.disabled) changePage(-1);
    });
    elements.pageNext.addEventListener("click", () => {
      if (!elements.pageNext.disabled) changePage(1);
    });
    mobile.addEventListener("change", () => {
      if (!isReady()) return;
      const previousPageSize = pageSize;
      const firstOffset = (currentPage - 1) * previousPageSize;
      pageSize = mobile.matches ? 6 : 10;
      currentPage = Math.floor(firstOffset / pageSize) + 1;
      render();
    });
    window.addEventListener("popstate", () => {
      if (!isReady()) return;
      applyParams();
      render({ announcement: "immediate" });
    });
    document.addEventListener("keydown", (event) => {
      if (!isReady() || elements.search.disabled) return;
      const editable = event.target instanceof HTMLElement && event.target.matches("input, textarea, select, [contenteditable=true]");
      const shortcut = (event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "k";
      if ((!editable && event.key === "/") || shortcut) {
        event.preventDefault();
        elements.search.focus();
        elements.search.select();
      }
    });

    applyParams();
    setBusy(true);
    setDataControlsDisabled(true);
    elements.statusText.textContent = "문서 데이터를 불러오는 중입니다.";
    fetch(explorer.dataset.indexUrl, { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data) => {
        if (!Array.isArray(data)) throw new Error("문서 데이터 형식이 올바르지 않습니다.");
        records = data;
        dataState = "ready";
        setBusy(false);
        setDataControlsDisabled(false);
        // The location may have changed while the index was loading.
        applyParams();
        render();
      })
      .catch(() => {
        dataState = "failed";
        setBusy(false);
        setDataControlsDisabled(true);
        if (staticFallbackCards.length) elements.results.replaceChildren(...staticFallbackCards);
        elements.statusText.textContent = "문서 데이터를 불러오지 못해 최신 문서 일부만 표시합니다.";
        elements.pagination.hidden = true;
        elements.pageStatus.textContent = "";
        elements.empty.hidden = true;
        announce("문서 데이터를 불러오지 못해 최신 문서 일부만 표시합니다.");
      });
  }

  initDocumentMeta();
  initDocumentIndex();
  initTypeArchive();
  initExplorer();
})();
