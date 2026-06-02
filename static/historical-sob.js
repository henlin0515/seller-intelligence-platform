/**
 * Historical SOB — fixed portfolio summary + seller table (Seller Level Analysis UX).
 */
(function () {
  const API = "/api/intelligence/v1/historical-sob";
  const contentEl = document.getElementById("siHistoricalSobContent");
  const metaEl = document.getElementById("siHistoricalSobMeta");

  let payload = null;
  let shellReady = false;
  let filters = defaultFilters();

  function defaultFilters() {
    return { q: "", mappingStatus: "all", sort: "shop_name" };
  }

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

  function fmtNa(reason) {
    const title = reason ? ` title="${escapeHtml(reason)}"` : "";
    return `<span class="si-v1-na"${title}>N/A</span>`;
  }

  function mappingBadge(status) {
    const map = {
      APPROVED: ["si-v1-badge--ok", "Approved"],
      PENDING_REVIEW: ["si-v1-badge--warn", "Pending review"],
      REJECTED: ["si-v1-badge--risk", "Rejected"],
      NOT_MAPPED: ["si-v1-badge--muted", "Not mapped"],
    };
    const [cls, label] = map[status] || ["si-v1-badge--muted", status || "—"];
    return `<span class="si-v1-badge ${cls}">${escapeHtml(label)}</span>`;
  }

  function sellerSearchBlob(row) {
    return [row.shop_id, row.shop_name, row.tiktok_shop_name]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function filterSellers(rows) {
    const q = filters.q.trim().toLowerCase();
    let list = (rows || []).filter((row) => {
      if (filters.mappingStatus !== "all" && row.mapping_status !== filters.mappingStatus) {
        return false;
      }
      if (q && !sellerSearchBlob(row).includes(q)) return false;
      return true;
    });
    return sortSellers(list, filters.sort);
  }

  function sortSellers(list, sort) {
    const copy = [...list];
    const cmp = (a, b) => (a > b ? 1 : a < b ? -1 : 0);
    copy.sort((a, b) => {
      switch (sort) {
        case "april_shopee":
          return cmp(b.april_shopee_gmv ?? -1, a.april_shopee_gmv ?? -1);
        case "april_tiktok":
          return cmp(b.april_tiktok_gmv ?? -1, a.april_tiktok_gmv ?? -1);
        case "april_sob":
          return cmp(b.april_sob_percent ?? -1, a.april_sob_percent ?? -1);
        case "may_shopee":
          return cmp(b.may_shopee_gmv ?? -1, a.may_shopee_gmv ?? -1);
        case "may_tiktok":
          return cmp(b.may_tiktok_gmv ?? -1, a.may_tiktok_gmv ?? -1);
        case "may_sob":
          return cmp(b.may_sob_percent ?? -1, a.may_sob_percent ?? -1);
        case "sob_change":
          return cmp(b.sob_change_pp ?? -999, a.sob_change_pp ?? -999);
        case "mapping":
          return String(a.mapping_status || "").localeCompare(String(b.mapping_status || ""));
        default:
          return String(a.shop_name || "").localeCompare(String(b.shop_name || ""));
      }
    });
    return copy;
  }

  function renderPortfolioKpi(label, value, sub, accent) {
    const accentCls = accent ? ` si-port-kpi--${accent}` : "";
    return `
      <article class="si-port-kpi${accentCls}">
        <div class="si-port-kpi-label">${escapeHtml(label)}</div>
        <div class="si-port-kpi-value">${value}</div>
        ${sub ? `<div class="si-port-kpi-sub">${escapeHtml(sub)}</div>` : ""}
      </article>`;
  }

  function renderOverallSummary() {
    const kpis = payload?.kpis || {};
    const summary = payload?.summary || {};
    const warnings = payload?.warnings || [];
    const warnHtml = warnings.length
      ? `<div class="hs-warnings" role="status"><strong>${escapeHtml(i18n("historicalSob.warningsTitle", "Data warnings"))}</strong><ul>${warnings
          .map((w) => `<li>${escapeHtml(w)}</li>`)
          .join("")}</ul></div>`
      : "";
    const debugLine = [
      `YTD rows: ${fmtNum(summary.ytd_monthly_rows_loaded ?? 0)}`,
      `Matched: ${fmtNum(summary.ytd_matched_count ?? 0)}`,
      `Unmatched: ${fmtNum(summary.ytd_unmatched_count ?? 0)}`,
      payload?.ytd_tab ? `Tab: ${payload.ytd_tab}` : "",
    ]
      .filter(Boolean)
      .join(" · ");

    return `
      ${warnHtml}
      <section class="hs-overall-summary" aria-label="Overall Historical SOB summary">
        <div class="si-port-kpi-grid">
          ${renderPortfolioKpi(
            i18n("historicalSob.kpiTotalShops", "Total Shops"),
            fmtNum(kpis.total_shops),
            payload?.master_tab,
            "neutral"
          )}
          ${renderPortfolioKpi(
            i18n("historicalSob.kpiAprShopee", "April Shopee GMV"),
            escapeHtml(fmtGmv(kpis.april_shopee_gmv)),
            "ytd_apr_adgmv × 30",
            "shopee"
          )}
          ${renderPortfolioKpi(
            i18n("historicalSob.kpiAprTiktok", "April TikTok GMV"),
            escapeHtml(fmtGmv(kpis.april_tiktok_gmv)),
            "FastMoss Apr",
            "tiktok"
          )}
          ${renderPortfolioKpi(
            i18n("historicalSob.kpiAprSob", "April Portfolio SOB %"),
            escapeHtml(fmtPct(kpis.april_portfolio_sob_percent)),
            "TikTok / (TikTok + Shopee)",
            "hero"
          )}
          ${renderPortfolioKpi(
            i18n("historicalSob.kpiMayShopee", "May Shopee GMV"),
            escapeHtml(fmtGmv(kpis.may_shopee_gmv)),
            "ytd_may_adgmv × 31",
            "shopee"
          )}
          ${renderPortfolioKpi(
            i18n("historicalSob.kpiMayTiktok", "May TikTok GMV"),
            escapeHtml(fmtGmv(kpis.may_tiktok_gmv)),
            "FastMoss May",
            "tiktok"
          )}
          ${renderPortfolioKpi(
            i18n("historicalSob.kpiMaySob", "May Portfolio SOB %"),
            escapeHtml(fmtPct(kpis.may_portfolio_sob_percent)),
            "TikTok / (TikTok + Shopee)",
            "hero"
          )}
          ${renderPortfolioKpi(
            i18n("historicalSob.kpiSobChange", "Portfolio SOB Change %"),
            escapeHtml(fmtChange(kpis.portfolio_sob_change_pp)),
            "May SOB − April SOB",
            "accent"
          )}
        </div>
        <p class="hs-debug-meta">${escapeHtml(debugLine)}</p>
      </section>`;
  }

  function toolbarHtml(f) {
    const statuses = payload?.filters?.mapping_statuses || [];
    const statusOpts = [
      `<option value="all">${escapeHtml(i18n("historicalSob.statusAll", "All"))}</option>`,
      ...statuses.map(
        (s) =>
          `<option value="${escapeHtml(s)}"${f.mappingStatus === s ? " selected" : ""}>${escapeHtml(s)}</option>`
      ),
    ].join("");
    return `
      <div class="si-v1-toolbar" data-toolbar="historical-sob">
        <div class="si-v1-toolbar-field si-v1-toolbar-field--search">
          <label for="hsFilterSearch">${escapeHtml(i18n("historicalSob.filterSearch", "Seller search"))}</label>
          <input id="hsFilterSearch" type="search" placeholder="${escapeHtml(i18n("historicalSob.filterSearchPh", "Shop ID, name, TikTok…"))}" value="${escapeHtml(f.q)}" data-f="q" />
        </div>
        <div class="si-v1-toolbar-field">
          <label for="hsFilterMapping">${escapeHtml(i18n("historicalSob.filterMapping", "TikTok mapping"))}</label>
          <select id="hsFilterMapping" data-f="mappingStatus">${statusOpts}</select>
        </div>
        <div class="si-v1-toolbar-field">
          <label for="hsFilterSort">${escapeHtml(i18n("historicalSob.filterSort", "Sort"))}</label>
          <select id="hsFilterSort" data-f="sort">
            <option value="shop_name"${f.sort === "shop_name" ? " selected" : ""}>Shop name</option>
            <option value="april_shopee"${f.sort === "april_shopee" ? " selected" : ""}>April Shopee GMV</option>
            <option value="april_tiktok"${f.sort === "april_tiktok" ? " selected" : ""}>April TikTok GMV</option>
            <option value="april_sob"${f.sort === "april_sob" ? " selected" : ""}>April SOB %</option>
            <option value="may_shopee"${f.sort === "may_shopee" ? " selected" : ""}>May Shopee GMV</option>
            <option value="may_tiktok"${f.sort === "may_tiktok" ? " selected" : ""}>May TikTok GMV</option>
            <option value="may_sob"${f.sort === "may_sob" ? " selected" : ""}>May SOB %</option>
            <option value="sob_change"${f.sort === "sob_change" ? " selected" : ""}>SOB Change</option>
            <option value="mapping"${f.sort === "mapping" ? " selected" : ""}>Mapping status</option>
          </select>
        </div>
        <button type="button" class="si-v1-btn-reset" data-reset>${escapeHtml(i18n("historicalSob.resetFilters", "Reset filters"))}</button>
        <p class="si-v1-result-count" data-result-count></p>
      </div>`;
  }

  function readFiltersFromToolbar(toolbar) {
    const f = { ...defaultFilters() };
    toolbar.querySelectorAll("[data-f]").forEach((node) => {
      f[node.dataset.f] = node.value;
    });
    return f;
  }

  function bindToolbar(el, onChange) {
    el.querySelectorAll("input, select").forEach((node) => {
      node.addEventListener("input", onChange);
      node.addEventListener("change", onChange);
    });
    el.querySelector("[data-reset]")?.addEventListener("click", (e) => {
      e.preventDefault();
      onChange({ reset: true });
    });
  }

  function cellGmv(value, reason) {
    if (value == null || Number.isNaN(Number(value))) return fmtNa(reason);
    return escapeHtml(fmtGmv(value));
  }

  function cellSob(value) {
    if (value == null || Number.isNaN(Number(value))) {
      return fmtNa("SOB requires Shopee and TikTok GMV");
    }
    return escapeHtml(fmtPct(value));
  }

  function renderSellerTable(rows) {
    if (!rows.length) {
      return `<p class="si-v1-empty">${escapeHtml(i18n("historicalSob.emptySellers", "No sellers match the current filters."))}</p>`;
    }
    const body = rows
      .map(
        (r) => `<tr>
          <td>${escapeHtml(r.shop_id)}</td>
          <td class="si-biz-name">${escapeHtml(r.shop_name)}</td>
          <td class="si-v1-num">${cellGmv(r.april_shopee_gmv, r.shopee_na_reason)}</td>
          <td class="si-v1-num">${cellGmv(r.april_tiktok_gmv, r.tiktok_na_reason)}</td>
          <td class="si-v1-num">${cellSob(r.april_sob_percent)}</td>
          <td class="si-v1-num">${cellGmv(r.may_shopee_gmv, r.shopee_na_reason)}</td>
          <td class="si-v1-num">${cellGmv(r.may_tiktok_gmv, r.tiktok_na_reason)}</td>
          <td class="si-v1-num">${cellSob(r.may_sob_percent)}</td>
          <td class="si-v1-num">${escapeHtml(fmtChange(r.sob_change_pp))}</td>
          <td>${mappingBadge(r.mapping_status)}</td>
        </tr>`
      )
      .join("");
    return `
      <div class="si-v1-table-wrap si-v1-table-wrap--wide">
        <table class="si-v1-table si-v1-table--business hs-seller-table">
          <thead>
            <tr>
              <th>Shop ID</th>
              <th>Shop Name</th>
              <th>April Shopee GMV</th>
              <th>April TikTok GMV</th>
              <th>April SOB %</th>
              <th>May Shopee GMV</th>
              <th>May TikTok GMV</th>
              <th>May SOB %</th>
              <th>SOB Change %</th>
              <th>TikTok Mapping Status</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function paintSummary() {
    const summaryEl = contentEl?.querySelector("[data-hs-summary]");
    if (summaryEl && payload) {
      summaryEl.innerHTML = renderOverallSummary();
    }
  }

  function paintSellerList() {
    if (!contentEl || !payload) return;
    const listEl = contentEl.querySelector("[data-hs-list]");
    const toolbarEl = contentEl.querySelector("[data-toolbar]");
    if (!listEl || !toolbarEl) return;

    const all = payload.sellers || [];
    const filtered = filterSellers(all);
    const countEl = toolbarEl.querySelector("[data-result-count]");
    if (countEl) {
      countEl.textContent = `Showing ${filtered.length} of ${all.length} sellers`;
    }
    listEl.innerHTML = renderSellerTable(filtered);
  }

  function setupShell() {
    if (!contentEl || !payload) return;
    if (!shellReady) {
      contentEl.innerHTML = `
        <div data-hs-summary class="hs-overall-summary-wrap"></div>
        ${toolbarHtml(filters)}
        <div class="si-v1-list" data-hs-list></div>`;

      const onToolbar = (ev) => {
        if (ev?.reset) {
          filters = defaultFilters();
        } else {
          filters = readFiltersFromToolbar(contentEl.querySelector("[data-toolbar]"));
        }
        contentEl.querySelector("[data-toolbar]").outerHTML = toolbarHtml(filters);
        bindToolbar(contentEl.querySelector("[data-toolbar]"), onToolbar);
        paintSellerList();
      };
      bindToolbar(contentEl.querySelector("[data-toolbar]"), onToolbar);
      shellReady = true;
    }
    paintSummary();
    paintSellerList();
  }

  function updateMeta() {
    if (!metaEl || !payload) return;
    const s = payload.summary || {};
    metaEl.textContent = [
      "April 2026 · May 2026",
      payload.ytd_tab,
      `${s.ytd_matched_count ?? 0}/${s.master_seller_count ?? 0} YTD matched`,
    ]
      .filter(Boolean)
      .join(" · ");
  }

  function showLoading() {
    shellReady = false;
    if (contentEl) {
      contentEl.innerHTML = `<p class="si-v1-loading">${escapeHtml(i18n("historicalSob.loading", "Loading Historical SOB…"))}</p>`;
    }
    if (metaEl) metaEl.textContent = i18n("historicalSob.loadingMeta", "Loading…");
  }

  function showError(message) {
    shellReady = false;
    if (contentEl) {
      contentEl.innerHTML = `<p class="si-v1-error">${escapeHtml(message || i18n("historicalSob.loadError", "Could not load Historical SOB"))}</p>`;
    }
    if (metaEl) metaEl.textContent = i18n("historicalSob.loadErrorMeta", "Load failed");
  }

  async function load(force = false) {
    if (!force && payload) {
      setupShell();
      updateMeta();
      return payload;
    }
    showLoading();
    try {
      payload = await fetchApi(API);
      setupShell();
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
    shellReady = false;
    filters = defaultFilters();
  }

  window.ShpHistoricalSob = { init, load, clearCache };
})();
