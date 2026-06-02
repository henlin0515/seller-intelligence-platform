/**
 * Historical SOB — complete analysis page (visual parity with Seller Level Analysis).
 */
(function () {
  const API = "/api/intelligence/v1/historical-sob";
  const contentEl = document.getElementById("siHistoricalSobContent");
  const metaEl = document.getElementById("siHistoricalSobMeta");
  const summaryEl = document.getElementById("siHistoricalSobActionSummary");
  const refreshBtn = document.getElementById("siHistoricalSobRefreshDataBtn");

  const SOB_INBAR_MIN = 14;

  let payload = null;
  let shellReady = false;
  let expanded = new Set();
  let filters = defaultFilters();

  function defaultFilters() {
    return { q: "", mapped: "all", category: "all", sort: "shop_name" };
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

  async function fetchApi(path, options = {}) {
    const res = await (window.SipApi ? window.SipApi.fetch : fetch)(path, {
      credentials: "same-origin",
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    return data;
  }

  function fmtNum(value, digits = 0) {
    if (value == null || Number.isNaN(Number(value))) return "—";
    return Number(value).toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits,
    });
  }

  function fmtGmv(value) {
    if (value == null || Number.isNaN(Number(value))) return null;
    return `₱${fmtNum(value)}`;
  }

  function fmtPct(value) {
    if (value == null || Number.isNaN(Number(value))) return "—";
    return `${fmtNum(value, 1)}%`;
  }

  function fmtChange(value) {
    if (value == null || Number.isNaN(Number(value))) return "—";
    const n = Number(value);
    const sign = n > 0 ? "+" : "";
    return `${sign}${n.toFixed(1)} pp`;
  }

  function fmtNa(reason) {
    const title = reason ? ` title="${escapeHtml(reason)}"` : "";
    return `<span class="si-v1-na"${title}>NA</span>`;
  }

  function fmtDetail(value) {
    if (value == null || value === "") return "—";
    return escapeHtml(String(value));
  }

  function clampSobPct(value) {
    if (value == null || Number.isNaN(value)) return null;
    return Math.max(0, Math.min(100, value));
  }

  function formatLastUpdated(iso) {
    if (!iso) return i18n("historicalSob.lastUpdatedUnknown", "Last updated: —");
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return i18n("historicalSob.lastUpdatedUnknown", "Last updated: —");
      return i18n("historicalSob.lastUpdated", "Last updated: {time}").replace(
        "{time}",
        d.toLocaleString()
      );
    } catch {
      return i18n("historicalSob.lastUpdatedUnknown", "Last updated: —");
    }
  }

  function formatMappingSummary(data) {
    const hs = data?.historical_sob || {};
    const summary = hs.summary || {};
    return i18n(
      "historicalSob.refreshSummary",
      "YTD matched: {matched} · TikTok cached: {tiktok}"
    )
      .replace("{matched}", String(summary.ytd_matched_count ?? "—"))
      .replace("{tiktok}", String(summary.tiktok_may_gmv_fetched_count ?? "—"));
  }

  function sellerSearchBlob(row) {
    return [row.shop_id, row.shop_name, row.tiktok_shop_name, row.fastmoss_shop_name]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function isMapped(row) {
    return String(row.mapping_status || "").toUpperCase() === "APPROVED";
  }

  function filterSellers(rows) {
    const q = filters.q.trim().toLowerCase();
    return sortSellers(
      (rows || []).filter((row) => {
        if (q && !sellerSearchBlob(row).includes(q)) return false;
        if (filters.mapped === "mapped" && !isMapped(row)) return false;
        if (filters.mapped === "not_mapped" && isMapped(row)) return false;
        const cat = row.category || i18n("historicalSob.uncategorized", "Uncategorized");
        if (filters.category !== "all" && cat !== filters.category) return false;
        return true;
      })
    );
  }

  function sortSellers(list) {
    const copy = [...list];
    const cmp = (a, b) => (a > b ? 1 : a < b ? -1 : 0);
    copy.sort((a, b) => {
      switch (filters.sort) {
        case "tiktok_sob":
          return cmp(
            b.may_tiktok_sob_percent ?? b.april_tiktok_sob_percent ?? -1,
            a.may_tiktok_sob_percent ?? a.april_tiktok_sob_percent ?? -1
          );
        case "shopee_sob":
          return cmp(
            b.may_shopee_sob_percent ?? b.april_shopee_sob_percent ?? -1,
            a.may_shopee_sob_percent ?? a.april_shopee_sob_percent ?? -1
          );
        case "sob_change":
          return cmp(
            Math.abs(b.sob_change_pp ?? -999),
            Math.abs(a.sob_change_pp ?? -999)
          );
        default:
          return String(a.shop_name || "").localeCompare(String(b.shop_name || ""));
      }
    });
    return copy;
  }

  function mappingReviewBadge(row) {
    const status = String(row.mapping_status || "").toUpperCase();
    const map = {
      APPROVED: ["si-v1-badge--ok", "Mapped"],
      PENDING_REVIEW: ["si-v1-badge--warn", "Pending review"],
      REJECTED: ["si-v1-badge--risk", "Rejected"],
      NOT_MAPPED: ["si-v1-badge--muted", "Not mapped"],
    };
    const [cls, label] = map[status] || ["si-v1-badge--muted", status || "—"];
    return `<span class="si-v1-badge ${cls}">${escapeHtml(label)}</span>`;
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

  function renderKpiGrid() {
    const k = payload?.kpis || {};
    const gmv = (v) => escapeHtml(fmtGmv(v) || "N/A");
    const pct = (v) => escapeHtml(fmtPct(v));
    const change = escapeHtml(fmtChange(k.portfolio_sob_change_pp));

    return `
      <div class="si-port-kpi-grid hs-page-kpis">
        ${renderPortfolioKpi(
          i18n("historicalSob.kpiAprPortfolioGmv", "April Portfolio GMV"),
          gmv(k.april_portfolio_gmv),
          "Shopee + TikTok",
          "hero"
        )}
        ${renderPortfolioKpi(
          i18n("historicalSob.kpiMayPortfolioGmv", "May Portfolio GMV"),
          gmv(k.may_portfolio_gmv),
          "Shopee + TikTok",
          "hero"
        )}
        ${renderPortfolioKpi(
          i18n("historicalSob.kpiAprShopeeSob", "April Shopee SOB"),
          pct(k.april_shopee_sob_percent),
          "",
          "shopee"
        )}
        ${renderPortfolioKpi(
          i18n("historicalSob.kpiMayShopeeSob", "May Shopee SOB"),
          pct(k.may_shopee_sob_percent),
          "",
          "shopee"
        )}
        ${renderPortfolioKpi(
          i18n("historicalSob.kpiAprTiktokSob", "April TikTok SOB"),
          pct(k.april_tiktok_sob_percent),
          "",
          "tiktok"
        )}
        ${renderPortfolioKpi(
          i18n("historicalSob.kpiMayTiktokSob", "May TikTok SOB"),
          pct(k.may_tiktok_sob_percent),
          "",
          "tiktok"
        )}
        ${renderPortfolioKpi(
          i18n("historicalSob.kpiPortfolioSobChange", "Portfolio MoM SOB Change"),
          change,
          "May TikTok SOB − April",
          "accent"
        )}
      </div>`;
  }

  function renderSobStackedSeg(platform, pct, gmvLabel, compact, animate) {
    const label = platform === "shp" ? "Shopee" : "TikTok";
    const width = animate ? 0 : pct;
    const compactCls = compact ? " is-compact" : "";
    const platCls = platform === "shp" ? "si-sob-stack-seg--shp" : "si-sob-stack-seg--tk";
    return `
      <div class="si-sob-stack-seg ${platCls}${compactCls}" style="width:${width}%" tabindex="0">
        <span class="si-sob-seg-label">${label} ${fmtPct(pct)}</span>
        <span class="si-sob-tip" role="tooltip">
          <span class="si-sob-tip-title">${label}</span>
          <span class="si-sob-tip-row">GMV ${escapeHtml(gmvLabel || "—")}</span>
          <span class="si-sob-tip-row">SOB ${fmtPct(pct)}</span>
        </span>
      </div>`;
  }

  function renderSobPeriodBlock(periodLabel, shpPct, tkPct, shpGmv, tkGmv, animate) {
    const shp = clampSobPct(shpPct);
    const tk = clampSobPct(tkPct);
    if (shp == null || tk == null) return `<p class="si-v1-empty">${fmtNa("SOB unavailable")}</p>`;
    const shpCompact = shp < SOB_INBAR_MIN;
    const tkCompact = tk < SOB_INBAR_MIN;
    const showBarAnnotations = shpCompact || tkCompact;
    return `
      <section class="si-sob-period-block">
        <div class="si-sob-period-label">${escapeHtml(periodLabel)}</div>
        <div class="si-sob-metrics">
          <div class="si-sob-metric si-sob-metric--shp">
            <span class="si-sob-metric-dot" aria-hidden="true"></span>
            <span class="si-sob-metric-name">Shopee</span>
            <strong class="si-sob-metric-pct">${fmtPct(shp)}</strong>
          </div>
          <div class="si-sob-metric si-sob-metric--tk">
            <span class="si-sob-metric-dot" aria-hidden="true"></span>
            <span class="si-sob-metric-name">TikTok</span>
            <strong class="si-sob-metric-pct">${fmtPct(tk)}</strong>
          </div>
        </div>
        ${
          showBarAnnotations
            ? `<div class="si-sob-bar-annotations">
          <span class="si-sob-bar-annotation si-sob-bar-annotation--shp" style="width:${shp}%">${shpCompact ? `Shopee ${fmtPct(shp)}` : ""}</span>
          <span class="si-sob-bar-annotation si-sob-bar-annotation--tk" style="width:${tk}%">${tkCompact ? `TikTok ${fmtPct(tk)}` : ""}</span>
        </div>`
            : ""
        }
        <div class="si-sob-stack-bar" data-sob-animate="${animate ? "1" : "0"}" data-shp="${shp}" data-tk="${tk}">
          ${renderSobStackedSeg("shp", shp, fmtGmv(shpGmv), shpCompact, animate)}
          ${renderSobStackedSeg("tk", tk, fmtGmv(tkGmv), tkCompact, animate)}
        </div>
      </section>`;
  }

  function renderTrendChart(row) {
    const apr = clampSobPct(row.april_tiktok_sob_percent);
    const may = clampSobPct(row.may_tiktok_sob_percent);
    if (apr == null && may == null) {
      return `<p class="si-v1-empty">${escapeHtml(i18n("historicalSob.trendNa", "Trend unavailable"))}</p>`;
    }
    const max = Math.max(apr || 0, may || 0, 1);
    const aprH = apr == null ? 0 : (apr / max) * 100;
    const mayH = may == null ? 0 : (may / max) * 100;
    return `
      <div class="hs-trend-chart" aria-label="TikTok SOB trend April vs May">
        <div class="hs-trend-col">
          <div class="hs-trend-bar hs-trend-bar--apr" style="height:${aprH}%"></div>
          <span class="hs-trend-label">Apr</span>
          <span class="hs-trend-value">${fmtPct(apr)}</span>
        </div>
        <div class="hs-trend-col">
          <div class="hs-trend-bar hs-trend-bar--may" style="height:${mayH}%"></div>
          <span class="hs-trend-label">May</span>
          <span class="hs-trend-value">${fmtPct(may)}</span>
        </div>
      </div>`;
  }

  function renderHistoricalSobCards(row) {
    return `
      <div class="hs-detail-kpi-grid">
        <article class="si-port-kpi si-port-kpi--shopee">
          <div class="si-port-kpi-label">April Shopee GMV</div>
          <div class="si-port-kpi-value">${escapeHtml(fmtGmv(row.april_shopee_gmv) || "N/A")}</div>
        </article>
        <article class="si-port-kpi si-port-kpi--tiktok">
          <div class="si-port-kpi-label">April TikTok GMV</div>
          <div class="si-port-kpi-value">${escapeHtml(fmtGmv(row.april_tiktok_gmv) || "N/A")}</div>
        </article>
        <article class="si-port-kpi si-port-kpi--shopee">
          <div class="si-port-kpi-label">May Shopee GMV</div>
          <div class="si-port-kpi-value">${escapeHtml(fmtGmv(row.may_shopee_gmv) || "N/A")}</div>
        </article>
        <article class="si-port-kpi si-port-kpi--tiktok">
          <div class="si-port-kpi-label">May TikTok GMV</div>
          <div class="si-port-kpi-value">${escapeHtml(fmtGmv(row.may_tiktok_gmv) || "N/A")}</div>
        </article>
        <article class="si-port-kpi si-port-kpi--accent">
          <div class="si-port-kpi-label">SOB Change</div>
          <div class="si-port-kpi-value">${escapeHtml(fmtChange(row.sob_change_pp))}</div>
        </article>
      </div>`;
  }

  function renderDetailPanel(row) {
    const aprBlock = renderSobPeriodBlock(
      "April",
      row.april_shopee_sob_percent,
      row.april_tiktok_sob_percent,
      row.april_shopee_gmv,
      row.april_tiktok_gmv,
      true
    );
    const mayBlock = renderSobPeriodBlock(
      "May",
      row.may_shopee_sob_percent,
      row.may_tiktok_sob_percent,
      row.may_shopee_gmv,
      row.may_tiktok_gmv,
      true
    );
    const divider =
      aprBlock && mayBlock ? `<div class="si-biz-sob-card-divider" role="presentation"></div>` : "";

    return `
      <div class="si-biz-detail-panel">
        <h3 class="si-section-title">${escapeHtml(i18n("historicalSob.detailMapping", "Mapping"))}</h3>
        <dl class="si-detail-grid si-detail-grid--compact">
          <div class="si-detail-cell"><dt>TikTok Shop Name</dt><dd>${fmtDetail(row.tiktok_shop_name)}</dd></div>
          <div class="si-detail-cell"><dt>FastMoss Matched Shop</dt><dd>${fmtDetail(row.fastmoss_shop_name)}</dd></div>
          <div class="si-detail-cell"><dt>Mapping Status</dt><dd>${mappingReviewBadge(row)}</dd></div>
          <div class="si-detail-cell"><dt>Category</dt><dd>${fmtDetail(row.category || i18n("historicalSob.uncategorized", "Uncategorized"))}</dd></div>
        </dl>
        <div class="si-biz-sob-card">
          <div class="si-biz-sob-card-head">
            <h4 class="si-biz-sob-card-title">${escapeHtml(i18n("historicalSob.detailSob", "Historical SOB Analysis"))}</h4>
          </div>
          <div class="si-biz-sob-card-body">
            ${renderHistoricalSobCards(row)}
            ${aprBlock}
            ${divider}
            ${mayBlock}
            <h4 class="hs-detail-subtitle">${escapeHtml(i18n("historicalSob.detailTrend", "TikTok SOB trend"))}</h4>
            ${renderTrendChart(row)}
          </div>
        </div>
      </div>`;
  }

  function cellGmv(value, reason) {
    const g = fmtGmv(value);
    if (g == null) return fmtNa(reason);
    return escapeHtml(g);
  }

  function cellSob(value) {
    if (value == null || Number.isNaN(Number(value))) {
      return fmtNa("SOB requires Shopee and TikTok GMV");
    }
    return escapeHtml(fmtPct(value));
  }

  function renderTableRow(row, isExpanded) {
    const expCls = isExpanded ? " is-expanded" : "";
    return `
      <tbody class="si-biz-group${expCls}" data-shop-id="${escapeHtml(row.shop_id)}">
        <tr class="si-biz-row-head" data-toggle-row>
          <td class="si-biz-toggle-cell"><span class="si-biz-toggle" aria-hidden="true">▶</span></td>
          <td>${escapeHtml(row.shop_id)}</td>
          <td class="si-biz-name">${escapeHtml(row.shop_name)}</td>
          <td>${mappingReviewBadge(row)}</td>
          <td class="si-v1-num">${cellGmv(row.april_shopee_gmv, row.shopee_na_reason)}</td>
          <td class="si-v1-num">${cellGmv(row.april_tiktok_gmv, row.tiktok_na_reason)}</td>
          <td class="si-v1-num">${cellSob(row.april_shopee_sob_percent)}</td>
          <td class="si-v1-num">${cellSob(row.april_tiktok_sob_percent)}</td>
          <td class="si-v1-num">${cellGmv(row.may_shopee_gmv, row.shopee_na_reason)}</td>
          <td class="si-v1-num">${cellGmv(row.may_tiktok_gmv, row.tiktok_na_reason)}</td>
          <td class="si-v1-num">${cellSob(row.may_shopee_sob_percent)}</td>
          <td class="si-v1-num">${cellSob(row.may_tiktok_sob_percent)}</td>
          <td class="si-v1-num">${escapeHtml(fmtChange(row.sob_change_pp))}</td>
        </tr>
        <tr class="si-biz-row-detail">
          <td colspan="13">${renderDetailPanel(row)}</td>
        </tr>
      </tbody>`;
  }

  function renderTable(rows) {
    if (!rows.length) {
      return `<p class="si-v1-empty">${escapeHtml(i18n("historicalSob.emptySellers", "No sellers match the current filters."))}</p>`;
    }
    return `
      <div class="si-v1-table-wrap si-v1-table-wrap--wide">
        <table class="si-v1-table si-v1-table--business">
          <thead>
            <tr>
              <th class="si-biz-toggle-cell" aria-label="Expand row"></th>
              <th>Shop ID</th>
              <th>Shop Name</th>
              <th>Mapping Status</th>
              <th>April Shopee GMV</th>
              <th>April TikTok GMV</th>
              <th>April Shopee SOB</th>
              <th>April TikTok SOB</th>
              <th>May Shopee GMV</th>
              <th>May TikTok GMV</th>
              <th>May Shopee SOB</th>
              <th>May TikTok SOB</th>
              <th>SOB Change</th>
            </tr>
          </thead>
          ${rows.map((r) => renderTableRow(r, expanded.has(r.shop_id))).join("")}
        </table>
      </div>`;
  }

  function toolbarHtml(f) {
    const categories = payload?.filters?.categories || [];
    const catOpts = [
      `<option value="all">${escapeHtml(i18n("historicalSob.categoryAll", "All"))}</option>`,
      ...categories.map(
        (c) =>
          `<option value="${escapeHtml(c)}"${f.category === c ? " selected" : ""}>${escapeHtml(c)}</option>`
      ),
    ].join("");

    return `
      <div class="si-v1-toolbar" data-toolbar="historical-sob">
        <div class="si-v1-toolbar-field si-v1-toolbar-field--search">
          <label for="hsFilterSearch">${escapeHtml(i18n("historicalSob.filterSearch", "Seller search"))}</label>
          <input id="hsFilterSearch" type="search" placeholder="${escapeHtml(i18n("historicalSob.filterSearchPh", "Shop ID, name, TikTok…"))}" value="${escapeHtml(f.q)}" data-f="q" />
        </div>
        <div class="si-v1-toolbar-field">
          <label for="hsFilterMapped">${escapeHtml(i18n("historicalSob.filterStatus", "Status"))}</label>
          <select id="hsFilterMapped" data-f="mapped">
            <option value="all"${f.mapped === "all" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.statusAll", "All"))}</option>
            <option value="mapped"${f.mapped === "mapped" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.statusMapped", "Mapped"))}</option>
            <option value="not_mapped"${f.mapped === "not_mapped" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.statusNotMapped", "Not Mapped"))}</option>
          </select>
        </div>
        <div class="si-v1-toolbar-field">
          <label for="hsFilterCategory">${escapeHtml(i18n("historicalSob.filterCategory", "Category"))}</label>
          <select id="hsFilterCategory" data-f="category">${catOpts}</select>
        </div>
        <div class="si-v1-toolbar-field">
          <label for="hsFilterSort">${escapeHtml(i18n("historicalSob.filterSort", "Sort"))}</label>
          <select id="hsFilterSort" data-f="sort">
            <option value="shop_name"${f.sort === "shop_name" ? " selected" : ""}>Shop name</option>
            <option value="tiktok_sob"${f.sort === "tiktok_sob" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.sortTiktokSob", "Highest TikTok SOB"))}</option>
            <option value="shopee_sob"${f.sort === "shopee_sob" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.sortShopeeSob", "Highest Shopee SOB"))}</option>
            <option value="sob_change"${f.sort === "sob_change" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.sortChange", "Largest Change"))}</option>
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

  function bindRowToggles(listEl) {
    listEl.querySelectorAll("[data-toggle-row]").forEach((head) => {
      head.addEventListener("click", () => {
        const row = head.closest("[data-shop-id]");
        const id = row?.dataset?.shopId;
        if (!id) return;
        if (expanded.has(id)) expanded.delete(id);
        else expanded.add(id);
        row.classList.toggle("is-expanded");
        if (row.classList.contains("is-expanded")) animateSobBars(row);
      });
    });
  }

  function animateSobBars(root) {
    requestAnimationFrame(() => {
      root.querySelectorAll('.si-sob-stack-bar[data-sob-animate="1"]').forEach((bar) => {
        const shp = parseFloat(bar.dataset.shp) || 0;
        const tk = parseFloat(bar.dataset.tk) || 0;
        const segs = bar.querySelectorAll(".si-sob-stack-seg");
        if (segs.length < 2) return;
        segs[0].style.width = "0%";
        segs[1].style.width = "0%";
        bar.offsetHeight;
        segs[0].style.width = `${shp}%`;
        segs[1].style.width = `${tk}%`;
      });
    });
  }

  function paintList() {
    if (!contentEl || !payload) return;
    const kpiEl = contentEl.querySelector("[data-hs-kpis]");
    if (kpiEl) kpiEl.innerHTML = renderKpiGrid();

    const listEl = contentEl.querySelector("[data-hs-list]");
    const toolbarEl = contentEl.querySelector("[data-toolbar]");
    if (!listEl || !toolbarEl) return;

    const all = payload.sellers || [];
    const filtered = filterSellers(all);
    const countEl = toolbarEl.querySelector("[data-result-count]");
    if (countEl) {
      countEl.textContent = `Showing ${filtered.length} of ${all.length} sellers`;
    }
    if (!filtered.length) {
      listEl.innerHTML = `<p class="si-v1-empty">${escapeHtml(i18n("historicalSob.emptySellers", "No sellers match the current filters."))}</p>`;
      return;
    }
    listEl.innerHTML = renderTable(filtered);
    bindRowToggles(listEl);
  }

  function setupShell() {
    if (!contentEl || !payload) return;
    if (!shellReady) {
      contentEl.innerHTML = `
        <div data-hs-kpis class="hs-page-kpis-wrap">${renderKpiGrid()}</div>
        ${toolbarHtml(filters)}
        <div class="si-v1-list" data-hs-list></div>`;

      const onToolbar = (ev) => {
        if (ev?.reset) filters = defaultFilters();
        else filters = readFiltersFromToolbar(contentEl.querySelector("[data-toolbar]"));
        contentEl.querySelector("[data-toolbar]").outerHTML = toolbarHtml(filters);
        bindToolbar(contentEl.querySelector("[data-toolbar]"), onToolbar);
        paintList();
      };
      bindToolbar(contentEl.querySelector("[data-toolbar]"), onToolbar);
      shellReady = true;
    }
    paintList();
  }

  function updateMeta() {
    if (!metaEl || !payload) return;
    metaEl.textContent = [
      i18n("historicalSob.metaPeriod", "April 2026 · May 2026"),
      formatLastUpdated(payload.cache_updated_at || payload.refreshed_at),
      payload.ytd_tab ? `YTD: ${payload.ytd_tab}` : "",
    ]
      .filter(Boolean)
      .join(" · ");
  }

  function showLoading() {
    shellReady = false;
    expanded.clear();
    if (contentEl) {
      contentEl.innerHTML = `
        <div class="si-port-state si-port-state--loading" role="status" aria-live="polite">
          <div class="si-port-state-spinner" aria-hidden="true"></div>
          <p class="si-port-state-title">${escapeHtml(i18n("historicalSob.loading", "Loading Historical SOB…"))}</p>
        </div>`;
    }
    if (metaEl) metaEl.textContent = i18n("historicalSob.loadingMeta", "Loading…");
  }

  function showError(message) {
    shellReady = false;
    if (contentEl) {
      contentEl.innerHTML = `
        <div class="si-port-state si-port-state--error" role="alert">
          <p class="si-port-state-title">${escapeHtml(i18n("historicalSob.loadError", "Could not load Historical SOB"))}</p>
          <p class="si-port-state-message">${escapeHtml(message || "Unknown error")}</p>
          <button type="button" class="btn si-v1-action-btn" data-hs-retry>${escapeHtml(i18n("historicalSob.retry", "Retry"))}</button>
        </div>`;
      contentEl.querySelector("[data-hs-retry]")?.addEventListener("click", () => {
        load(true).catch(() => {});
      });
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

  async function refreshData() {
    const defaultLabel = i18n("si.refreshData", "Refresh Data");
    if (refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.classList.add("is-loading");
      refreshBtn.textContent = i18n("si.dataRefreshing", "Refreshing…");
    }
    try {
      let data;
      if (window.ShpPlatform?.refreshAllSheetData) {
        data = await window.ShpPlatform.refreshAllSheetData();
      } else {
        data = await fetchApi("/api/intelligence/v1/refresh-data", { method: "POST" });
      }
      if (summaryEl) {
        summaryEl.textContent = formatMappingSummary(data);
        summaryEl.classList.remove("hidden");
      }
      payload = null;
      shellReady = false;
      expanded.clear();
      await load(true);
      return data;
    } catch (err) {
      window.ShpPlatform?.showPlatformToast?.(err.message || "Refresh failed", "error");
      throw err;
    } finally {
      if (refreshBtn) {
        refreshBtn.disabled = false;
        refreshBtn.classList.remove("is-loading");
        refreshBtn.textContent = defaultLabel;
      }
    }
  }

  function init() {
    load(false).catch(() => {});
  }

  function clearCache() {
    payload = null;
    shellReady = false;
    expanded.clear();
    filters = defaultFilters();
  }

  refreshBtn?.addEventListener("click", () => {
    refreshData().catch(() => {});
  });

  window.ShpHistoricalSob = { init, load, clearCache, refreshData };
})();
