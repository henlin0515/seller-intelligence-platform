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

  function fmtPct(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return `${fmtNum(n, 1)}%`;
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
    const sh = s.shopee_mom_percent;
    const tk = s.tiktok_mom_percent;
    if (sh == null && tk == null) return "unknown";
    if ((sh != null && sh < -5) && (tk != null && tk < -5)) return "at_risk";
    if ((sh != null && sh < 0) || (tk != null && tk < 0)) return "attention";
    return "healthy";
  }

  function deriveBusinessRisk(s) {
    const mtdSh = s.mtd_shopee_sob_percent;
    const mtdTk = s.mtd_tiktok_sob_percent;
    if (mtdTk != null && mtdSh != null && mtdTk > mtdSh) return "tiktok_leading";
    const sh = s.shopee_mom_percent;
    const tk = s.tiktok_mom_percent;
    if ((sh != null && sh < -8) || (tk != null && tk < -8)) return "high";
    if ((sh != null && sh > 5) || (tk != null && tk > 5)) return "low";
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

  function renderSobBar(shpPct, tkPct, periodLabelText, animate) {
    const shp = shpPct != null ? Math.max(0, Math.min(100, shpPct)) : 0;
    const tk = tkPct != null ? Math.max(0, Math.min(100, tkPct)) : 0;
    const shpW = animate ? shp : 0;
    const tkW = animate ? tk : 0;
    return `
      <div class="si-sob-wrap">
        <div class="si-sob-label">
          <span class="shp">SHP ${fmtPct(shp)}</span>
          <span class="tk">TK ${fmtPct(tk)}</span>
        </div>
        <div class="si-sob-bar" data-sob-animate="${animate ? "1" : "0"}">
          <div class="si-sob-seg si-sob-seg--shp" style="width:${shpW}%"></div>
          <div class="si-sob-seg si-sob-seg--tk" style="width:${tkW}%"></div>
        </div>
        <div class="si-sob-period">${escapeHtml(periodLabelText)}</div>
      </div>`;
  }

  function animateSobBars(root) {
    requestAnimationFrame(() => {
      root.querySelectorAll('.si-sob-bar[data-sob-animate="1"]').forEach((bar) => {
        const segs = bar.querySelectorAll(".si-sob-seg");
        if (segs.length < 2) return;
        const parent = bar.closest(".si-sob-wrap");
        const labels = parent?.querySelectorAll(".si-sob-label span");
        if (!labels?.length) return;
        const shpText = labels[0]?.textContent?.match(/([\d.]+)%/);
        const tkText = labels[1]?.textContent?.match(/([\d.]+)%/);
        const shp = shpText ? parseFloat(shpText[1]) : 0;
        const tk = tkText ? parseFloat(tkText[1]) : 0;
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

  function renderBusinessRow(s, expanded) {
    const tkLeading =
      s.mtd_tiktok_sob_percent != null &&
      s.mtd_shopee_sob_percent != null &&
      s.mtd_tiktok_sob_percent > s.mtd_shopee_sob_percent;
    const rowCls = tkLeading ? "si-v1-row si-v1-row--tk-leading" : "si-v1-row";
    const expCls = expanded ? " is-expanded" : "";
    return `
      <article class="${rowCls}${expCls}" data-shop-id="${escapeHtml(s.shop_id)}">
        <div class="si-v1-row-head" data-toggle-row>
          <div class="si-v1-row-toggle" aria-hidden="true">▶</div>
          <div class="si-v1-row-title">
            <strong>${escapeHtml(s.shop_name)}</strong>
            <span>${escapeHtml(s.shop_id)} · ${escapeHtml(s.tiktok_shop_name || "")}</span>
          </div>
          <div class="si-v1-row-summary">
            <div class="si-v1-row-metrics-inline">
              ${renderMom(s.shopee_mom_percent, "Shopee MoM")}
              ${renderMom(s.tiktok_mom_percent, "TikTok MoM")}
              ${tkLeading ? '<span class="si-v1-badge si-v1-badge--purple">TK SOB lead</span>' : ""}
            </div>
            ${renderSobBar(s.mtd_shopee_sob_percent, s.mtd_tiktok_sob_percent, "MTD SOB", true)}
            ${renderSobBar(s.m1_shopee_sob_percent, s.m1_tiktok_sob_percent, "M-1 SOB", true)}
          </div>
        </div>
        <div class="si-v1-row-body">
          <dl class="si-detail-grid">
            <div class="si-detail-cell"><dt>Shopee MTD ADGMV</dt><dd>$${fmtNum(s.shopee_mtd_adgmv_usd)}</dd></div>
            <div class="si-detail-cell"><dt>TikTok MTD ADGMV</dt><dd>$${fmtNum(s.tiktok_mtd_adgmv_usd)}</dd></div>
            <div class="si-detail-cell"><dt>Shopee M-1 ADGMV</dt><dd>$${fmtNum(s.shopee_m1_adgmv_usd)}</dd></div>
            <div class="si-detail-cell"><dt>TikTok M-1 ADGMV</dt><dd>$${fmtNum(s.tiktok_m1_adgmv_usd)}</dd></div>
            <div class="si-detail-cell"><dt>Shopee MoM</dt><dd>${renderMom(s.shopee_mom_percent, "")}</dd></div>
            <div class="si-detail-cell"><dt>TikTok MoM</dt><dd>${renderMom(s.tiktok_mom_percent, "")}</dd></div>
          </dl>
          <div class="si-sob-detail-row">
            ${renderSobBar(s.mtd_shopee_sob_percent, s.mtd_tiktok_sob_percent, "MTD share of business", true)}
            ${renderSobBar(s.m1_shopee_sob_percent, s.m1_tiktok_sob_percent, "M-1 share of business", true)}
          </div>
        </div>
      </article>`;
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
    listEl.innerHTML = filtered
      .map((s) => renderBusinessRow(s, st.expanded.has(s.shop_id)))
      .join("");
    bindRowToggles(listEl, st.expanded);
    animateSobBars(listEl);
  }

  function setupBusiness(data) {
    const el = containers.siBusiness;
    if (!el) return;
    state.business.raw = data;
    if (metas.siBusiness) {
      metas.siBusiness.textContent = `${periodLabel(data.periods)} · Mock · USD/PHP ${data.usd_php_rate}`;
    }
    if (!state.business.shellReady) {
      el.innerHTML = `${businessToolbarHtml(state.business.filters)}<div class="si-v1-list" data-si-list></div>`;
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
    paintBusinessList();
  }

  /* ---------- Assortment render ---------- */

  function renderMissingCard(p) {
    return `
      <article class="si-product-card">
        <img src="${escapeHtml(p.image_url)}" alt="" loading="lazy" width="72" height="72" />
        <div class="si-product-card-body">
          <h4>${escapeHtml(p.product_name)}</h4>
          <p>TikTok price: ₱${fmtNum(p.price_php)}</p>
          <p>${escapeHtml(p.reason)}</p>
          <p>Confidence: ${p.confidence_score != null ? fmtPct(p.confidence_score * 100) : "—"}</p>
          <a href="${escapeHtml(p.tiktok_link)}" target="_blank" rel="noopener noreferrer">TikTok product link</a>
        </div>
      </article>`;
  }

  function renderReviewPair(r) {
    return `
      <article class="si-review-pair">
        <div class="si-review-pair-header">
          <span>Similarity</span>
          <strong>${r.similarity_score != null ? fmtPct(r.similarity_score * 100) : "—"}</strong>
        </div>
        <div class="si-review-columns">
          <div class="si-review-col">
            <span class="tag">Shopee</span>
            <img src="${escapeHtml(r.shopee.image_url)}" alt="" loading="lazy" />
            <h5>${escapeHtml(r.shopee.product_name)}</h5>
            <a href="${escapeHtml(r.shopee.product_link)}" target="_blank" rel="noopener noreferrer">Shopee link</a>
          </div>
          <div class="si-review-vs">VS</div>
          <div class="si-review-col">
            <span class="tag tag--tt">TikTok</span>
            <img src="${escapeHtml(r.tiktok.image_url)}" alt="" loading="lazy" />
            <h5>${escapeHtml(r.tiktok.product_name)}</h5>
            <a href="${escapeHtml(r.tiktok.product_link)}" target="_blank" rel="noopener noreferrer">TikTok link</a>
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
      metas.siAssortment.textContent = `Mock assortment data · Tracker off · FastMoss off`;
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
          <div class="si-v1-card-label">Sellers (mock)</div>
          <div class="si-v1-card-value">${escapeHtml(String(data.seller_count ?? 0))}</div>
        </article>
        <article class="si-v1-card">
          <div class="si-v1-card-label">Business</div>
          <div class="si-v1-card-value"><span class="si-v1-badge">${escapeHtml(mods.business_intelligence?.status || "—")}</span></div>
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
