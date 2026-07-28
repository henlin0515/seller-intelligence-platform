/**
 * FastMoss Shop Search — standalone TikTok shop search and MTD ADG page.
 */
(function () {
  const API = {
    search: "/api/intelligence/v1/fastmoss-shop-search",
    detail: (shopId, params = "") =>
      `/api/intelligence/v1/fastmoss-shop-search/${encodeURIComponent(shopId)}${params}`,
  };
  const SEARCH_TIMEOUT_MS = 20000;
  const DETAIL_TIMEOUT_MS = 30000;
  const CACHE_TTL_MS = 30 * 60 * 1000;

  const contentEl = document.getElementById("siFastmossSearchContent");
  const metaEl = document.getElementById("siFastmossSearchMeta");

  const state = {
    initialized: false,
    loading: false,
    query: "",
    results: [],
    selected: null,
    error: "",
    searchCache: new Map(),
    detailCache: new Map(),
    inFlightSearch: null,
  };

  function fetchApi(path, options = {}) {
    const fn = window.SipApi?.fetch || fetch;
    return fn(path, { credentials: "same-origin", ...options });
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = String(text ?? "");
    return div.innerHTML;
  }

  function fmtNum(value, digits = 0) {
    if (value == null || value === "") return "N/A";
    const n = Number(value);
    if (!Number.isFinite(n)) return "N/A";
    return n.toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function fmtMoney(value, currency = "PHP", digits = 2) {
    if (value == null || value === "") return "N/A";
    const n = Number(value);
    if (!Number.isFinite(n)) return "N/A";
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency,
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(n);
    } catch {
      return `${currency} ${fmtNum(n, digits)}`;
    }
  }

  function cacheGet(map, key) {
    const row = map.get(key);
    if (!row) return null;
    if (Date.now() > row.expiresAt) {
      map.delete(key);
      return null;
    }
    return row.value;
  }

  function cacheSet(map, key, value, ttlMs = CACHE_TTL_MS) {
    map.set(key, { value, expiresAt: Date.now() + ttlMs });
    return value;
  }

  async function fetchJsonWithTimeout(path, { timeoutMs = 20000, ...options } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetchApi(path, { ...options, signal: controller.signal });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
      return data;
    } catch (err) {
      if (err.name === "AbortError") {
        throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  function currentErrorMessage(err) {
    const text = String(err?.message || err || "");
    if (/429|rate/i.test(text)) {
      return "FastMoss request limit reached. Please retry later.";
    }
    return text || "Could not load FastMoss shop data.";
  }

  async function search(query) {
    const q = String(query || "").trim();
    state.query = q;
    state.error = "";
    state.selected = null;
    if (!q) {
      state.results = [];
      render();
      return;
    }
    const cached = cacheGet(state.searchCache, q.toLowerCase());
    if (cached) {
      state.results = cached.results || [];
      render();
      return;
    }
    state.loading = true;
    render();
    try {
      const data = await fetchJsonWithTimeout(
        `${API.search}?query=${encodeURIComponent(q)}&limit=10`,
        { timeoutMs: SEARCH_TIMEOUT_MS }
      );
      console.debug("[FastMoss Shop Search] search response", data);
      state.results = data.results || [];
      cacheSet(state.searchCache, q.toLowerCase(), data);
      if (!state.results.length) {
        state.error = "No matching FastMoss shop found";
      }
    } catch (err) {
      state.results = [];
      state.error = currentErrorMessage(err);
    } finally {
      state.loading = false;
      render();
    }
  }

  async function loadDetail(candidate, forceRefresh = false) {
    const shopId = String(candidate?.shopId || "").trim();
    if (!shopId) return;
    state.error = "";
    const cacheKey = shopId;
    if (!forceRefresh) {
      const cached = cacheGet(state.detailCache, cacheKey);
      if (cached) {
        state.selected = cached;
        render();
        return;
      }
    }
    state.selected = { shopId, shopName: candidate.shopName, loading: true };
    render();
    try {
      const params = new URLSearchParams();
      if (candidate.shopName) params.set("shop_name", candidate.shopName);
      if (forceRefresh) params.set("force_refresh", "true");
      const data = await fetchJsonWithTimeout(
        API.detail(shopId, `?${params.toString()}`),
        { timeoutMs: DETAIL_TIMEOUT_MS }
      );
      console.debug("[FastMoss Shop Search] detail response", data);
      state.selected = data;
      cacheSet(state.detailCache, cacheKey, data);
    } catch (err) {
      state.selected = null;
      state.error = currentErrorMessage(err);
    }
    render();
  }

  function resultCardHtml(item) {
    return `<button type="button" class="fmss-result-card" data-shop-id="${escapeHtml(
      item.shopId
    )}">
      <div class="fmss-result-card__logo">${
        item.shopLogo
          ? `<img src="${escapeHtml(item.shopLogo)}" alt="${escapeHtml(item.shopName || "shop logo")}" />`
          : `<span>${escapeHtml((item.shopName || "?").slice(0, 1).toUpperCase())}</span>`
      }</div>
      <div class="fmss-result-card__body">
        <div class="fmss-result-card__top">
          <strong>${escapeHtml(item.shopName || "—")}</strong>
          <span class="fmss-match fmss-match--${String(item.matchLabel || "possible")
            .toLowerCase()
            .replace(/\s+/g, "-")}">${escapeHtml(item.matchLabel || "Possible Match")}</span>
        </div>
        <div class="fmss-result-card__meta">
          <span>Shop ID: ${escapeHtml(item.shopId || "—")}</span>
          <span>${escapeHtml(item.region || "—")}</span>
          <span>${escapeHtml(item.category || "N/A")}</span>
          <span>Score ${fmtNum(item.matchScore, 2)}</span>
        </div>
        <div class="fmss-result-card__stats">
          <span>Followers: ${fmtNum(item.followers)}</span>
          <span>Products: ${fmtNum(item.totalProducts)}</span>
          <span>Total Sales: ${fmtNum(item.totalSales)}</span>
          <span>Total GMV: ${fmtMoney(item.totalGmv, item.currency || "PHP")}</span>
        </div>
      </div>
    </button>`;
  }

  function kpiCard(label, value, extra = "", cls = "") {
    return `<article class="fmss-kpi ${cls}">
      <div class="fmss-kpi__label">${escapeHtml(label)}</div>
      <div class="fmss-kpi__value">${value}</div>
      ${extra ? `<div class="fmss-kpi__extra">${escapeHtml(extra)}</div>` : ""}
    </article>`;
  }

  function selectedHtml(selected) {
    if (!selected) return "";
    if (selected.loading) {
      return `<div class="fmss-loading">Loading shop detail…</div>`;
    }
    const mtdPeriod = selected.mtdPeriod || {};
    const currency = selected.currency || "PHP";
    const adgValue =
      selected.mtdAdg == null ? "N/A" : fmtMoney(selected.mtdAdg, currency, 2);
    return `<section class="fmss-detail">
      <div class="fmss-shop-card">
        <div class="fmss-shop-card__logo">${
          selected.shopLogo
            ? `<img src="${escapeHtml(selected.shopLogo)}" alt="${escapeHtml(selected.shopName || "shop logo")}" />`
            : `<span>${escapeHtml((selected.shopName || "?").slice(0, 1).toUpperCase())}</span>`
        }</div>
        <div class="fmss-shop-card__info">
          <div class="fmss-shop-card__title-row">
            <div>
              <h2>${escapeHtml(selected.shopName || "—")}</h2>
              <p>Shop ID: ${escapeHtml(selected.shopId || "—")}</p>
            </div>
            <button type="button" class="btn si-sla-btn-outline" data-force-refresh="${
              escapeHtml(selected.shopId || "")
            }">更新資料</button>
          </div>
          <div class="fmss-shop-card__grid">
            <div><span>Region</span><strong>${escapeHtml(selected.region || "N/A")}</strong></div>
            <div><span>Main Category</span><strong>${escapeHtml(selected.mainCategory || selected.category || "N/A")}</strong></div>
            <div><span>Followers</span><strong>${fmtNum(selected.followers)}</strong></div>
            <div><span>TikTok Shop URL</span><strong>${
              selected.shopUrl
                ? `<a href="${escapeHtml(selected.shopUrl)}" target="_blank" rel="noreferrer">Open shop</a>`
                : "N/A"
            }</strong></div>
          </div>
          <div class="fmss-period-line">
            <span>MTD Period: ${escapeHtml(mtdPeriod.startDate || "—")} → ${escapeHtml(
              mtdPeriod.endDate || "—"
            )}</span>
            <span>Elapsed Days: ${escapeHtml(selected.elapsedDays ?? "—")}</span>
            <span>Last Data Date: ${escapeHtml(selected.lastDataDate || "—")}</span>
            <span>Last Updated: ${escapeHtml(selected.lastUpdatedAt || "—")}</span>
          </div>
          ${
            selected.apiStatus && selected.apiStatus !== "SUCCESS"
              ? `<p class="si-v1-error">${escapeHtml(selected.errorMessage || selected.apiStatus)}</p>`
              : ""
          }
        </div>
      </div>
      <div class="fmss-kpi-grid">
        ${kpiCard("MTD Sales", fmtMoney(selected.mtdSales, currency))}
        ${kpiCard("MTD ADG", adgValue, "MTD Sales ÷ Elapsed Days", "fmss-kpi--accent")}
        ${kpiCard("MTD Orders", fmtNum(selected.mtdOrders))}
        ${kpiCard("Followers", fmtNum(selected.followers), "N/A if unavailable")}
        ${kpiCard("Active Products", fmtNum(selected.activeProducts))}
        ${kpiCard("Total Products", fmtNum(selected.totalProducts))}
        ${kpiCard("Total Sales", fmtNum(selected.totalSales))}
        ${kpiCard("Total GMV", fmtMoney(selected.totalGmv, currency))}
      </div>
    </section>`;
  }

  function render() {
    if (!contentEl) return;
    if (metaEl) {
      metaEl.textContent = "Search TikTok shops and calculate month-to-date ADG";
    }
    contentEl.innerHTML = `<section class="fmss-page">
      <div class="si-v1-toolbar fmss-toolbar">
        <div class="si-v1-toolbar-field si-v1-toolbar-field--search">
          <label for="fmssQuery">Search by shop name</label>
          <input id="fmssQuery" type="search" placeholder="FastMoss / TikTok Shop Name" value="${escapeHtml(
            state.query
          )}" />
        </div>
        <button type="button" class="btn btn-primary fmss-search-btn" id="fmssSearchBtn">${
          state.loading ? "Searching…" : "Search"
        }</button>
      </div>
      ${state.error ? `<p class="si-v1-error">${escapeHtml(state.error)}</p>` : ""}
      <div class="fmss-layout">
        <section class="fmss-results">
          <h3>候選店鋪</h3>
          ${
            !state.results.length
              ? `<p class="si-v1-meta">${escapeHtml(
                  state.loading ? "Searching FastMoss…" : "Enter a shop name to see the top 10 matches."
                )}</p>`
              : state.results.map(resultCardHtml).join("")
          }
        </section>
        <section class="fmss-selected">
          ${selectedHtml(state.selected) || `<div class="fmss-empty">Select a shop candidate to load detail.</div>`}
        </section>
      </div>
    </section>`;

    document.getElementById("fmssSearchBtn")?.addEventListener("click", () => {
      search(document.getElementById("fmssQuery")?.value || "");
    });
    document.getElementById("fmssQuery")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        search(e.currentTarget.value || "");
      }
    });
    contentEl.querySelectorAll("[data-shop-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = state.results.find((r) => String(r.shopId) === String(btn.dataset.shopId));
        if (item) loadDetail(item);
      });
    });
    contentEl.querySelector("[data-force-refresh]")?.addEventListener("click", (e) => {
      const shopId = e.currentTarget.dataset.forceRefresh;
      const item = state.results.find((r) => String(r.shopId) === String(shopId)) || state.selected;
      if (item) {
        state.detailCache.delete(String(shopId));
        loadDetail(item, true);
      }
    });
  }

  function onShow(reset = false) {
    if (reset && !state.query) {
      state.results = [];
      state.selected = null;
    }
    render();
  }

  window.ShpFastmossShopSearch = { onShow, search, loadDetail };
})();
