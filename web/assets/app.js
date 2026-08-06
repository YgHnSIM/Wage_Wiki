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

  function initDecisionTreeWizards() {
    const tabs = Array.from(document.querySelectorAll(".tool-tab"));
    const panels = Array.from(document.querySelectorAll(".wizard-panel"));
    if (!tabs.length || !panels.length) return;

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        tabs.forEach((t) => {
          t.classList.remove("active");
          t.setAttribute("aria-selected", "false");
        });
        panels.forEach((p) => (p.style.display = "none"));

        tab.classList.add("active");
        tab.setAttribute("aria-selected", "true");
        const targetId = tab.getAttribute("aria-controls");
        const targetPanel = document.getElementById(targetId);
        if (targetPanel) targetPanel.style.display = "block";
      });
    });

    const RESULT_TEMPLATES = {
      "pos-ordinary-wage": {
        badge: "badge--success",
        badgeText: "✅ 통상임금 성립",
        title: "통상임금 3대 요건 (정기성·일률성·사전확정성) 충족",
        desc: "해당 수당은 근로기준법 시행령 제6조 및 2024년 대법원 전원합의체 판례(2020다247190)에 의거 통상임금에 해당합니다. 연장·야간·휴일근로 가산수당 및 해고예고수당, 연차휴가 미사용수당 산정의 기초임금에 합산되어야 합니다.",
        linkText: "관련 대법원 전원합의체 판례 보기",
        linkUrl: "../entities/case-2020da247190-7521e102/"
      },
      "neg-regularity": {
        badge: "badge--warning",
        badgeText: "❌ 통상임금 제외 (정기성 부재)",
        title: "정기성 요건 미충족",
        desc: "지급 주기가 불규칙하거나 임시·우발적으로 지급되는 금품은 정기성이 인정되지 않아 통상임금에서 제외됩니다.",
        linkText: "관련 통상임금 판단 규칙 보기",
        linkUrl: "../entities/rule-ru34-fixedness-excluded-2024-5d554a93/"
      },
      "neg-uniformity": {
        badge: "badge--warning",
        badgeText: "❌ 통상임금 제외 (일률성 부재)",
        title: "일률성 요건 미충족",
        desc: "일정한 조건이나 자격을 갖춘 모든 근로자가 아닌, 특정 개별 근로자에게만 임의로 지급되는 금품은 일률성이 부정됩니다.",
        linkText: "관련 통상임금 판단 규칙 보기",
        linkUrl: "../entities/rule-ru34-fixedness-excluded-2024-5d554a93/"
      },
      "neg-fixedness": {
        badge: "badge--warning",
        badgeText: "❌ 통상임금 제외 (사전확정성 결여)",
        title: "사전확정성/대가성 요건 미충족",
        desc: "실제 개인 영업 성과 달성이나 조건에 따라 변동 지급되는 불확정 성과급은 소정근로 대가성이 부정되어 통상임금에서 제외됩니다.",
        linkText: "관련 판단 규칙 보기",
        linkUrl: "../entities/rule-ru34-fixedness-excluded-2024-5d554a93/"
      },
      "comp-invalid": {
        badge: "badge--danger",
        badgeText: "🚨 포괄임금약정 절대 무효 (가산수당 차액 청구 대상)",
        title: "포괄임금약정 무효 및 실근로시간 기반 수당 재산정 대상",
        desc: "PC Off 시스템 등 근로시간 집계가 가능한 상황에서 일반 사무직·IT근로자에게 체결된 포괄임금약정은 근로기준법 제43조 및 제56조 위반으로 무효입니다. 기존 포괄수당 외에 실근로시간에 상응하는 150% 가산수당 차액을 지체 없이 청구할 수 있습니다.",
        linkText: "관련 포괄임금 무효 판단 규칙 보기",
        linkUrl: "../entities/rule-invalid-comprehensive-wage-recalculation-5e580e60/"
      },
      "comp-valid-possible": {
        badge: "badge--info",
        badgeText: "⚠️ 포괄임금 수용 가능성 예외 검토",
        title: "근로시간 산정 곤란성 검토 필요",
        desc: "근로시간을 객관적으로 집계하기 극히 어려운 엄격한 사정이 증명되는 경우 예외적으로 포괄임금약정이 유효할 수 있습니다.",
        linkText: "관련 임금지급법령 보기",
        linkUrl: "../entities/law-lsa-article-43-wage-payment-principles-85e6833b/"
      },
      "comp-valid-exception": {
        badge: "badge--info",
        badgeText: "⚠️ 사업장 밖 근로 등 특수직종 예외",
        title: "사업장 밖 근로시간 간주제 적용 가능성",
        desc: "외근 업무, 사업장 밖 근로 등 근로시간 관리가 어려운 경우 포괄임금 또는 간주근로시간제가 인정될 수 있습니다.",
        linkText: "관련 판단 규칙 보기",
        linkUrl: "../entities/rule-invalid-comprehensive-wage-recalculation-5e580e60/"
      },
      "u5-full-apply": {
        badge: "badge--success",
        badgeText: "✅ 근로기준법 전면 적용 사업장",
        title: "상시 5인 이상 사업장",
        desc: "가산수당(150%), 연차유급휴가, 부당해고 제한(제23조) 등 근로기준법 모든 조항이 전면 적용됩니다.",
        linkText: "관련 근로기준법 제11조 보기",
        linkUrl: "../entities/law-lsa-article-11-scope-e67d4e30/"
      },
      "u5-excluded-items": {
        badge: "badge--warning",
        badgeText: "⚠️ 5인 미만 사업장 적용 배제 조항",
        title: "가산수당·연차휴가·부당해고 구제 적용 제외",
        desc: "상시 5인 미만 사업장은 근로기준법 제11조 제2항에 따라 제56조 가산수당(50% 가산), 제60조 연차휴가, 제23조 부당해고 노동위원회 구제신청이 적용 제외됩니다. (단, 근무한 시급 100% 자체는 지급받아야 함)",
        linkText: "관련 5인 미만 적용 규칙 보기",
        linkUrl: "../entities/rule-under-5-employees-lsa-exclusion-cd044cf4/"
      },
      "u5-mandatory-items": {
        badge: "badge--success",
        badgeText: "✅ 5인 미만 사업장 필수 적용 조항",
        title: "주휴수당·최저임금·퇴직금·해고예고 필수 적용",
        desc: "상시 5인 미만 사업장이라도 주휴수당(제55조), 최저임금법, 법정 퇴직금, 30일 전 해고예고수당(제26조)은 100% 강행 적용되므로 미지급 시 임금체불에 해당합니다.",
        linkText: "관련 주휴수당 규칙 보기",
        linkUrl: "../entities/rule-weekly-holiday-allowance-short-term-09e4f58c/"
      }
    };

    document.querySelectorAll(".wizard-card").forEach((card) => {
      const stepBadgeNum = card.querySelector(".current-step-num");
      const steps = Array.from(card.querySelectorAll(".wizard-step"));
      const resultContainer = card.querySelector(".wizard-result");
      const resultBox = card.querySelector(".result-box");

      function showStep(num) {
        steps.forEach((s) => {
          if (parseInt(s.dataset.step, 10) === num) {
            s.style.display = "block";
            s.classList.add("active");
          } else {
            s.style.display = "none";
            s.classList.remove("active");
          }
        });
        if (resultContainer) resultContainer.style.display = "none";
        if (stepBadgeNum) stepBadgeNum.textContent = num;
      }

      function showResult(key) {
        steps.forEach((s) => (s.style.display = "none"));
        const data = RESULT_TEMPLATES[key];
        if (data && resultBox && resultContainer) {
          resultBox.innerHTML = `
            <div class="result-badge-wrap"><span class="badge ${data.badge}">${data.badgeText}</span></div>
            <h4 class="result-title">${data.title}</h4>
            <p class="result-desc">${data.desc}</p>
            ${data.linkUrl ? `<a href="${data.linkUrl}" class="text-link">${data.linkText} →</a>` : ""}
          `;
          resultContainer.style.display = "block";
        }
      }

      card.addEventListener("click", (e) => {
        const btn = e.target.closest("button");
        if (!btn) return;

        if (btn.dataset.next) {
          showStep(parseInt(btn.dataset.next, 10));
        } else if (btn.dataset.prev) {
          showStep(parseInt(btn.dataset.prev, 10));
        } else if (btn.dataset.result) {
          showResult(btn.dataset.result);
        } else if (btn.classList.contains("btn-reset")) {
          showStep(1);
        }
      });
    });
  }

  function initWageCalculators() {
    function fmt(val) {
      return Math.round(val).toLocaleString("ko-KR") + " 원";
    }

    const baseSalInput = document.getElementById("input-base-salary");
    const fixedAllowInput = document.getElementById("input-fixed-allowance");
    const monthlyHoursInput = document.getElementById("input-monthly-hours");

    function calcOrdinary() {
      if (!baseSalInput || !fixedAllowInput || !monthlyHoursInput) return;
      const base = parseFloat(baseSalInput.value) || 0;
      const fixed = parseFloat(fixedAllowInput.value) || 0;
      const hours = parseFloat(monthlyHoursInput.value) || 209;

      const monthlyWage = base + fixed;
      const hourlyRate = hours > 0 ? monthlyWage / hours : 0;
      const dailyRate = hourlyRate * 8;

      const resMonthly = document.getElementById("res-monthly-wage");
      const resHourly = document.getElementById("res-ordinary-hourly");
      const resDaily = document.getElementById("res-daily-ordinary");
      if (resMonthly) resMonthly.textContent = fmt(monthlyWage);
      if (resHourly) resHourly.textContent = fmt(hourlyRate);
      if (resDaily) resDaily.textContent = fmt(dailyRate);

      const overtimeRateInput = document.getElementById("input-hourly-rate");
      if (overtimeRateInput && document.activeElement !== overtimeRateInput) {
        overtimeRateInput.value = Math.round(hourlyRate);
        calcOvertime();
      }
    }

    const hourlyInput = document.getElementById("input-hourly-rate");
    const overtimeHoursInput = document.getElementById("input-overtime-hours");
    const nightHoursInput = document.getElementById("input-night-hours");
    const holidayHoursInput = document.getElementById("input-holiday-hours");

    function calcOvertime() {
      if (!hourlyInput || !overtimeHoursInput || !nightHoursInput || !holidayHoursInput) return;
      const h = parseFloat(hourlyInput.value) || 0;
      const ot = parseFloat(overtimeHoursInput.value) || 0;
      const nt = parseFloat(nightHoursInput.value) || 0;
      const ht = parseFloat(holidayHoursInput.value) || 0;

      const otPay = ot * h * 1.5;
      const ntPay = nt * h * 0.5;
      const htPay = ht * h * 1.5;
      const totalPay = otPay + ntPay + htPay;

      const resOt = document.getElementById("res-overtime-pay");
      const resNt = document.getElementById("res-night-pay");
      const resHt = document.getElementById("res-holiday-pay");
      const resTotal = document.getElementById("res-total-allowance");
      if (resOt) resOt.textContent = fmt(otPay);
      if (resNt) resNt.textContent = fmt(ntPay);
      if (resHt) resHt.textContent = fmt(htPay);
      if (resTotal) resTotal.textContent = fmt(totalPay);
    }

    const minBaseInput = document.getElementById("input-min-base");
    const minMealInput = document.getElementById("input-min-meal");
    const minBonusInput = document.getElementById("input-min-bonus");

    function calcMinWage() {
      if (!minBaseInput || !minMealInput || !minBonusInput) return;
      const base = parseFloat(minBaseInput.value) || 0;
      const meal = parseFloat(minMealInput.value) || 0;
      const bonus = parseFloat(minBonusInput.value) || 0;

      const totalComp = base + meal + bonus;
      const hourlyEq = totalComp / 209;
      const MIN_WAGE_2026_MONTHLY = 2096270;

      const resMinTot = document.getElementById("res-min-total");
      const resMinHr = document.getElementById("res-min-hourly");
      if (resMinTot) resMinTot.textContent = fmt(totalComp);
      if (resMinHr) resMinHr.textContent = fmt(hourlyEq);

      const statusBox = document.getElementById("res-min-status");
      if (statusBox) {
        const diff = totalComp - MIN_WAGE_2026_MONTHLY;
        if (diff >= 0) {
          statusBox.innerHTML = `
            <span class="badge badge--success">✅ 최저임금 준수</span>
            <p style="margin:4px 0 0 0;font-size:0.9em;color:var(--color-fg-muted);">기준액(월 2,096,270원) 대비 <strong>+${fmt(diff)}</strong> 초과 지급 중입니다.</p>
          `;
        } else {
          statusBox.innerHTML = `
            <span class="badge badge--danger">🚨 최저임금 미달 (임금체불)</span>
            <p style="margin:4px 0 0 0;font-size:0.9em;color:var(--color-fg-muted);">기준액(월 2,096,270원) 대비 <strong style="color:var(--color-danger);">${fmt(Math.abs(diff))} 미달</strong>되어 최저임금법 제6조 위반입니다.</p>
          `;
        }
      }
    }

    const wage3mInput = document.getElementById("input-3month-wage");
    const bonusAnnInput = document.getElementById("input-annual-bonus");
    const tenureInput = document.getElementById("input-tenure-days");
    const childcareCheck = document.getElementById("check-childcare-leave");

    function calcSeverance() {
      if (!wage3mInput || !bonusAnnInput || !tenureInput) return;
      const wage3m = parseFloat(wage3mInput.value) || 0;
      const bonusAnn = parseFloat(bonusAnnInput.value) || 0;
      const tenureDays = parseFloat(tenureInput.value) || 0;

      const dailyAvg = (wage3m + (bonusAnn * 0.25)) / 92;
      const totalSeverance = dailyAvg * 30 * (tenureDays / 365);

      const resDailyAvg = document.getElementById("res-daily-average");
      const resTotSev = document.getElementById("res-total-severance");
      if (resDailyAvg) resDailyAvg.textContent = fmt(dailyAvg);
      if (resTotSev) resTotSev.textContent = fmt(totalSeverance);
    }

    [baseSalInput, fixedAllowInput, monthlyHoursInput].forEach((el) => el && el.addEventListener("input", calcOrdinary));
    [hourlyInput, overtimeHoursInput, nightHoursInput, holidayHoursInput].forEach((el) => el && el.addEventListener("input", calcOvertime));
    [minBaseInput, minMealInput, minBonusInput].forEach((el) => el && el.addEventListener("input", calcMinWage));
    [wage3mInput, bonusAnnInput, tenureInput, childcareCheck].forEach((el) => el && el.addEventListener("input", calcSeverance));

    calcOrdinary();
    calcMinWage();
    calcSeverance();
  }

  initDocumentMeta();
  initDocumentIndex();
  initTypeArchive();
  initExplorer();
  initDecisionTreeWizards();
  initWageCalculators();
})();
