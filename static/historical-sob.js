/**
 * Historical SOB — Section 1: portfolio summary + Section 2: seller drill-down.
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

  function renderPortfolioCard(label, value, accent) {
    const accentCls = accent ? ` hs-portfolio-card--${accent}` : "";
    return `
      <article class="hs-portfolio-card${accentCls}">
        <span class="hs-portfolio-card-label">${escapeHtml(label)}</span>
        <strong class="hs-portfolio-card-value">${value}</strong>
      </article>`;
  }

  function renderSobCompareRow(platform, pct) {
    const width =
      pct == null || Number.isNaN(Number(pct)) ? 0 : Math.max(0, Math.min(100, Number(pct)));
    const variant = platform === "Shopee" ? "shopee" : "tiktok";
    return `
      <div class="hs-sob-compare-row hs-sob-compare-row--${variant}">
        <span class="hs-sob-compare-platform">${escapeHtml(platform)}</span>
        <div class="hs-sob-compare-track" aria-hidden="true">
          <span class="hs-sob-compare-fill" data-target-width="${width}" style="width:0%"></span>
        </div>
        <span class="hs-sob-compare-pct">${escapeHtml(fmtPct(pct))}</span>
      </div>`;
  }

  function renderSobCompareMonth(title, shopeePct, tiktokPct) {
    return `
      <div class="hs-sob-compare-month">
        <h3 class="hs-sob-compare-month-title">${escapeHtml(title)}</h3>
        ${renderSobCompareRow("Shopee", shopeePct)}
        ${renderSobCompareRow("TikTok", tiktokPct)}
      </div>`;
  }

  function renderSobCompareBars(portfolio) {
    if (!portfolio) {
      return `<p class="si-v1-empty">${escapeHtml(i18n("historicalSob.sobBarsNa", "SOB comparison unavailable"))}</p>`;
    }
    const aprShp = portfolio.april_shopee_sob_percent;
    const aprTk = portfolio.april_tiktok_sob_percent;
    const mayShp = portfolio.may_shopee_sob_percent;
    const mayTk = portfolio.may_tiktok_sob_percent;
    if ([aprShp, aprTk, mayShp, mayTk].every((v) => v == null)) {
      return `<p class="si-v1-empty">${escapeHtml(i18n("historicalSob.sobBarsNa", "SOB comparison unavailable"))}</p>`;
    }
    return `
      <div class="hs-sob-compare" data-hs-sob-bars>
        ${renderSobCompareMonth("April", aprShp, aprTk)}
        ${renderSobCompareMonth("May", mayShp, mayTk)}
      </div>`;
  }

  function animateSobCompareBars(root) {
    requestAnimationFrame(() => {
      root.querySelectorAll(".hs-sob-compare-fill[data-target-width]").forEach((bar) => {
        const target = bar.getAttribute("data-target-width") || "0";
        bar.style.width = "0%";
        bar.offsetHeight;
        bar.style.width = `${target}%`;
      });
    });
  }

  function renderPortfolioSection() {
    const kpis = payload?.kpis || {};
    const portfolio = payload?.portfolio || {};
    const warnings = payload?.warnings || [];
    const warnHtml = warnings.length
      ? `<div class="hs-warnings" role="status"><ul>${warnings
          .map((w) => `<li>${escapeHtml(w)}</li>`)
          .join("")}</ul></div>`
      : "";

    return `
      ${warnHtml}
      <section class="hs-section hs-section--portfolio" aria-label="Overall portfolio summary">
        <h2 class="hs-section-title">${escapeHtml(i18n("historicalSob.sectionPortfolio", "Overall Portfolio Summary"))}</h2>
        <div class="hs-portfolio-cards">
          ${renderPortfolioCard(
            i18n("historicalSob.kpiAprShopee", "April Shopee GMV"),
            escapeHtml(fmtGmv(kpis.april_shopee_gmv)),
            "shopee"
          )}
          ${renderPortfolioCard(
            i18n("historicalSob.kpiAprTiktok", "April TikTok GMV"),
            escapeHtml(fmtGmv(kpis.april_tiktok_gmv)),
            "tiktok"
          )}
          ${renderPortfolioCard(
            i18n("historicalSob.kpiAprSob", "April SOB %"),
            escapeHtml(fmtPct(kpis.april_portfolio_sob_percent)),
            "sob"
          )}
          ${renderPortfolioCard(
            i18n("historicalSob.kpiMayShopee", "May Shopee GMV"),
            escapeHtml(fmtGmv(kpis.may_shopee_gmv)),
            "shopee"
          )}
          ${renderPortfolioCard(
            i18n("historicalSob.kpiMayTiktok", "May TikTok GMV"),
            escapeHtml(fmtGmv(kpis.may_tiktok_gmv)),
            "tiktok"
          )}
          ${renderPortfolioCard(
            i18n("historicalSob.kpiMaySob", "May SOB %"),
            escapeHtml(fmtPct(kpis.may_portfolio_sob_percent)),
            "sob"
          )}
          ${renderPortfolioCard(
            i18n("historicalSob.kpiSobChange", "SOB Change %"),
            escapeHtml(fmtChange(kpis.portfolio_sob_change_pp)),
            "change"
          )}
        </div>
        <div class="hs-portfolio-bars-wrap">
          <h3 class="hs-portfolio-bars-title">${escapeHtml(
            i18n("historicalSob.sobCompareTitle", "Shopee vs TikTok share — April vs May")
          )}</h3>
          ${renderSobCompareBars(portfolio)}
        </div>
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

  function paintPortfolioSection() {
    const portfolioEl = contentEl?.querySelector("[data-hs-portfolio]");
    if (!portfolioEl || !payload) return;
    portfolioEl.innerHTML = renderPortfolioSection();
    const barsRoot = portfolioEl.querySelector("[data-hs-sob-bars]");
    if (barsRoot) animateSobCompareBars(barsRoot);
  }

  function paintSellerSection() {
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
        <div data-hs-portfolio class="hs-portfolio-fixed"></div>
        <section class="hs-section hs-section--sellers">
          <h2 class="hs-section-title">${escapeHtml(i18n("historicalSob.sectionSellers", "Seller Level Historical SOB"))}</h2>
          ${toolbarHtml(filters)}
          <div class="si-v1-list" data-hs-list></div>
        </section>`;

      const onToolbar = (ev) => {
        if (ev?.reset) {
          filters = defaultFilters();
        } else {
          filters = readFiltersFromToolbar(contentEl.querySelector("[data-toolbar]"));
        }
        const sellerSection = contentEl.querySelector(".hs-section--sellers");
        const toolbar = sellerSection.querySelector("[data-toolbar]");
        toolbar.outerHTML = toolbarHtml(filters);
        bindToolbar(sellerSection.querySelector("[data-toolbar]"), onToolbar);
        paintSellerSection();
      };
      bindToolbar(contentEl.querySelector("[data-toolbar]"), onToolbar);
      shellReady = true;
    }
    paintPortfolioSection();
    paintSellerSection();
  }

  function updateMeta() {
    if (!metaEl || !payload) return;
    metaEl.textContent = [
      i18n("historicalSob.metaPeriod", "April 2026 · May 2026"),
      payload.ytd_tab,
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
