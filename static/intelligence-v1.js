/**
 * Seller Intelligence V1 — command center UI (business + assortment).
 */
(function () {
  const API = {
    dashboard: "/api/intelligence/v1/dashboard",
    business: "/api/intelligence/v1/business",
    assortment: "/api/intelligence/v1/assortment",
    voucher: "/api/intelligence/v1/voucher",
  };

  const containers = {
    siDashboard: document.getElementById("siDashboardContent"),
    siBusiness: document.getElementById("siBusinessContent"),
    siAssortment: document.getElementById("siAssortmentContent"),
    siVoucher: document.getElementById("siVoucherContent"),
  };

  const metas = {
    siDashboard: document.getElementById("siDashboardMeta"),
    siBusiness: document.getElementById("siBusinessMeta"),
    siAssortment: document.getElementById("siAssortmentMeta"),
    siVoucher: document.getElementById("siVoucherMeta"),
  };

  const cache = {};
  const state = {
    business: {
      raw: null,
      filters: defaultBusinessFilters(),
      expanded: new Set(),
      shellReady: false,
      viewMode: "portfolio",
    },
    assortment: {
      raw: null,
      filters: defaultAssortmentFilters(),
      expanded: new Set(),
      shellReady: false,
    },
  };

  function defaultBusinessFilters() {
    return { q: "", status: "all", risk: "all", sort: "shop_name" };
  }

  function defaultAssortmentFilters() {
    return {
      q: "",
      mapping: "all",
      missing: "all",
      review: "all",
      priceGap: "all",
      newListings: "all",
      sort: "shop_name",
    };
  }

  function fetchApi(path) {
    const fn = window.SipApi?.fetch || fetch;
    return fn(path, { credentials: "same-origin" });
  }

  function escapeHtml(text) {
    const d = document.createElement("div");
    d.textContent = String(text ?? "");
    return d.innerHTML;
  }

  function fmtNum(n, digits = 0) {
    if (n == null || Number.isNaN(n)) return "—";
    return Number(n).toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits,
    });
  }

  function fmtUsd(n) {
    if (n == null || Number.isNaN(n)) return null;
    return `$${fmtNum(n, 2)}`;
  }

  function fmtPhp(n) {
    if (n == null || Number.isNaN(n)) return null;
    return `₱${fmtNum(n, 0)}`;
  }

  function fmtPct(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return `${fmtNum(n, 1)}%`;
  }

  function fmtNa(reason) {
    const title = reason ? ` title="${escapeHtml(reason)}"` : "";
    return `<span class="si-v1-na"${title}>NA</span>`;
  }

  function fmtShopeeUsd(value, reason) {
    if (value == null || Number.isNaN(value)) {
      return fmtNa(reason || "Shopee ADGMV not found in Tracker");
    }
    return escapeHtml(fmtUsd(value));
  }

  function fmtSobPct(value, reason) {
    if (value == null || Number.isNaN(value)) {
      return fmtNa(reason || "SOB requires Shopee and TikTok ADGMV");
    }
    return `${fmtNum(value, 1)}%`;
  }

  function fastmossStatusBadge(status) {
    const map = {
      MAPPED: ["si-v1-badge--ok", "Mapped"],
      NEED_REVIEW: ["si-v1-badge--warn", "Need review"],
      NOT_FOUND: ["si-v1-badge--risk", "Not found"],
    };
    const [cls, label] = map[status] || ["si-v1-badge--muted", status || "—"];
    return `<span class="si-v1-badge ${cls}">${escapeHtml(label)}</span>`;
  }

  function fmtTikTokUsd(value, gmvPhp, label) {
    if (value == null || Number.isNaN(value)) return fmtNa(label);
    const tip = gmvPhp != null ? ` title="GMV ${fmtPhp(gmvPhp)}"` : "";
    return `<span${tip}>${fmtUsd(value)}</span>`;
  }

  function periodLabel(periods) {
    if (!periods?.mtd || !periods?.m1) return "";
    return `MTD ${periods.mtd.start} → ${periods.mtd.end} · M-1 ${periods.m1.start} → ${periods.m1.end}`;
  }

  async function load(path) {
    const res = await fetchApi(path);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${res.status})`);
    }
    return res.json();
  }

  /* ---------- Search & filters (client-side) ---------- */

  function sellerSearchBlob(s) {
    return [
      s.shop_id,
      s.shop_name,
      s.shopee_link,
      s.tiktok_shop_name,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function matchesQuery(s, q) {
    if (!q) return true;
    return sellerSearchBlob(s).includes(q.trim().toLowerCase());
  }

  function deriveBusinessStatus(s) {
    if (s.tiktok_data_status !== "available") return "unknown";
    const tk = s.tiktok_mom_percent;
    if (tk == null) return "unknown";
    if (tk < -5) return "at_risk";
    if (tk < 0) return "attention";
    return "healthy";
  }

  function deriveBusinessRisk(s) {
    if (s.tiktok_data_status !== "available") return "medium";
    const tk = s.tiktok_mom_percent;
    if (tk != null && tk < -8) return "high";
    if (tk != null && tk > 5) return "low";
    return "medium";
  }

  function filterBusinessSellers(sellers, f) {
    let list = sellers.filter((s) => {
      if (!matchesQuery(s, f.q)) return false;
      if (f.status !== "all" && deriveBusinessStatus(s) !== f.status) return false;
      if (f.risk !== "all" && deriveBusinessRisk(s) !== f.risk) return false;
      return true;
    });
    list = sortBusiness(list, f.sort);
    return list;
  }

  function sortBusiness(list, sort) {
    const copy = [...list];
    const cmp = (a, b) => (a > b ? 1 : a < b ? -1 : 0);
    copy.sort((a, b) => {
      switch (sort) {
        case "shopee_mtd":
          return cmp(b.shopee_mtd_adgmv_usd ?? 0, a.shopee_mtd_adgmv_usd ?? 0);
        case "tiktok_mtd":
          return cmp(b.tiktok_mtd_adgmv_usd ?? 0, a.tiktok_mtd_adgmv_usd ?? 0);
        case "shopee_mom":
          return cmp(b.shopee_mom_percent ?? -999, a.shopee_mom_percent ?? -999);
        case "tiktok_mom":
          return cmp(b.tiktok_mom_percent ?? -999, a.tiktok_mom_percent ?? -999);
        case "fastmoss":
          return (a.fastmoss_match_status || "").localeCompare(b.fastmoss_match_status || "");
        default:
          return (a.shop_name || "").localeCompare(b.shop_name || "");
      }
    });
    return copy;
  }

  function filterAssortmentSellers(sellers, f) {
    let list = sellers.filter((s) => {
      if (!matchesQuery(s, f.q)) return false;
      if (f.mapping !== "all" && s.mapping_status !== f.mapping) return false;
      if (f.missing === "yes" && !(s.missing_count > 0)) return false;
      if (f.review === "yes" && !(s.need_review_count > 0)) return false;
      if (f.priceGap === "yes" && !s.price_gap_risk) return false;
      if (f.newListings === "yes" && !(s.new_listings_count > 0)) return false;
      return true;
    });
    const copy = [...list];
    copy.sort((a, b) => {
      if (f.sort === "missing") return (b.missing_count ?? 0) - (a.missing_count ?? 0);
      if (f.sort === "review") return (b.need_review_count ?? 0) - (a.need_review_count ?? 0);
      return (a.shop_name || "").localeCompare(b.shop_name || "");
    });
    return copy;
  }

  /* ---------- UI components ---------- */

  function renderMom(pct, label) {
    if (pct == null || Number.isNaN(pct)) {
      return `<span class="si-mom si-mom--flat" title="${escapeHtml(label)}">—</span>`;
    }
    const up = pct > 0.05;
    const down = pct < -0.05;
    const cls = up ? "si-mom--up" : down ? "si-mom--down" : "si-mom--flat";
    const arrow = up ? "▲" : down ? "▼" : "●";
    return `<span class="si-mom ${cls}" title="${escapeHtml(label)}"><span class="si-mom-arrow">${arrow}</span>${fmtPct(pct)}</span>`;
  }

  function clampSobPct(value) {
    if (value == null || Number.isNaN(value)) return null;
    return Math.max(0, Math.min(100, value));
  }

  function fmtSobAdgmv(value) {
    if (value == null || Number.isNaN(value)) return "—";
    return fmtUsd(value);
  }

  const SOB_INBAR_MIN = 14;

  function renderSobStackedSeg(platform, pct, adgmv, compact, animate) {
    const label = platform === "shp" ? "Shopee" : "TikTok";
    const width = animate ? 0 : pct;
    const compactCls = compact ? " is-compact" : "";
    const platCls = platform === "shp" ? "si-sob-stack-seg--shp" : "si-sob-stack-seg--tk";
    return `
      <div class="si-sob-stack-seg ${platCls}${compactCls}" style="width:${width}%" tabindex="0">
        <span class="si-sob-seg-label">${label} ${fmtPct(pct)}</span>
        <span class="si-sob-tip" role="tooltip">
          <span class="si-sob-tip-title">${label}</span>
          <span class="si-sob-tip-row">ADGMV ${escapeHtml(fmtSobAdgmv(adgmv))}</span>
          <span class="si-sob-tip-row">SOB ${fmtPct(pct)}</span>
        </span>
      </div>`;
  }

  function renderSobPeriodBlock(periodLabel, shpPct, tkPct, shpAdgmv, tkAdgmv, animate) {
    const shp = clampSobPct(shpPct);
    const tk = clampSobPct(tkPct);
    if (shp == null || tk == null) return "";
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
          ${renderSobStackedSeg("shp", shp, shpAdgmv, shpCompact, animate)}
          ${renderSobStackedSeg("tk", tk, tkAdgmv, tkCompact, animate)}
        </div>
      </section>`;
  }

  function renderBusinessSobAnalysis(s) {
    const sobReason = s.sob_na_reason || "SOB requires Shopee and TikTok ADGMV";
    const hasMtd =
      s.mtd_shopee_sob_percent != null &&
      s.mtd_tiktok_sob_percent != null &&
      !Number.isNaN(s.mtd_shopee_sob_percent) &&
      !Number.isNaN(s.mtd_tiktok_sob_percent);
    const hasM1 =
      s.m1_shopee_sob_percent != null &&
      s.m1_tiktok_sob_percent != null &&
      !Number.isNaN(s.m1_shopee_sob_percent) &&
      !Number.isNaN(s.m1_tiktok_sob_percent);
    if (!hasMtd && !hasM1) {
      return `
        <div class="si-biz-sob-card">
          <div class="si-biz-sob-card-head">
            <h4 class="si-biz-sob-card-title">SOB Analysis</h4>
          </div>
          <div class="si-biz-sob-card-body">${fmtNa(sobReason)}</div>
        </div>`;
    }
    const mtdBlock = hasMtd
      ? renderSobPeriodBlock(
          "MTD",
          s.mtd_shopee_sob_percent,
          s.mtd_tiktok_sob_percent,
          s.shopee_mtd_adgmv_usd,
          s.tiktok_mtd_adgmv_usd,
          true
        )
      : "";
    const m1Block = hasM1
      ? renderSobPeriodBlock(
          "M-1",
          s.m1_shopee_sob_percent,
          s.m1_tiktok_sob_percent,
          s.shopee_m1_adgmv_usd,
          s.tiktok_m1_adgmv_usd,
          true
        )
      : "";
    const divider = mtdBlock && m1Block ? `<div class="si-biz-sob-card-divider" role="presentation"></div>` : "";
    return `
      <div class="si-biz-sob-card">
        <div class="si-biz-sob-card-head">
          <h4 class="si-biz-sob-card-title">SOB Analysis</h4>
        </div>
        <div class="si-biz-sob-card-body">
          ${mtdBlock}
          ${divider}
          ${m1Block}
        </div>
      </div>`;
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

  function mappingBadge(status) {
    const map = {
      mapped: ["si-v1-badge--ok", "Mapped"],
      partial: ["si-v1-badge--warn", "Partial"],
      unmapped: ["si-v1-badge--risk", "Unmapped"],
    };
    const [cls, label] = map[status] || ["si-v1-badge--muted", status || "—"];
    return `<span class="si-v1-badge ${cls}">${escapeHtml(label)}</span>`;
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

  function businessToolbarHtml(f) {
    return `
      <div class="si-v1-toolbar" data-toolbar="business">
        <div class="si-v1-toolbar-field si-v1-toolbar-field--search">
          <label for="siBizSearch">Seller search</label>
          <input id="siBizSearch" type="search" placeholder="Shop ID, name, Shopee link, TikTok shop…" value="${escapeHtml(f.q)}" data-f="q" />
        </div>
        <div class="si-v1-toolbar-field">
          <label for="siBizStatus">Status</label>
          <select id="siBizStatus" data-f="status">
            <option value="all"${f.status === "all" ? " selected" : ""}>All</option>
            <option value="healthy"${f.status === "healthy" ? " selected" : ""}>Healthy</option>
            <option value="attention"${f.status === "attention" ? " selected" : ""}>Needs attention</option>
            <option value="at_risk"${f.status === "at_risk" ? " selected" : ""}>At risk</option>
          </select>
        </div>
        <div class="si-v1-toolbar-field">
          <label for="siBizRisk">Risk</label>
          <select id="siBizRisk" data-f="risk">
            <option value="all"${f.risk === "all" ? " selected" : ""}>All</option>
            <option value="low"${f.risk === "low" ? " selected" : ""}>Low</option>
            <option value="medium"${f.risk === "medium" ? " selected" : ""}>Medium</option>
            <option value="high"${f.risk === "high" ? " selected" : ""}>High</option>
            <option value="tiktok_leading"${f.risk === "tiktok_leading" ? " selected" : ""}>TikTok SOB lead</option>
          </select>
        </div>
        <div class="si-v1-toolbar-field">
          <label for="siBizSort">Sort</label>
          <select id="siBizSort" data-f="sort">
            <option value="shop_name"${f.sort === "shop_name" ? " selected" : ""}>Shop name</option>
            <option value="shopee_mtd"${f.sort === "shopee_mtd" ? " selected" : ""}>Shopee MTD ADGMV</option>
            <option value="tiktok_mtd"${f.sort === "tiktok_mtd" ? " selected" : ""}>TikTok MTD ADGMV</option>
            <option value="shopee_mom"${f.sort === "shopee_mom" ? " selected" : ""}>Shopee MoM</option>
            <option value="tiktok_mom"${f.sort === "tiktok_mom" ? " selected" : ""}>TikTok MoM</option>
            <option value="fastmoss"${f.sort === "fastmoss" ? " selected" : ""}>FastMoss status</option>
          </select>
        </div>
        <button type="button" class="si-v1-btn-reset" data-reset>Reset filters</button>
        <p class="si-v1-result-count" data-result-count></p>
      </div>`;
  }

  function assortmentToolbarHtml(f) {
    return `
      <div class="si-v1-toolbar" data-toolbar="assortment">
        <div class="si-v1-toolbar-field si-v1-toolbar-field--search">
          <label for="siAssSearch">Seller search</label>
          <input id="siAssSearch" type="search" placeholder="Shop ID, name, Shopee link, TikTok shop…" value="${escapeHtml(f.q)}" data-f="q" />
        </div>
        <div class="si-v1-toolbar-field">
          <label for="siAssMap">Mapping</label>
          <select id="siAssMap" data-f="mapping">
            <option value="all"${f.mapping === "all" ? " selected" : ""}>All</option>
            <option value="mapped"${f.mapping === "mapped" ? " selected" : ""}>Mapped</option>
            <option value="partial"${f.mapping === "partial" ? " selected" : ""}>Partial</option>
            <option value="unmapped"${f.mapping === "unmapped" ? " selected" : ""}>Unmapped</option>
          </select>
        </div>
        <div class="si-v1-toolbar-field">
          <label for="siAssMiss">Missing</label>
          <select id="siAssMiss" data-f="missing">
            <option value="all"${f.missing === "all" ? " selected" : ""}>All</option>
            <option value="yes"${f.missing === "yes" ? " selected" : ""}>&gt; 0</option>
          </select>
        </div>
        <div class="si-v1-toolbar-field">
          <label for="siAssRev">Need review</label>
          <select id="siAssRev" data-f="review">
            <option value="all"${f.review === "all" ? " selected" : ""}>All</option>
            <option value="yes"${f.review === "yes" ? " selected" : ""}>&gt; 0</option>
          </select>
        </div>
        <div class="si-v1-toolbar-field">
          <label for="siAssGap">Price gap</label>
          <select id="siAssGap" data-f="priceGap">
            <option value="all"${f.priceGap === "all" ? " selected" : ""}>All</option>
            <option value="yes"${f.priceGap === "yes" ? " selected" : ""}>At risk</option>
          </select>
        </div>
        <div class="si-v1-toolbar-field">
          <label for="siAssNew">New listings</label>
          <select id="siAssNew" data-f="newListings">
            <option value="all"${f.newListings === "all" ? " selected" : ""}>All</option>
            <option value="yes"${f.newListings === "yes" ? " selected" : ""}>&gt; 0</option>
          </select>
        </div>
        <div class="si-v1-toolbar-field">
          <label for="siAssSort">Sort</label>
          <select id="siAssSort" data-f="sort">
            <option value="shop_name"${f.sort === "shop_name" ? " selected" : ""}>Shop name</option>
            <option value="missing"${f.sort === "missing" ? " selected" : ""}>Missing count</option>
            <option value="review"${f.sort === "review" ? " selected" : ""}>Need review</option>
          </select>
        </div>
        <button type="button" class="si-v1-btn-reset" data-reset>Reset filters</button>
        <p class="si-v1-result-count" data-result-count></p>
      </div>`;
  }

  function readFiltersFromToolbar(toolbar, defaults) {
    const f = { ...defaults };
    toolbar.querySelectorAll("[data-f]").forEach((node) => {
      f[node.dataset.f] = node.value;
    });
    return f;
  }

  /* ---------- Business render ---------- */

  function businessViewToggleHtml(mode) {
    const portfolioActive = mode === "portfolio" ? " is-active" : "";
    const sellerActive = mode === "seller" ? " is-active" : "";
    return `
      <div class="si-biz-view-toggle" role="tablist" aria-label="Business Intelligence view">
        <button type="button" class="si-biz-view-btn${portfolioActive}" data-biz-view="portfolio" role="tab" aria-selected="${mode === "portfolio"}">Portfolio View</button>
        <button type="button" class="si-biz-view-btn${sellerActive}" data-biz-view="seller" role="tab" aria-selected="${mode === "seller"}">Seller View</button>
      </div>`;
  }

  function renderPortfolioKpi(label, value, sub, accent) {
    const accentCls = accent ? ` si-port-kpi--${accent}` : "";
    return `
      <article class="si-port-kpi${accentCls}">
        <div class="si-port-kpi-label">${escapeHtml(label)}</div>
        <div class="si-port-kpi-value">${value}</div>
        ${sub ? `<div class="si-port-kpi-sub">${sub}</div>` : ""}
      </article>`;
  }

  function renderPortfolioMomCard(label, pct) {
    const mom = renderMom(pct, "Portfolio MoM");
    return `
      <article class="si-port-trend-card">
        <div class="si-port-trend-label">${escapeHtml(label)}</div>
        <div class="si-port-trend-value">${mom}</div>
      </article>`;
  }

  function renderPortfolioSobHero(portfolio) {
    const shp = portfolio.portfolio_sob_mtd_shopee_percent;
    const tk = portfolio.portfolio_sob_mtd_tiktok_percent;
    if (shp == null || tk == null) {
      return `<div class="si-port-sob-hero">${fmtNa("SOB requires Shopee and TikTok ADGMV")}</div>`;
    }
    const mtdBlock = renderSobPeriodBlock(
      "Portfolio SOB MTD",
      shp,
      tk,
      portfolio.shopee_mtd_adgmv_usd,
      portfolio.tiktok_mtd_adgmv_usd,
      true
    );
    const m1Block =
      portfolio.portfolio_sob_m1_shopee_percent != null &&
      portfolio.portfolio_sob_m1_tiktok_percent != null
        ? renderSobPeriodBlock(
            "Portfolio SOB M-1",
            portfolio.portfolio_sob_m1_shopee_percent,
            portfolio.portfolio_sob_m1_tiktok_percent,
            portfolio.shopee_m1_adgmv_usd,
            portfolio.tiktok_m1_adgmv_usd,
            true
          )
        : "";
    return `<div class="si-port-sob-hero">${mtdBlock}${m1Block ? `<div class="si-biz-sob-card-divider"></div>${m1Block}` : ""}</div>`;
  }

  function renderPortfolioSegmentCards(portfolio) {
    return `
      <div class="si-port-segments">
        <article class="si-port-segment si-port-segment--grow">
          <span class="si-port-segment-label">Growing</span>
          <strong>${fmtNum(portfolio.growing_seller_count ?? 0)}</strong>
          <span class="si-port-segment-hint">&gt; +5% total ADGMV</span>
        </article>
        <article class="si-port-segment si-port-segment--flat">
          <span class="si-port-segment-label">Flat</span>
          <strong>${fmtNum(portfolio.flat_seller_count ?? 0)}</strong>
          <span class="si-port-segment-hint">±5% band</span>
        </article>
        <article class="si-port-segment si-port-segment--down">
          <span class="si-port-segment-label">Declining</span>
          <strong>${fmtNum(portfolio.declining_seller_count ?? 0)}</strong>
          <span class="si-port-segment-hint">&lt; −5% total ADGMV</span>
        </article>
      </div>`;
  }

  function renderPortfolioTop5Table(rows, portfolioTotal) {
    if (!rows?.length) {
      return '<p class="si-v1-empty">No mapped sellers with MTD ADGMV yet.</p>';
    }
    const body = rows
      .map(
        (r, idx) => `<tr>
          <td class="si-port-rank">${idx + 1}</td>
          <td>${escapeHtml(r.shop_name)}</td>
          <td class="si-v1-num">${fmtShopeeUsd(r.shopee_mtd_adgmv_usd)}</td>
          <td class="si-v1-num">${fmtTikTokUsd(r.tiktok_mtd_adgmv_usd, null, "TikTok data unavailable")}</td>
          <td class="si-v1-num">${fmtShopeeUsd(r.total_mtd_adgmv_usd)}</td>
          <td class="si-v1-num">${fmtPct(r.contribution_percent)}</td>
        </tr>`
      )
      .join("");
    return `
      <div class="si-v1-table-wrap">
        <table class="si-v1-table si-v1-table--portfolio">
          <thead>
            <tr>
              <th>#</th>
              <th>Seller</th>
              <th>Shopee MTD</th>
              <th>TikTok MTD</th>
              <th>Total MTD</th>
              <th>Contribution</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function renderPortfolioThreatTable(rows) {
    if (!rows?.length) {
      return '<p class="si-v1-empty">No TikTok SOB data for mapped sellers yet.</p>';
    }
    const body = rows
      .map(
        (r, idx) => `<tr>
          <td class="si-port-rank">${idx + 1}</td>
          <td>${escapeHtml(r.shop_name)}</td>
          <td class="si-v1-num"><span class="si-v1-badge si-v1-badge--warn">${fmtPct(r.tiktok_mtd_sob_percent)}</span></td>
          <td class="si-v1-num">${fmtTikTokUsd(r.tiktok_mtd_adgmv_usd, null, "TikTok data unavailable")}</td>
          <td class="si-v1-num">${fmtShopeeUsd(r.shopee_mtd_adgmv_usd)}</td>
          <td class="si-v1-num">${renderMom(r.tiktok_mom_percent, "TikTok MoM")}</td>
        </tr>`
      )
      .join("");
    return `
      <div class="si-v1-table-wrap">
        <table class="si-v1-table si-v1-table--portfolio">
          <thead>
            <tr>
              <th>#</th>
              <th>Seller</th>
              <th>TikTok MTD SOB</th>
              <th>TikTok MTD</th>
              <th>Shopee MTD</th>
              <th>TikTok MoM</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function renderPortfolioOverview(data) {
    const p = data.portfolio || {};
    const mapped = p.mapped_sellers ?? 0;
    const total = p.total_sellers ?? 0;
    return `
      <div class="si-port-overview">
        <div class="si-port-kpi-grid">
          ${renderPortfolioKpi("Total Sellers", fmtNum(total), `${fmtNum(mapped)} mapped`, "neutral")}
          ${renderPortfolioKpi("Mapping Rate", fmtPct(p.mapping_rate_percent), "FastMoss mapped / total", "accent")}
          ${renderPortfolioKpi("Portfolio Total MTD", fmtShopeeUsd(p.portfolio_total_mtd_adgmv_usd), "Shopee + TikTok", "hero")}
          ${renderPortfolioKpi("Shopee MTD ADGMV", fmtShopeeUsd(p.shopee_mtd_adgmv_usd), `M-1 ${fmtUsd(p.shopee_m1_adgmv_usd) || "—"}`, "shopee")}
          ${renderPortfolioKpi("TikTok MTD ADGMV", fmtTikTokUsd(p.tiktok_mtd_adgmv_usd, null, "TikTok data unavailable"), `M-1 ${fmtUsd(p.tiktok_m1_adgmv_usd) || "—"}`, "tiktok")}
          ${renderPortfolioKpi("Shopee M-1 ADGMV", fmtShopeeUsd(p.shopee_m1_adgmv_usd), "Prior month", "shopee")}
          ${renderPortfolioKpi("TikTok M-1 ADGMV", fmtTikTokUsd(p.tiktok_m1_adgmv_usd, null, "TikTok data unavailable"), "Prior month", "tiktok")}
        </div>
        <div class="si-port-mid-grid">
          <section class="si-port-panel si-port-panel--sob">
            <h3 class="si-port-panel-title">Portfolio SOB</h3>
            ${renderPortfolioSobHero(p)}
          </section>
          <section class="si-port-panel si-port-panel--trends">
            <h3 class="si-port-panel-title">Portfolio MoM</h3>
            <div class="si-port-trend-grid">
              ${renderPortfolioMomCard("Shopee MoM", p.shopee_mom_percent)}
              ${renderPortfolioMomCard("TikTok MoM", p.tiktok_mom_percent)}
            </div>
            <h3 class="si-port-panel-title si-port-panel-title--sub">Seller Segmentation</h3>
            ${renderPortfolioSegmentCards(p)}
          </section>
        </div>
        <div class="si-port-tables-grid">
          <section class="si-port-panel">
            <h3 class="si-port-panel-title">Top 5 Seller Contribution</h3>
            ${renderPortfolioTop5Table(p.top5_seller_contribution, p.portfolio_total_mtd_adgmv_usd)}
          </section>
          <section class="si-port-panel">
            <h3 class="si-port-panel-title">Top TikTok Threat Sellers</h3>
            ${renderPortfolioThreatTable(p.top_tiktok_threat_sellers)}
          </section>
        </div>
      </div>`;
  }

  function bindBusinessViewToggle(el) {
    el.querySelectorAll("[data-biz-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.dataset.bizView;
        if (!mode || state.business.viewMode === mode) return;
        state.business.viewMode = mode;
        paintBusinessShell();
      });
    });
  }

  function paintBusinessShell() {
    const el = containers.siBusiness;
    const st = state.business;
    if (!el || !st.raw) return;
    const toggle = el.querySelector("[data-biz-view-toggle]");
    if (toggle) {
      toggle.outerHTML = businessViewToggleHtml(st.viewMode);
      bindBusinessViewToggle(el);
    }
    const portfolioEl = el.querySelector("[data-portfolio-root]");
    const sellerEl = el.querySelector("[data-seller-root]");
    if (portfolioEl) {
      portfolioEl.hidden = st.viewMode !== "portfolio";
      if (st.viewMode === "portfolio") {
        portfolioEl.innerHTML = renderPortfolioOverview(st.raw);
        animateSobBars(portfolioEl);
      }
    }
    if (sellerEl) {
      sellerEl.hidden = st.viewMode !== "seller";
      if (st.viewMode === "seller") paintBusinessList();
    }
  }

  function fmtDetail(value, fallback) {
    if (value == null || value === "") return fallback || "—";
    return escapeHtml(String(value));
  }

  function fmtDetailLink(url, label) {
    if (!url) return "—";
    const text = label || url;
    return `<a class="si-biz-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(text)}</a>`;
  }

  function fmtDetailPhp(value, reason) {
    if (value == null || Number.isNaN(value)) return fmtNa(reason || "TikTok data unavailable");
    return escapeHtml(fmtPhp(value));
  }

  function renderBusinessDetailPanel(s) {
    const tkReason = s.tiktok_na_reason || "TikTok data unavailable";
    return `
      <div class="si-biz-detail-panel">
        <h3 class="si-section-title">Mapping</h3>
        <dl class="si-detail-grid si-detail-grid--compact">
          <div class="si-detail-cell"><dt>TikTok Shop Name</dt><dd>${fmtDetail(s.tiktok_shop_name)}</dd></div>
          <div class="si-detail-cell"><dt>FastMoss Matched Shop</dt><dd>${fmtDetail(s.fastmoss_matched_shop)}</dd></div>
          <div class="si-detail-cell"><dt>FastMoss Match Status</dt><dd>${fastmossStatusBadge(s.fastmoss_match_status)}</dd></div>
          <div class="si-detail-cell"><dt>TikTok raw MTD GMV PHP</dt><dd>${fmtDetailPhp(s.tiktok_mtd_gmv_php, tkReason)}</dd></div>
          <div class="si-detail-cell"><dt>TikTok raw M-1 GMV PHP</dt><dd>${fmtDetailPhp(s.tiktok_m1_gmv_php, tkReason)}</dd></div>
        </dl>
        ${renderBusinessSobAnalysis(s)}
      </div>`;
  }

  function renderBusinessTableRow(s, expanded) {
    const tkReason = s.tiktok_na_reason || "TikTok data unavailable";
    const shReason = s.shopee_na_reason || "Shopee ADGMV not found in Tracker";
    const tkMom =
      s.tiktok_data_status === "available"
        ? renderMom(s.tiktok_mom_percent, tkReason)
        : fmtNa(tkReason);
    const expCls = expanded ? " is-expanded" : "";
    return `
      <tbody class="si-biz-group${expCls}" data-shop-id="${escapeHtml(s.shop_id)}">
        <tr class="si-biz-row-head" data-toggle-row>
          <td class="si-biz-toggle-cell"><span class="si-biz-toggle" aria-hidden="true">▶</span></td>
          <td>${escapeHtml(s.shop_id)}</td>
          <td class="si-biz-name">${escapeHtml(s.shop_name)}</td>
          <td>${fastmossStatusBadge(s.fastmoss_match_status)}</td>
          <td class="si-v1-num">${fmtTikTokUsd(s.tiktok_mtd_adgmv_usd, s.tiktok_mtd_gmv_php, tkReason)}</td>
          <td class="si-v1-num">${fmtTikTokUsd(s.tiktok_m1_adgmv_usd, s.tiktok_m1_gmv_php, tkReason)}</td>
          <td class="si-v1-num">${tkMom}</td>
          <td class="si-v1-num">${fmtShopeeUsd(s.shopee_mtd_adgmv_usd, shReason)}</td>
          <td class="si-v1-num">${fmtShopeeUsd(s.shopee_m1_adgmv_usd, shReason)}</td>
        </tr>
        <tr class="si-biz-row-detail">
          <td colspan="9">${renderBusinessDetailPanel(s)}</td>
        </tr>
      </tbody>`;
  }

  function renderBusinessTable(sellers, expandedSet) {
    return `
      <div class="si-v1-table-wrap si-v1-table-wrap--wide">
        <table class="si-v1-table si-v1-table--business">
          <thead>
            <tr>
              <th class="si-biz-toggle-cell" aria-label="Expand row"></th>
              <th>Shop ID</th>
              <th>Shop Name</th>
              <th>FastMoss Match Status</th>
              <th>TikTok MTD ADGMV USD</th>
              <th>TikTok M-1 ADGMV USD</th>
              <th>TikTok MoM %</th>
              <th>Shopee MTD ADGMV</th>
              <th>Shopee M-1 ADGMV</th>
            </tr>
          </thead>
          ${sellers.map((s) => renderBusinessTableRow(s, expandedSet.has(s.shop_id))).join("")}
        </table>
      </div>`;
  }

  function paintBusinessList() {
    const el = containers.siBusiness;
    const st = state.business;
    if (!el || !st.raw) return;
    const listEl = el.querySelector("[data-si-list]");
    if (!listEl) return;
    const filtered = filterBusinessSellers(st.raw.sellers || [], st.filters);
    const countEl = el.querySelector("[data-result-count]");
    if (countEl) {
      countEl.textContent = `Showing ${filtered.length} of ${(st.raw.sellers || []).length} sellers`;
    }
    if (!filtered.length) {
      listEl.innerHTML = '<p class="si-v1-empty">No sellers match the current filters.</p>';
      return;
    }
    listEl.innerHTML = renderBusinessTable(filtered, st.expanded);
    bindRowToggles(listEl, st.expanded);
    animateSobBars(listEl);
  }

  function setupBusiness(data) {
    const el = containers.siBusiness;
    if (!el) return;
    state.business.raw = data;
    const fm = data.fastmoss || {};
    const summary = data.summary || {};
    const src = fm.fastmoss_connected ? "FastMoss TikTok" : "Seller master";
    const collected = fm.summary?.success != null ? ` · ${summary.tiktok_available ?? fm.summary.success} TikTok` : "";
    if (metas.siBusiness) {
      metas.siBusiness.textContent = `${periodLabel(data.periods)} · ${src}${collected} · USD/PHP ${data.usd_php_rate}`;
    }
    if (!state.business.shellReady) {
      const showPortfolio = state.business.viewMode === "portfolio";
      el.innerHTML = `
        <div class="si-biz-shell">
          <div data-biz-view-toggle>${businessViewToggleHtml(state.business.viewMode)}</div>
          <div class="si-biz-view-panel" data-portfolio-root${showPortfolio ? "" : " hidden"}></div>
          <div class="si-biz-view-panel" data-seller-root${showPortfolio ? " hidden" : ""}>
            ${businessToolbarHtml(state.business.filters)}
            <div class="si-v1-list" data-si-list></div>
          </div>
        </div>`;
      bindBusinessViewToggle(el);
      const onToolbar = (ev) => {
        if (ev?.reset) state.business.filters = defaultBusinessFilters();
        else {
          state.business.filters = readFiltersFromToolbar(
            el.querySelector("[data-toolbar]"),
            defaultBusinessFilters()
          );
        }
        el.querySelector("[data-toolbar]").outerHTML = businessToolbarHtml(state.business.filters);
        bindToolbar(el.querySelector("[data-toolbar]"), onToolbar);
        paintBusinessList();
      };
      bindToolbar(el.querySelector("[data-toolbar]"), onToolbar);
      state.business.shellReady = true;
    }
    paintBusinessShell();
  }

  /* ---------- Assortment render ---------- */

  function renderMissingCard(p) {
    const sold =
      p.sold_count != null ? `<p>Sold: ${escapeHtml(String(p.sold_count))}</p>` : "";
    const sales =
      p.sales_amount != null ? `<p>Sales: ₱${fmtNum(p.sales_amount)}</p>` : "";
    return `
      <article class="si-product-card">
        <img src="${escapeHtml(p.image_url || "")}" alt="" loading="lazy" width="72" height="72" />
        <div class="si-product-card-body">
          <h4>${escapeHtml(p.product_name)}</h4>
          <p>TikTok price: ₱${fmtNum(p.price_php)}</p>
          ${sold}
          ${sales}
          <p>${escapeHtml(p.reason || "Not found on Shopee")}</p>
          <a href="${escapeHtml(p.tiktok_link || "#")}" target="_blank" rel="noopener noreferrer">TikTok product link</a>
        </div>
      </article>`;
  }

  function renderReviewPair(r) {
    const shopee = r.shopee || {};
    const tiktok = r.tiktok || {};
    return `
      <article class="si-review-pair">
        <div class="si-review-pair-header">
          <span>Similarity</span>
          <strong>${r.similarity_score != null ? fmtPct(r.similarity_score * 100) : "—"}</strong>
        </div>
        <p class="si-review-reason">${escapeHtml(r.reason || "")}</p>
        <div class="si-review-columns">
          <div class="si-review-col">
            <span class="tag">Shopee</span>
            <img src="${escapeHtml(shopee.image_url || "")}" alt="" loading="lazy" />
            <h5>${escapeHtml(shopee.product_name || "—")}</h5>
            <p class="si-review-price">₱${fmtNum(shopee.price_php)}</p>
            <a href="${escapeHtml(shopee.product_link || "#")}" target="_blank" rel="noopener noreferrer">Shopee link</a>
          </div>
          <div class="si-review-vs">VS</div>
          <div class="si-review-col">
            <span class="tag tag--tt">TikTok</span>
            <img src="${escapeHtml(tiktok.image_url || "")}" alt="" loading="lazy" />
            <h5>${escapeHtml(tiktok.product_name || "—")}</h5>
            <p class="si-review-price">₱${fmtNum(tiktok.price_php)}</p>
            <a href="${escapeHtml(tiktok.product_link || "#")}" target="_blank" rel="noopener noreferrer">TikTok link</a>
          </div>
        </div>
      </article>`;
  }

  function renderAssortmentRow(s, expanded) {
    const expCls = expanded ? " is-expanded" : "";
    const gapBadge = s.price_gap_risk
      ? '<span class="si-v1-badge si-v1-badge--risk">Gap risk</span>'
      : "";
    return `
      <article class="si-v1-row${expCls}" data-shop-id="${escapeHtml(s.shop_id)}">
        <div class="si-v1-row-head" data-toggle-row>
          <div class="si-v1-row-toggle" aria-hidden="true">▶</div>
          <div class="si-v1-row-title">
            <strong>${escapeHtml(s.shop_name)}</strong>
            <span>${escapeHtml(s.shop_id)}</span>
          </div>
          <div class="si-v1-row-summary si-v1-row-metrics-inline">
            ${mappingBadge(s.mapping_status)}
            <span class="si-v1-badge si-v1-badge--warn">Missing ${s.missing_count ?? 0}</span>
            <span class="si-v1-badge si-v1-badge--muted">Review ${s.need_review_count ?? 0}</span>
            ${gapBadge}
            <span class="si-v1-badge si-v1-badge--muted">New ${s.new_listings_count ?? 0}</span>
          </div>
        </div>
        <div class="si-v1-row-body">
          <h3 class="si-section-title">Missing products (${(s.missing_products || []).length})</h3>
          <div class="si-missing-grid">
            ${(s.missing_products || []).map(renderMissingCard).join("") || '<p class="si-v1-empty">None</p>'}
          </div>
          <h3 class="si-section-title">Need review (${(s.need_review || []).length})</h3>
          <div class="si-review-list">
            ${(s.need_review || []).map(renderReviewPair).join("") || '<p class="si-v1-empty">None</p>'}
          </div>
        </div>
      </article>`;
  }

  function paintAssortmentList() {
    const el = containers.siAssortment;
    const st = state.assortment;
    if (!el || !st.raw) return;
    const listEl = el.querySelector("[data-si-list]");
    if (!listEl) return;
    const filtered = filterAssortmentSellers(st.raw.sellers || [], st.filters);
    const countEl = el.querySelector("[data-result-count]");
    if (countEl) {
      countEl.textContent = `Showing ${filtered.length} of ${(st.raw.sellers || []).length} sellers`;
    }
    if (!filtered.length) {
      listEl.innerHTML = '<p class="si-v1-empty">No sellers match the current filters.</p>';
      return;
    }
    listEl.innerHTML = filtered.map((s) => renderAssortmentRow(s, st.expanded.has(s.shop_id))).join("");
    bindRowToggles(listEl, st.expanded);
  }

  function setupAssortment(data) {
    const el = containers.siAssortment;
    if (!el) return;
    state.assortment.raw = data;
    if (metas.siAssortment) {
      const phase1 = data.phase1_shop_id;
      metas.siAssortment.textContent = phase1
        ? `Phase 1 live · ${phase1} · FastMoss + Shopee catalog compare`
        : `Sheet master · Phase 1 pending`;
    }
    if (!state.assortment.shellReady) {
      el.innerHTML = `${assortmentToolbarHtml(state.assortment.filters)}<div class="si-v1-list" data-si-list></div>`;
      const handler = (ev) => {
        if (ev?.reset) state.assortment.filters = defaultAssortmentFilters();
        else {
          state.assortment.filters = readFiltersFromToolbar(
            el.querySelector("[data-toolbar]"),
            defaultAssortmentFilters()
          );
        }
        el.querySelector("[data-toolbar]").outerHTML = assortmentToolbarHtml(state.assortment.filters);
        bindToolbar(el.querySelector("[data-toolbar]"), handler);
        paintAssortmentList();
      };
      bindToolbar(el.querySelector("[data-toolbar]"), handler);
      state.assortment.shellReady = true;
    }
    paintAssortmentList();
  }

  function bindRowToggles(listEl, expandedSet) {
    listEl.querySelectorAll("[data-toggle-row]").forEach((head) => {
      head.addEventListener("click", () => {
        const row = head.closest("[data-shop-id]");
        const id = row?.dataset?.shopId;
        if (!id) return;
        if (expandedSet.has(id)) expandedSet.delete(id);
        else expandedSet.add(id);
        row.classList.toggle("is-expanded");
        if (row.classList.contains("is-expanded")) {
          animateSobBars(row);
        }
      });
    });
  }

  /* ---------- Dashboard & voucher (simple) ---------- */

  function renderDashboard(data) {
    const el = containers.siDashboard;
    if (!el) return;
    const p = data.periods;
    if (metas.siDashboard) {
      metas.siDashboard.textContent = `${periodLabel(p)} · USD/PHP ${data.usd_php_rate}`;
    }
    const mods = data.modules || {};
    el.innerHTML = `
      <div class="si-v1-cards">
        <article class="si-v1-card">
          <div class="si-v1-card-label">Sellers</div>
          <div class="si-v1-card-value">${escapeHtml(String(data.seller_count ?? 0))}</div>
        </article>
        <article class="si-v1-card">
          <div class="si-v1-card-label">Business</div>
          <div class="si-v1-card-value"><span class="si-v1-badge si-v1-badge--ok">${escapeHtml(mods.business_intelligence?.status || "—")}</span></div>
          <p class="si-v1-card-sub">FastMoss ${mods.business_intelligence?.fastmoss_connected ? "on" : "off"} · TikTok ${mods.business_intelligence?.tiktok_collected ?? "—"}</p>
        </article>
        <article class="si-v1-card">
          <div class="si-v1-card-label">Assortment</div>
          <div class="si-v1-card-value"><span class="si-v1-badge si-v1-badge--warn">${escapeHtml(mods.assortment_intelligence?.status || "—")}</span></div>
        </article>
        <article class="si-v1-card">
          <div class="si-v1-card-label">Voucher</div>
          <div class="si-v1-card-value">${escapeHtml(mods.voucher_intelligence?.value || "N/A")}</div>
        </article>
      </div>`;
  }

  function renderVoucher(data) {
    const el = containers.siVoucher;
    if (!el) return;
    if (metas.siVoucher) metas.siVoucher.textContent = `Placeholder · N/A`;
    const rows = (data.sellers || [])
      .map(
        (s) => `<tr>
        <td>${escapeHtml(s.shop_name)}</td>
        <td>${escapeHtml(s.shop_id)}</td>
        <td>${escapeHtml(s.active_voucher_count)}</td>
        <td>${escapeHtml(s.competitor_voucher_status)}</td>
      </tr>`
      )
      .join("");
    el.innerHTML = `<div class="si-v1-table-wrap"><table class="si-v1-table"><thead><tr>
      <th>Seller</th><th>Shop ID</th><th>Vouchers</th><th>Status</th>
    </tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function showLoading(view) {
    const el = containers[view];
    if (el) {
      el.innerHTML = '<p class="si-v1-loading">Loading…</p>';
      if (view === "siBusiness") state.business.shellReady = false;
      if (view === "siAssortment") state.assortment.shellReady = false;
    }
  }

  function showError(view, message) {
    const el = containers[view];
    if (el) el.innerHTML = `<p class="si-v1-error">${escapeHtml(message)}</p>`;
  }

  async function onShow(view) {
    const paths = {
      siDashboard: API.dashboard,
      siBusiness: API.business,
      siAssortment: API.assortment,
      siVoucher: API.voucher,
    };
    const path = paths[view];
    if (!path) return;

    const useCache = cache[view] && view !== "siBusiness" && view !== "siAssortment";
    if (useCache) {
      if (view === "siDashboard") renderDashboard(cache[view]);
      else if (view === "siVoucher") renderVoucher(cache[view]);
      return;
    }

    if (!cache[view]) showLoading(view);

    try {
      if (!cache[view]) {
        cache[view] = await load(path);
      }
      const data = cache[view];
      if (view === "siDashboard") renderDashboard(data);
      else if (view === "siBusiness") setupBusiness(data);
      else if (view === "siAssortment") setupAssortment(data);
      else if (view === "siVoucher") renderVoucher(data);
    } catch (err) {
      showError(view, err.message || "Failed to load");
    }
  }

  window.ShpIntelligenceV1 = {
    onShow,
    clearCache: () => {
      Object.keys(cache).forEach((k) => delete cache[k]);
      state.business.shellReady = false;
      state.assortment.shellReady = false;
      state.business.expanded.clear();
      state.assortment.expanded.clear();
    },
  };
})();
