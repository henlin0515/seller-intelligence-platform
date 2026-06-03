/**
 * Historical SOB — complete analysis page (visual parity with Seller Level Analysis).
 */
(function () {
  const API = "/api/intelligence/v1/historical-sob";
  const contentEl = document.getElementById("siHistoricalSobContent");
  const metaEl = document.getElementById("siHistoricalSobMeta");
  const headerLastUpdatedEl = document.getElementById("siHistoricalSobLastUpdated");

  const SOB_INBAR_MIN = 14;

  let payload = null;
  let shellReady = false;
  let expanded = new Set();
  let filters = defaultFilters();
  let slaUpdateListenerBound = false;

  function defaultFilters() {
    return { q: "", rm: "all", gp: "all", status: "all", category: "all", sort: "shop_name" };
  }

  function sheetFilters() {
    return {
      rm: payload?.rm_filter || payload?.sheet_filters?.rm_filter || {
        options: [{ value: "all", label: "All RM" }],
        by_rm: {},
      },
      gp: payload?.gp_filter || payload?.sheet_filters?.gp_filter || {
        options: [{ value: "all", label: "All GP" }],
        by_gp: {},
        gp_names_by_rm: {},
      },
    };
  }

  function gpFilterForRm(gpFilter, rmValue) {
    const base = gpFilter || { options: [{ value: "all", label: "All GP" }], by_gp: {} };
    if (!rmValue || rmValue === "all") return base;
    const names = base.gp_names_by_rm?.[rmValue] || [];
    return {
      ...base,
      options: [
        { value: "all", label: "All GP" },
        ...names.map((gp) => ({ value: gp, label: gp })),
      ],
    };
  }

  function coerceGpForRm(f) {
    const sf = sheetFilters();
    const rm = f.rm || "all";
    const gp = f.gp || "all";
    if (rm === "all" || gp === "all") return f;
    const allowed = sf.gp?.gp_names_by_rm?.[rm] || [];
    if (!allowed.includes(gp)) return { ...f, gp: "all" };
    return f;
  }

  function normalizeShopKey(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");
  }

  function matchesRmFilter(s, rmValue, rmFilter) {
    if (!rmValue || rmValue === "all") return true;
    const rmNeedle = String(rmValue).trim().toLowerCase();
    const rowRm = String(s.rm || "").trim().toLowerCase();
    if (rowRm && rmNeedle && rowRm === rmNeedle) return true;
    const allowed = rmFilter?.by_rm?.[rmValue];
    if (!allowed || !allowed.length) return false;
    const set = new Set(allowed);
    const keys = [normalizeShopKey(s.shop_name), normalizeShopKey(s.tiktok_shop_name)].filter(Boolean);
    return keys.some((k) => set.has(k));
  }

  function matchesGpFilter(s, gpValue, gpFilter) {
    if (!gpValue || gpValue === "all") return true;
    const gpNeedle = normalizeShopKey(gpValue);
    if (gpNeedle && normalizeShopKey(s.gp_shop_name) === gpNeedle) return true;
    const allowed = gpFilter?.by_gp?.[gpValue];
    if (!allowed || !allowed.length) return false;
    const set = new Set(allowed);
    const keys = [normalizeShopKey(s.shop_name), normalizeShopKey(s.tiktok_shop_name)].filter(Boolean);
    return keys.some((k) => set.has(k));
  }

  function matchesStatusFilter(row, statusValue) {
    if (!statusValue || statusValue === "all") return true;
    const ps = String(row.platform_source || "NORMAL").toUpperCase();
    const fm = String(row.fastmoss_match_status || "").toUpperCase();
    switch (statusValue) {
      case "shopee_only":
        return ps === "SHOPEE_ONLY";
      case "tiktok_only":
        return ps === "TIKTOK_ONLY";
      case "mapped":
        return ps === "NORMAL" && fm === "MAPPED";
      case "need_review":
        return ps === "NORMAL" && fm === "NEED_REVIEW";
      case "not_found":
        return ps === "NORMAL" && fm === "NOT_FOUND";
      default:
        return true;
    }
  }

  function filterSelectOptionsHtml(filterDef, selected, fallbackLabel) {
    const options = filterDef?.options || [{ value: "all", label: fallbackLabel }];
    return options
      .map(
        (opt) =>
          `<option value="${escapeHtml(opt.value)}"${opt.value === selected ? " selected" : ""}>${escapeHtml(opt.label)}</option>`
      )
      .join("");
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

  function fmtUsd(value) {
    if (value == null || Number.isNaN(Number(value))) return null;
    return `$${fmtNum(value, 2)}`;
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

  function sellerSearchBlob(row) {
    return [
      row.shop_id,
      row.shop_name,
      row.tiktok_shop_name,
      row.fastmoss_shop_name,
      row.gp_shop_id,
      row.gp_shop_name,
      row.rm,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function filterSellers(rows) {
    const q = filters.q.trim().toLowerCase();
    const sf = sheetFilters();
    return sortSellers(
      (rows || []).filter((row) => {
        if (q && !sellerSearchBlob(row).includes(q)) return false;
        if (!matchesRmFilter(row, filters.rm, sf.rm)) return false;
        if (!matchesGpFilter(row, filters.gp, sf.gp)) return false;
        if (!matchesStatusFilter(row, filters.status)) return false;
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
        case "april_sob":
          return cmp(
            b.april_tiktok_sob_percent ?? -1,
            a.april_tiktok_sob_percent ?? -1
          );
        case "may_sob":
          return cmp(b.may_tiktok_sob_percent ?? -1, a.may_tiktok_sob_percent ?? -1);
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

  function fastmossStatusBadge(status) {
    const map = {
      MAPPED: ["si-v1-badge--ok", "Mapped"],
      NEED_REVIEW: ["si-v1-badge--warn", "Need review"],
      NOT_FOUND: ["si-v1-badge--risk", "Not found"],
    };
    const key = String(status || "").toUpperCase();
    const [cls, label] = map[key] || ["si-v1-badge--muted", status || "—"];
    return `<span class="si-v1-badge ${cls}">${escapeHtml(label)}</span>`;
  }

  function platformSourceBadge(row) {
    const source = String(row.platform_source || "NORMAL").toUpperCase();
    if (source === "SHOPEE_ONLY") {
      return `<span class="si-v1-badge si-v1-badge--shopee">Shopee only</span>`;
    }
    if (source === "TIKTOK_ONLY") {
      return `<span class="si-v1-badge si-v1-badge--tiktok">TikTok only</span>`;
    }
    return fastmossStatusBadge(row.fastmoss_match_status);
  }

  function mappingReviewBadge(row) {
    const source = String(row.platform_source || "NORMAL").toUpperCase();
    if (source === "SHOPEE_ONLY" || source === "TIKTOK_ONLY") {
      return platformSourceBadge(row);
    }
    const review = String(row.fastmoss_review_status || "").toUpperCase();
    if (review === "APPROVED") {
      return platformSourceBadge(row);
    }
    const map = {
      PENDING_REVIEW: ["si-v1-badge--warn", "Pending review"],
      REJECTED: ["si-v1-badge--risk", "Rejected"],
    };
    if (map[review]) {
      const [cls, label] = map[review];
      return `<span class="si-v1-badge ${cls}">${escapeHtml(label)}</span>`;
    }
    return platformSourceBadge(row);
  }

  function hsPeriodGmvUsd(row, period, platform) {
    const shpField = period === "april" ? "april_shopee_gmv" : "may_shopee_gmv";
    const tkField = period === "april" ? "april_tiktok_gmv" : "may_tiktok_gmv";
    const field = platform === "shp" ? shpField : tkField;
    const v = row[field];
    if (v == null || v === "" || Number.isNaN(Number(v))) return 0;
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : 0;
  }

  /** Summary SOB from summed monthly GMV — never averages row SOB %. */
  function computeHsSummarySob(sellers, period) {
    let shopeeGmv = 0;
    let tiktokGmv = 0;
    for (const s of sellers || []) {
      shopeeGmv += hsPeriodGmvUsd(s, period, "shp");
      tiktokGmv += hsPeriodGmvUsd(s, period, "tk");
    }
    const total = shopeeGmv + tiktokGmv;
    if (total <= 0) return { kind: "na" };
    return {
      kind: "values",
      shpPct: (shopeeGmv / total) * 100,
      tkPct: (tiktokGmv / total) * 100,
    };
  }

  function renderHsSobLegendBar(shpPct, tkPct) {
    const shp = clampSobPct(shpPct);
    const tk = clampSobPct(tkPct);
    if (shp == null || tk == null) return "";
    return `
        <div class="hs-inline-sob-legend">
          <span class="hs-inline-sob-tag hs-inline-sob-tag--shp">
            <span class="hs-inline-sob-dot" aria-hidden="true"></span>SHP ${fmtPct(shp)}
          </span>
          <span class="hs-inline-sob-tag hs-inline-sob-tag--tk">
            <span class="hs-inline-sob-dot" aria-hidden="true"></span>TK ${fmtPct(tk)}
          </span>
        </div>
        <div class="si-sob-stack-bar hs-inline-sob-bar si-sla-summary-sob-bar" data-shp="${shp}" data-tk="${tk}">
          <div class="si-sob-stack-seg si-sob-stack-seg--shp" style="width:${shp}%"></div>
          <div class="si-sob-stack-seg si-sob-stack-seg--tk" style="width:${tk}%"></div>
        </div>`;
  }

  function renderHsSummaryCard(title, { prompt, selection, aprilSob, maySob }) {
    const head = `<h3 class="si-sla-summary-card__title">${escapeHtml(title)}</h3>`;
    if (prompt) {
      return `<article class="si-sla-summary-card">${head}<p class="si-sla-summary-card__prompt">${escapeHtml(prompt)}</p></article>`;
    }
    const sel = selection ? `<p class="si-sla-summary-card__sel">${escapeHtml(selection)}</p>` : "";
    const periodBlock = (label, sob) => {
      if (sob?.kind !== "values") {
        return `<div class="hs-summary-period"><span class="hs-summary-period-label">${escapeHtml(label)}</span>${fmtNa("SOB N/A")}</div>`;
      }
      return `<div class="hs-summary-period"><span class="hs-summary-period-label">${escapeHtml(label)}</span>${renderHsSobLegendBar(sob.shpPct, sob.tkPct)}</div>`;
    };
    return `<article class="si-sla-summary-card">
      ${head}${sel}
      <div class="hs-summary-periods">
        ${periodBlock("April", aprilSob)}
        ${periodBlock("May", maySob)}
      </div>
    </article>`;
  }

  function renderHsCategorySobCard(categoryName, matchedCount, aprilSob, maySob) {
    const head = `<h4 class="si-sla-summary-card__title">${escapeHtml(categoryName)}</h4>`;
    const countLine = `<p class="si-sla-summary-card__count">${fmtNum(matchedCount)} shops in scope</p>`;
    const periodBlock = (label, sob) => {
      if (sob?.kind !== "values") {
        return `<div class="hs-summary-period hs-summary-period--compact"><span>${escapeHtml(label)}</span> ${fmtNa("N/A")}</div>`;
      }
      return `<div class="hs-summary-period hs-summary-period--compact"><span>${escapeHtml(label)}</span> SHP ${fmtPct(sob.shpPct)} · TK ${fmtPct(sob.tkPct)}</div>`;
    };
    return `<article class="si-sla-summary-card si-sla-summary-card--category">
      ${head}${countLine}
      ${periodBlock("Apr", aprilSob)}
      ${periodBlock("May", maySob)}
    </article>`;
  }

  function hsFilteredScopeLabel(filtered, f) {
    const n = filtered.length;
    const bits = [`${n} shop${n === 1 ? "" : "s"}`];
    if (f.gp && f.gp !== "all") bits.push(`GP: ${f.gp}`);
    if (f.rm && f.rm !== "all") bits.push(`RM: ${f.rm}`);
    if (f.category && f.category !== "all") bits.push(f.category);
    if (f.status && f.status !== "all") bits.push(f.status.replace(/_/g, " "));
    if (f.q?.trim()) bits.push("search");
    return bits.join(" · ");
  }

  function businessCategoryMapping() {
    return payload?.category_mapping || { categories: [], loaded: false };
  }

  function sellersForCategoryKeys(sellers, shopKeys) {
    const set = new Set(shopKeys || []);
    if (!set.size) return [];
    return (sellers || []).filter((s) => {
      const keys = [normalizeShopKey(s.shop_name), normalizeShopKey(s.tiktok_shop_name)].filter(Boolean);
      return keys.some((k) => set.has(k));
    });
  }

  function paintHistoricalSummarySob() {
    const summaryEl = contentEl?.querySelector("[data-hs-summary-sob]");
    if (!summaryEl || !payload) return;

    const sellers = payload.sellers || [];
    const f = filters;
    const filtered = filterSellers(sellers);
    const scopeLabel = hsFilteredScopeLabel(filtered, f);
    const aprilScope = computeHsSummarySob(filtered, "april");
    const mayScope = computeHsSummarySob(filtered, "may");

    const overallCard = renderHsSummaryCard("Overall SOB", {
      selection: scopeLabel,
      aprilSob: aprilScope,
      maySob: mayScope,
    });

    let gpCard;
    if (!f.gp || f.gp === "all") {
      gpCard = renderHsSummaryCard("GP SOB", { prompt: "Select GP to view GP SOB" });
    } else {
      gpCard = renderHsSummaryCard("GP SOB", {
        selection: `${f.gp} · ${scopeLabel}`,
        aprilSob: aprilScope,
        maySob: mayScope,
      });
    }

    let rmCard;
    if (!f.rm || f.rm === "all") {
      rmCard = renderHsSummaryCard("RM SOB", { prompt: "Select RM to view RM SOB" });
    } else {
      rmCard = renderHsSummaryCard("RM SOB", {
        selection: `${f.rm} · ${scopeLabel}`,
        aprilSob: aprilScope,
        maySob: mayScope,
      });
    }

    const categories = businessCategoryMapping().categories || [];
    const filteredIds = new Set(filtered.map((s) => String(s.shop_id)));
    let categorySection = "";
    if (!categories.length) {
      categorySection = `<section class="si-sla-category-sob" data-hs-category-sob>
        <h3 class="si-sla-category-sob__heading">Category SOB</h3>
        <p class="si-sla-category-sob__empty">Category mapping not loaded from sheet.</p>
      </section>`;
    } else {
      const categoryCards = categories
        .map((cat) => {
          const matched = sellersForCategoryKeys(sellers, cat.shop_keys).filter((s) =>
            filteredIds.has(String(s.shop_id))
          );
          return renderHsCategorySobCard(
            cat.name,
            matched.length,
            computeHsSummarySob(matched, "april"),
            computeHsSummarySob(matched, "may")
          );
        })
        .join("");
      categorySection = `<section class="si-sla-category-sob" data-hs-category-sob>
        <h3 class="si-sla-category-sob__heading">Category SOB</h3>
        <div class="si-sla-category-grid">${categoryCards}</div>
      </section>`;
    }

    summaryEl.innerHTML = `${categorySection}<div class="si-sla-summary-grid hs-summary-grid">${overallCard}${gpCard}${rmCard}</div>`;
    animateSobBars(summaryEl);
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
    const gmv = (v) => escapeHtml(fmtUsd(v) || "N/A");
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
          ${renderSobStackedSeg("shp", shp, fmtUsd(shpGmv), shpCompact, animate)}
          ${renderSobStackedSeg("tk", tk, fmtUsd(tkGmv), tkCompact, animate)}
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
          <div class="si-port-kpi-value">${escapeHtml(fmtUsd(row.april_shopee_gmv) || "N/A")}</div>
        </article>
        <article class="si-port-kpi si-port-kpi--tiktok">
          <div class="si-port-kpi-label">April TikTok GMV</div>
          <div class="si-port-kpi-value">${escapeHtml(fmtUsd(row.april_tiktok_gmv) || "N/A")}</div>
        </article>
        <article class="si-port-kpi si-port-kpi--shopee">
          <div class="si-port-kpi-label">May Shopee GMV</div>
          <div class="si-port-kpi-value">${escapeHtml(fmtUsd(row.may_shopee_gmv) || "N/A")}</div>
        </article>
        <article class="si-port-kpi si-port-kpi--tiktok">
          <div class="si-port-kpi-label">May TikTok GMV</div>
          <div class="si-port-kpi-value">${escapeHtml(fmtUsd(row.may_tiktok_gmv) || "N/A")}</div>
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
          <div class="si-detail-cell"><dt>FastMoss Status</dt><dd>${fastmossStatusBadge(row.fastmoss_match_status)}</dd></div>
          <div class="si-detail-cell"><dt>Review Status</dt><dd>${fmtDetail(row.fastmoss_review_status || "—")}</dd></div>
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
    const g = fmtUsd(value);
    if (g == null) return fmtNa(reason);
    return escapeHtml(g);
  }

  function renderInlineSobBarCell(shpPct, tkPct) {
    const shp = clampSobPct(shpPct);
    const tk = clampSobPct(tkPct);
    if (shp == null || tk == null) {
      return `<td class="hs-sob-bar-cell">${fmtNa("SOB requires Shopee and TikTok GMV")}</td>`;
    }
    return `
      <td class="hs-sob-bar-cell">
        <div class="hs-inline-sob">
          <div class="hs-inline-sob-legend">
            <span class="hs-inline-sob-tag hs-inline-sob-tag--shp">
              <span class="hs-inline-sob-dot" aria-hidden="true"></span>SHP ${fmtPct(shp)}
            </span>
            <span class="hs-inline-sob-tag hs-inline-sob-tag--tk">
              <span class="hs-inline-sob-dot" aria-hidden="true"></span>TK ${fmtPct(tk)}
            </span>
          </div>
          <div class="si-sob-stack-bar hs-inline-sob-bar" data-sob-animate="1" data-shp="${shp}" data-tk="${tk}">
            <div class="si-sob-stack-seg si-sob-stack-seg--shp" style="width:0%" aria-hidden="true"></div>
            <div class="si-sob-stack-seg si-sob-stack-seg--tk" style="width:0%" aria-hidden="true"></div>
          </div>
        </div>
      </td>`;
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
          ${renderInlineSobBarCell(row.april_shopee_sob_percent, row.april_tiktok_sob_percent)}
          ${renderInlineSobBarCell(row.may_shopee_sob_percent, row.may_tiktok_sob_percent)}
          <td class="si-v1-num">${escapeHtml(fmtChange(row.sob_change_pp))}</td>
          <td class="si-v1-num">${cellGmv(row.april_shopee_gmv, row.shopee_na_reason)}</td>
          <td class="si-v1-num">${cellGmv(row.april_tiktok_gmv, row.tiktok_na_reason)}</td>
          <td class="si-v1-num">${cellGmv(row.may_shopee_gmv, row.shopee_na_reason)}</td>
          <td class="si-v1-num">${cellGmv(row.may_tiktok_gmv, row.tiktok_na_reason)}</td>
        </tr>
        <tr class="si-biz-row-detail">
          <td colspan="11">${renderDetailPanel(row)}</td>
        </tr>
      </tbody>`;
  }

  function renderTable(rows) {
    if (!rows.length) {
      return `<p class="si-v1-empty">${escapeHtml(i18n("historicalSob.emptySellers", "No sellers match the current filters."))}</p>`;
    }
    return `
      <div class="si-v1-table-wrap si-v1-table-wrap--wide">
        <table class="si-v1-table si-v1-table--business hs-seller-table">
          <thead>
            <tr>
              <th class="si-biz-toggle-cell" aria-label="Expand row"></th>
              <th>Shop ID</th>
              <th>Shop Name</th>
              <th>Mapping Status</th>
              <th class="hs-sob-bar-col">APR SOB BAR</th>
              <th class="hs-sob-bar-col">MAY SOB BAR</th>
              <th>SOB Change %</th>
              <th>April Shopee GMV</th>
              <th>April TikTok GMV</th>
              <th>May Shopee GMV</th>
              <th>May TikTok GMV</th>
            </tr>
          </thead>
          ${rows.map((r) => renderTableRow(r, expanded.has(r.shop_id))).join("")}
        </table>
      </div>`;
  }

  function categoryOptionsHtml(f) {
    const categories = payload?.filters?.categories || [];
    return [
      `<option value="all">${escapeHtml(i18n("historicalSob.categoryAll", "All"))}</option>`,
      ...categories.map(
        (c) =>
          `<option value="${escapeHtml(c)}"${f.category === c ? " selected" : ""}>${escapeHtml(c)}</option>`
      ),
    ].join("");
  }

  function toolbarFieldsHtml(f) {
    const sf = sheetFilters();
    const gpDef = gpFilterForRm(sf.gp, f.rm);
    return `
          <div class="si-v1-toolbar-field si-v1-toolbar-field--search">
            <label for="hsFilterSearch">${escapeHtml(i18n("historicalSob.filterSearch", "Search"))}</label>
            <input id="hsFilterSearch" type="search" placeholder="${escapeHtml(i18n("historicalSob.filterSearchPh", "Shop ID, name, TikTok…"))}" value="${escapeHtml(f.q)}" data-f="q" />
          </div>
          <div class="si-v1-toolbar-field">
            <label for="hsFilterRm">RM</label>
            <select id="hsFilterRm" data-f="rm">${filterSelectOptionsHtml(sf.rm, f.rm, "All RM")}</select>
          </div>
          <div class="si-v1-toolbar-field">
            <label for="hsFilterGp">GP</label>
            <select id="hsFilterGp" data-f="gp">${filterSelectOptionsHtml(gpDef, f.gp, "All GP")}</select>
          </div>
          <div class="si-v1-toolbar-field">
            <label for="hsFilterStatus">${escapeHtml(i18n("historicalSob.filterStatus", "Status"))}</label>
            <select id="hsFilterStatus" data-f="status">
              <option value="all"${f.status === "all" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.statusAll", "All"))}</option>
              <option value="mapped"${f.status === "mapped" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.statusMapped", "Mapped"))}</option>
              <option value="need_review"${f.status === "need_review" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.statusNeedReview", "Need review"))}</option>
              <option value="not_found"${f.status === "not_found" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.statusNotFound", "Not found"))}</option>
              <option value="shopee_only"${f.status === "shopee_only" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.statusShopeeOnly", "Shopee only"))}</option>
              <option value="tiktok_only"${f.status === "tiktok_only" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.statusTiktokOnly", "TikTok only"))}</option>
            </select>
          </div>
          <div class="si-v1-toolbar-field">
            <label for="hsFilterCategory">${escapeHtml(i18n("historicalSob.filterCategory", "Category"))}</label>
            <select id="hsFilterCategory" data-f="category">${categoryOptionsHtml(f)}</select>
          </div>
          <div class="si-v1-toolbar-field">
            <label for="hsFilterSort">${escapeHtml(i18n("historicalSob.filterSort", "Sort"))}</label>
            <select id="hsFilterSort" data-f="sort">
              <option value="shop_name"${f.sort === "shop_name" ? " selected" : ""}>Shop name</option>
              <option value="april_sob"${f.sort === "april_sob" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.sortAprilSob", "April SOB"))}</option>
              <option value="may_sob"${f.sort === "may_sob" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.sortMaySob", "May SOB"))}</option>
              <option value="sob_change"${f.sort === "sob_change" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.sortChange", "SOB Change"))}</option>
              <option value="tiktok_sob"${f.sort === "tiktok_sob" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.sortTiktokSob", "Highest TikTok SOB"))}</option>
              <option value="shopee_sob"${f.sort === "shopee_sob" ? " selected" : ""}>${escapeHtml(i18n("historicalSob.sortShopeeSob", "Highest Shopee SOB"))}</option>
            </select>
          </div>
          <button type="button" class="si-sla-btn-reset" data-reset>${escapeHtml(i18n("historicalSob.resetFilters", "Reset filters"))}</button>`;
  }

  function filterCardHtml(f) {
    return `<div class="si-sla-filter-card" data-hs-filter-card>
        <div class="si-v1-toolbar si-sla-toolbar" data-toolbar="historical-sob">${toolbarFieldsHtml(f)}</div>
        <p class="si-sla-result-count" data-result-count></p>
      </div>`;
  }

  function syncFilterControls() {
    const card = contentEl?.querySelector("[data-hs-filter-card]");
    const toolbar = card?.querySelector("[data-toolbar='historical-sob']");
    if (!toolbar) return;
    filters = coerceGpForRm(filters);
    const f = filters;
    const sf = sheetFilters();
    const q = toolbar.querySelector("[data-f='q']");
    if (q) q.value = f.q || "";
    const map = {
      rm: "hsFilterRm",
      gp: "hsFilterGp",
      status: "hsFilterStatus",
      category: "hsFilterCategory",
      sort: "hsFilterSort",
    };
    Object.entries(map).forEach(([key, id]) => {
      const node = toolbar.querySelector(`#${id}`);
      if (node) node.value = f[key] || "all";
    });
    const rmSel = toolbar.querySelector("#hsFilterRm");
    if (rmSel) rmSel.innerHTML = filterSelectOptionsHtml(sf.rm, f.rm, "All RM");
    const gpSel = toolbar.querySelector("#hsFilterGp");
    if (gpSel) {
      gpSel.innerHTML = filterSelectOptionsHtml(gpFilterForRm(sf.gp, f.rm), f.gp, "All GP");
    }
    const catSel = toolbar.querySelector("#hsFilterCategory");
    if (catSel) catSel.innerHTML = categoryOptionsHtml(f);
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

    paintHistoricalSummarySob();

    const listEl = contentEl.querySelector("[data-hs-list]");
    const countEl = contentEl.querySelector("[data-result-count]");
    if (!listEl) return;

    const all = payload.sellers || [];
    const filtered = filterSellers(all);
    if (countEl) {
      countEl.textContent = `Showing ${filtered.length} of ${all.length} sellers`;
    }
    if (!filtered.length) {
      listEl.innerHTML = `<p class="si-v1-empty">${escapeHtml(i18n("historicalSob.emptySellers", "No sellers match the current filters."))}</p>`;
      return;
    }
    listEl.innerHTML = renderTable(filtered);
    bindRowToggles(listEl);
    animateSobBars(listEl);
  }

  function setupShell() {
    if (!contentEl || !payload) return;
    if (!shellReady) {
      contentEl.innerHTML = `
        <div class="hs-shell">
          <div data-hs-kpis class="hs-page-kpis-wrap">${renderKpiGrid()}</div>
          ${filterCardHtml(filters)}
          <div class="si-sla-summary-sob" data-hs-summary-sob aria-live="polite"></div>
          <div class="si-v1-list" data-hs-list></div>
        </div>`;

      const onToolbar = (ev) => {
        if (ev?.reset) {
          filters = defaultFilters();
        } else {
          const toolbar = contentEl.querySelector("[data-toolbar='historical-sob']");
          filters = coerceGpForRm(readFiltersFromToolbar(toolbar));
        }
        syncFilterControls();
        paintList();
      };
      bindToolbar(contentEl.querySelector("[data-toolbar='historical-sob']"), onToolbar);
      shellReady = true;
    } else {
      syncFilterControls();
    }
    paintList();
  }

  function applySharedSlaUpdateFromPayload(data) {
    const sla = data?.sla_update_state;
    if (window.ShpIntelligenceV1?.applySharedSlaUpdateState) {
      window.ShpIntelligenceV1.applySharedSlaUpdateState(sla, { headerEl: headerLastUpdatedEl });
      return;
    }
    if (!headerLastUpdatedEl || !sla?.completed) return;
    const iso = sla.refreshed_at || sla.finished_at;
    const fmt = window.ShpIntelligenceV1?.formatSlaLastUpdatedHeader?.(iso) || iso || "";
    if (fmt) {
      headerLastUpdatedEl.textContent = `${i18n("si.lastUpdated", "Last updated:")} ${fmt}`;
    }
  }

  function updateMeta() {
    if (payload) applySharedSlaUpdateFromPayload(payload);
    if (!metaEl || !payload) return;
    metaEl.textContent = [
      i18n("historicalSob.metaPeriod", "April 2026 · May 2026"),
      payload.ytd_tab ? `YTD: ${payload.ytd_tab}` : "",
      payload.usd_php_rate != null ? `USD/PHP ${payload.usd_php_rate}` : "",
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

  function init() {
    load(false).catch(() => {});
    if (!slaUpdateListenerBound) {
      slaUpdateListenerBound = true;
      document.addEventListener("sla-update-complete", () => {
        payload = null;
        shellReady = false;
        expanded.clear();
        load(true).catch(() => {});
      });
    }
  }

  function clearCache() {
    payload = null;
    shellReady = false;
    expanded.clear();
    filters = defaultFilters();
  }

  window.ShpHistoricalSob = { init, load, clearCache };
})();
