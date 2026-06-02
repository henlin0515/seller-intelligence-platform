/**
 * Historical SOB Analysis — April/May Shopee + TikTok share of business.
 */
(function () {
  const API = "/api/intelligence/v1/historical-sob";
  const contentEl = document.getElementById("siHistoricalSobContent");
  const metaEl = document.getElementById("siHistoricalSobMeta");

  let payload = null;
  let filters = {
    search: "",
    month: "all",
    mappingStatus: "all",
    category: "all",
  };

  function i18n(key, fallback = "") {
    return window.SipI18n?.t(key, fallback) ?? fallback ?? key;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function fetchApi(path) {
    const res = await (window.SipApi ? window.SipApi.fetch : fetch)(path, {
      credentials: "same-origin",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    return data;
  }

  function fmtNum(value) {
    if (value == null || Number.isNaN(Number(value))) return "—";
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function fmtGmv(value) {
    if (value == null || Number.isNaN(Number(value))) return "N/A";
    return `₱${fmtNum(value)}`;
  }

  function fmtPct(value) {
    if (value == null || Number.isNaN(Number(value))) return "N/A";
    return `${Number(value).toFixed(1)}%`;
  }

  function fmtChange(value) {
    if (value == null || Number.isNaN(Number(value))) return "N/A";
    const n = Number(value);
    const sign = n > 0 ? "+" : "";
    return `${sign}${n.toFixed(1)} pp`;
  }

  function filteredRows() {
    const rows = payload?.sellers || [];
    const q = filters.search.trim().toLowerCase();
    return rows.filter((row) => {
      if (filters.mappingStatus !== "all" && row.mapping_status !== filters.mappingStatus) {
        return false;
      }
      if (filters.category !== "all") {
        const cat = row.category || i18n("historicalSob.uncategorized", "Uncategorized");
        if (cat !== filters.category) return false;
      }
      if (filters.month === "april" && row.april_shopee_sob_percent == null && row.april_tiktok_sob_percent == null) {
        return false;
      }
      if (filters.month === "may" && row.may_shopee_sob_percent == null && row.may_tiktok_sob_percent == null) {
        return false;
      }
      if (!q) return true;
      const hay = [
        row.shop_id,
        row.shop_name,
        row.tiktok_shop_name,
        row.fastmoss_shop_name,
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }

  function renderKpi(label, value, sub, accent) {
    return `<article class="hs-kpi hs-kpi--${accent || "neutral"}">
      <span class="hs-kpi-label">${escapeHtml(label)}</span>
      <strong class="hs-kpi-value">${escapeHtml(value)}</strong>
      ${sub ? `<span class="hs-kpi-sub">${escapeHtml(sub)}</span>` : ""}
    </article>`;
  }

  function renderSobBar(label, shopeePct, tiktokPct) {
    if (shopeePct == null || tiktokPct == null) {
      return `<div class="hs-sob-block"><div class="hs-sob-label">${escapeHtml(label)}</div><p class="hs-empty">N/A</p></div>`;
    }
    const shp = Math.max(0, Math.min(100, Number(shopeePct)));
    const tk = Math.max(0, Math.min(100, Number(tiktokPct)));
    return `
      <div class="hs-sob-block">
        <div class="hs-sob-label">${escapeHtml(label)}</div>
        <div class="hs-sob-metrics">
          <span class="hs-sob-metric hs-sob-metric--shp">Shopee ${fmtPct(shp)}</span>
          <span class="hs-sob-metric hs-sob-metric--tk">TikTok ${fmtPct(tk)}</span>
        </div>
        <div class="hs-sob-stack" aria-hidden="true">
          <span class="hs-sob-seg hs-sob-seg--shp" style="width:${shp}%"></span>
          <span class="hs-sob-seg hs-sob-seg--tk" style="width:${tk}%"></span>
        </div>
      </div>`;
  }

  function renderGmvBars(portfolio) {
    const items = [
      { key: "april_shopee_gmv", label: "Apr Shopee", cls: "shp" },
      { key: "april_tiktok_gmv", label: "Apr TikTok", cls: "tk" },
      { key: "may_shopee_gmv", label: "May Shopee", cls: "shp" },
      { key: "may_tiktok_gmv", label: "May TikTok", cls: "tk" },
    ];
    const values = items.map((item) => Number(portfolio?.[item.key] || 0));
    const max = Math.max(...values, 1);
    const bars = items
      .map((item, idx) => {
        const val = portfolio?.[item.key];
        const width = val == null ? 0 : (Number(val) / max) * 100;
        return `<div class="hs-gmv-row">
          <span class="hs-gmv-label">${escapeHtml(item.label)}</span>
          <div class="hs-gmv-track"><span class="hs-gmv-fill hs-gmv-fill--${item.cls}" style="width:${width}%"></span></div>
          <span class="hs-gmv-value">${fmtGmv(val)}</span>
        </div>`;
      })
      .join("");
    return `<div class="hs-gmv-chart">${bars}</div>`;
  }

  function renderToolbar() {
    const statuses = payload?.filters?.mapping_statuses || [];
    const categories = payload?.filters?.categories || [];
    const statusOpts = [
      `<option value="all">${escapeHtml(i18n("historicalSob.statusAll", "All"))}</option>`,
      ...statuses.map(
        (s) => `<option value="${escapeHtml(s)}"${filters.mappingStatus === s ? " selected" : ""}>${escapeHtml(s)}</option>`
      ),
    ].join("");
    const catOpts = [
      `<option value="all">${escapeHtml(i18n("historicalSob.categoryAll", "All categories"))}</option>`,
      ...categories.map(
        (c) => `<option value="${escapeHtml(c)}"${filters.category === c ? " selected" : ""}>${escapeHtml(c)}</option>`
      ),
    ].join("");
    return `
      <div class="hs-toolbar">
        <label class="hs-filter">
          <span>${escapeHtml(i18n("historicalSob.filterSearch", "Search"))}</span>
          <input type="search" id="hsFilterSearch" value="${escapeHtml(filters.search)}" placeholder="${escapeHtml(i18n("historicalSob.filterSearchPh", "Shop ID, name, TikTok…"))}">
        </label>
        <label class="hs-filter">
          <span>${escapeHtml(i18n("historicalSob.filterMonth", "Month"))}</span>
          <select id="hsFilterMonth">
            <option value="all"${filters.month === "all" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.monthAll", "Both months"))}</option>
            <option value="april"${filters.month === "april" ? " selected" : ""}>April</option>
            <option value="may"${filters.month === "may" ? " selected" : ""}>May</option>
          </select>
        </label>
        <label class="hs-filter">
          <span>${escapeHtml(i18n("historicalSob.filterMapping", "TikTok mapping"))}</span>
          <select id="hsFilterMapping">${statusOpts}</select>
        </label>
        <label class="hs-filter">
          <span>${escapeHtml(i18n("historicalSob.filterCategory", "Category"))}</span>
          <select id="hsFilterCategory">${catOpts}</select>
        </label>
        <span class="hs-filter-count">${escapeHtml(i18n("historicalSob.resultCount", "{n} shops").replace("{n}", String(filteredRows().length)))}</span>
      </div>`;
  }

  function renderMoversTable(rows) {
    if (!rows.length) return `<p class="hs-empty">${escapeHtml(i18n("historicalSob.emptyMovers", "No SOB movers match filters."))}</p>`;
    const body = rows
      .map(
        (r) => `<tr>
          <td>${escapeHtml(r.shop_id)}</td>
          <td>${escapeHtml(r.shop_name)}</td>
          <td class="si-v1-num">${fmtPct(r.april_shopee_sob_percent)}</td>
          <td class="si-v1-num">${fmtPct(r.april_tiktok_sob_percent)}</td>
          <td class="si-v1-num">${fmtPct(r.may_shopee_sob_percent)}</td>
          <td class="si-v1-num">${fmtPct(r.may_tiktok_sob_percent)}</td>
          <td class="si-v1-num">${fmtChange(r.sob_change_pp)}</td>
        </tr>`
      )
      .join("");
    return `
      <div class="si-v1-table-wrap">
        <table class="si-v1-table hs-table">
          <thead>
            <tr>
              <th>Shop ID</th>
              <th>Shop Name</th>
              <th>Apr Shopee SOB</th>
              <th>Apr TikTok SOB</th>
              <th>May Shopee SOB</th>
              <th>May TikTok SOB</th>
              <th>SOB Change</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function renderThreatTable(rows) {
    if (!rows.length) return `<p class="hs-empty">${escapeHtml(i18n("historicalSob.emptyThreats", "No TikTok threat sellers match filters."))}</p>`;
    const body = rows
      .map(
        (r) => `<tr>
          <td>${escapeHtml(r.shop_name)}</td>
          <td class="si-v1-num">${fmtPct(r.may_tiktok_sob_percent)}</td>
          <td class="si-v1-num">${fmtGmv(r.may_tiktok_gmv)}</td>
          <td class="si-v1-num">${fmtGmv(r.may_shopee_gmv)}</td>
          <td class="si-v1-num">${fmtPct(r.april_tiktok_sob_percent)}</td>
          <td class="si-v1-num">${fmtChange(r.sob_change_pp)}</td>
        </tr>`
      )
      .join("");
    return `
      <div class="si-v1-table-wrap">
        <table class="si-v1-table hs-table">
          <thead>
            <tr>
              <th>Shop Name</th>
              <th>May TikTok SOB</th>
              <th>May TikTok GMV</th>
              <th>May Shopee GMV</th>
              <th>Apr TikTok SOB</th>
              <th>Change</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function renderWarnings() {
    const warnings = payload?.warnings || [];
    if (!warnings.length) return "";
    const items = warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("");
    return `<div class="hs-warnings" role="status"><strong>${escapeHtml(i18n("historicalSob.warningsTitle", "Data warnings"))}</strong><ul>${items}</ul></div>`;
  }

  function renderPage() {
    if (!contentEl || !payload) return;
    const kpis = payload.kpis || {};
    const portfolio = payload.portfolio || {};
    const rows = filteredRows();
    const movers = (payload.top_sob_movers || []).filter((r) =>
      rows.some((x) => x.shop_id === r.shop_id)
    );
    const threats = (payload.tiktok_threat_sellers || []).filter((r) =>
      rows.some((x) => x.shop_id === r.shop_id)
    );

    contentEl.innerHTML = `
      ${renderWarnings()}
      ${renderToolbar()}
      <section class="hs-kpi-grid">
        ${renderKpi(i18n("historicalSob.kpiTotalShops", "Total Shops"), fmtNum(kpis.total_shops), payload.master_tab, "neutral")}
        ${renderKpi(i18n("historicalSob.kpiAprShopee", "April Shopee GMV"), fmtGmv(kpis.april_shopee_gmv), "ytd_ap_adgmv × 30", "shopee")}
        ${renderKpi(i18n("historicalSob.kpiAprTiktok", "April TikTok GMV"), fmtGmv(kpis.april_tiktok_gmv), "FastMoss sale_amount", "tiktok")}
        ${renderKpi(i18n("historicalSob.kpiMayShopee", "May Shopee GMV"), fmtGmv(kpis.may_shopee_gmv), "ytd_may_adgmv × 31", "shopee")}
        ${renderKpi(i18n("historicalSob.kpiMayTiktok", "May TikTok GMV"), fmtGmv(kpis.may_tiktok_gmv), "FastMoss sale_amount", "tiktok")}
      </section>
      <section class="hs-panel">
        <h2 class="hs-panel-title">${escapeHtml(i18n("historicalSob.chartSob", "Portfolio Historical SOB"))}</h2>
        ${renderSobBar("April", portfolio.april_shopee_sob_percent, portfolio.april_tiktok_sob_percent)}
        ${renderSobBar("May", portfolio.may_shopee_sob_percent, portfolio.may_tiktok_sob_percent)}
      </section>
      <section class="hs-panel">
        <h2 class="hs-panel-title">${escapeHtml(i18n("historicalSob.tableMovers", "Top SOB Movers"))}</h2>
        ${renderMoversTable(movers)}
      </section>
      <section class="hs-panel">
        <h2 class="hs-panel-title">${escapeHtml(i18n("historicalSob.tableThreats", "Biggest TikTok Threat Sellers"))}</h2>
        ${renderThreatTable(threats)}
      </section>`;

    bindFilters();
  }

  function bindFilters() {
    document.getElementById("hsFilterSearch")?.addEventListener("input", (e) => {
      filters.search = e.target.value;
      renderPage();
    });
    document.getElementById("hsFilterMonth")?.addEventListener("change", (e) => {
      filters.month = e.target.value;
      renderPage();
    });
    document.getElementById("hsFilterMapping")?.addEventListener("change", (e) => {
      filters.mappingStatus = e.target.value;
      renderPage();
    });
    document.getElementById("hsFilterCategory")?.addEventListener("change", (e) => {
      filters.category = e.target.value;
      renderPage();
    });
  }

  function updateMeta() {
    if (!metaEl || !payload) return;
    const s = payload.summary || {};
    metaEl.textContent = [
      payload.master_tab,
      payload.ytd_tab,
      `${s.april_sob_calculated_count || 0} Apr SOB`,
      `${s.may_sob_calculated_count || 0} May SOB`,
      payload.cache_updated_at ? `cache ${payload.cache_updated_at}` : "",
    ]
      .filter(Boolean)
      .join(" · ");
  }

  function showLoading() {
    if (contentEl) contentEl.innerHTML = `<p class="si-v1-loading">${escapeHtml(i18n("historicalSob.loading", "Loading Historical SOB…"))}</p>`;
    if (metaEl) metaEl.textContent = i18n("historicalSob.loadingMeta", "Loading…");
  }

  function showError(message) {
    if (contentEl) {
      contentEl.innerHTML = `<p class="si-v1-error">${escapeHtml(message || i18n("historicalSob.loadError", "Could not load Historical SOB"))}</p>`;
    }
    if (metaEl) metaEl.textContent = i18n("historicalSob.loadErrorMeta", "Load failed");
  }

  async function load(force = false) {
    if (!force && payload) {
      renderPage();
      updateMeta();
      return payload;
    }
    showLoading();
    try {
      payload = await fetchApi(API);
      renderPage();
      updateMeta();
      return payload;
    } catch (err) {
      showError(err.message);
      throw err;
    }
  }

  function init() {
    load(false).catch(() => {});
  }

  function clearCache() {
    payload = null;
  }

  window.ShpHistoricalSob = { init, load, clearCache };
})();
