/**
 * Competitor Assortment Intelligence — Command Center UI
 */
(function () {
  const panels = {
    dashboard: document.getElementById("caiPanelDashboard"),
    missing: document.getElementById("caiPanelMissing"),
    review: document.getElementById("caiPanelReview"),
    priceGap: document.getElementById("caiPanelPriceGap"),
    newListings: document.getElementById("caiPanelNewListings"),
  };
  const metricsEl = document.getElementById("caiMetrics");
  const trackerEl = document.getElementById("caiTrackerTable");
  const syncBtn = document.getElementById("caiSyncTrackerBtn");
  const syncStatusEl = document.getElementById("caiSyncStatus");
  let activeTab = "dashboard";

  function escapeHtml(t) {
    const d = document.createElement("div");
    d.textContent = String(t ?? "");
    return d.innerHTML;
  }

  function imgCell(url, cls) {
    const c = cls || "cai-thumb";
    if (!url) return `<div class="${c} cc-img-placeholder">NO SIGNAL</div>`;
    return `<img class="${c}" src="${escapeHtml(url)}" alt="" loading="lazy" onerror="this.outerHTML='<div class=\\'${c} cc-img-placeholder\\'>NO SIGNAL</div>'" />`;
  }

  function linkCell(url, label) {
    if (!url || url === "NA") return '<span class="cc-link-na">NA</span>';
    const text = label || "OPEN INTEL";
    return `<a class="cc-intel-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(text)}</a>`;
  }

  function skuList(arr) {
    if (!arr || !arr.length) return "—";
    return escapeHtml(arr.join(", "));
  }

  function formatRelativeTime(iso) {
    if (!iso) return "Unknown";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return escapeHtml(String(iso));
    const days = Math.floor((Date.now() - d.getTime()) / 86400000);
    if (days <= 0) return "Today";
    if (days === 1) return "1 day ago";
    return `${days} days ago`;
  }

  function confidenceBar(score) {
    const pct = Math.min(100, Math.max(0, Number(score) || 0));
    return `<div class="cc-confidence">
      <span class="cc-confidence-label">CONF</span>
      <div class="cc-confidence-bar"><div class="cc-confidence-fill" style="width:${pct}%"></div></div>
      <span class="cc-confidence-val">${escapeHtml(pct)}%</span>
    </div>`;
  }

  async function api(path, options = {}) {
    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.sheet_error || "Request failed");
    return data;
  }

  function emptyBlock(message) {
    return `<p class="cai-empty cc-empty-terminal">${escapeHtml(message || "No competitor data available")}</p>`;
  }

  function shopSectorHeader(g) {
    return `<div class="cc-shop-sector">
      <div class="cc-sector-label">SECTOR · ${escapeHtml(g.seller_name)} <span class="cc-sector-id">[${escapeHtml(g.seller_id)}]</span></div>
      <p class="cai-hint cc-sector-links">Shopee ${linkCell(g.shopee_link, "SHOPEE")} · TikTok ${linkCell(g.tiktok_link, "TIKTOK")}</p>`;
  }

  function shopGroupHeader(g) {
    return shopSectorHeader(g);
  }

  function updateSidebarTabHighlight(tab) {
    document.querySelectorAll(".nav-assortment").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.caiTab === tab);
    });
  }

  function setTab(name) {
    activeTab = name || "dashboard";
    Object.entries(panels).forEach(([key, el]) => {
      if (el) el.classList.toggle("hidden", key !== activeTab);
    });
    updateSidebarTabHighlight(activeTab);
    if (activeTab === "dashboard") {
      loadDashboard();
      loadTracker();
    }
    if (activeTab === "missing") loadMissing();
    if (activeTab === "review") loadReview();
    if (activeTab === "priceGap") loadPriceGap();
    if (activeTab === "newListings") loadNewListings();
  }

  function sideStatusBadge(label) {
    const s = (label || "NA").toUpperCase();
    const cls = s === "OK" ? "sip-badge sip-badge-ok" : "sip-badge sip-badge-na";
    return `<span class="${cls}">${escapeHtml(s)}</span>`;
  }

  async function loadTracker() {
    if (!trackerEl) return;
    trackerEl.innerHTML = '<p class="cai-hint">Loading COMPETITOR_TRACKER…</p>';
    try {
      const data = await api("/api/assortment/tracker");
      if (data.sheet_error && !data.sellers?.length) {
        trackerEl.innerHTML = emptyBlock(`Tracker connection: ${data.sheet_error}`);
        return;
      }
      const sellers = data.sellers || [];
      if (data.tab_empty) {
        trackerEl.innerHTML = emptyBlock(
          data.tab_empty_message || "COMPETITOR_TRACKER has no rows with Column C or D links."
        );
        return;
      }
      if (!sellers.length) {
        trackerEl.innerHTML = emptyBlock("No rows loaded from COMPETITOR_TRACKER.");
        return;
      }
      trackerEl.innerHTML = `
        <table class="cai-table">
          <thead><tr>
            <th>Row</th><th>Seller</th><th>Shopee Link (C)</th><th>TikTok Link (D)</th>
            <th>Shopee Status</th><th>TikTok Status</th><th>Shopee Reason</th><th>TikTok Reason</th>
            <th>Shopee Products</th><th>TikTok Products</th><th>Compare</th>
          </tr></thead>
          <tbody>
          ${sellers
            .map((s) => {
              const cmp = s.comparison || {};
              const compareTxt =
                cmp.both_accessible || cmp.matching_product_names != null
                  ? `match names: ${cmp.matching_product_names ?? 0} · only Shopee: ${cmp.only_on_shopee ?? "—"} · only TikTok: ${cmp.only_on_tiktok ?? "—"}`
                  : "—";
              return `<tr>
                <td>${escapeHtml(s.row_number ?? "—")}</td>
                <td>${escapeHtml(s.seller_name)}<br/><small>${escapeHtml(s.seller_id)}</small></td>
                <td>${linkCell(s.shopee_link)}</td>
                <td>${linkCell(s.tiktok_link)}</td>
                <td>${sideStatusBadge(s.shopee_status)}</td>
                <td>${sideStatusBadge(s.tiktok_status)}</td>
                <td class="cai-reason">${escapeHtml(s.shopee_reason || "—")}</td>
                <td class="cai-reason">${escapeHtml(s.tiktok_reason || "—")}</td>
                <td>${escapeHtml(s.shopee_products_found ?? 0)}</td>
                <td>${escapeHtml(s.tiktok_products_found ?? 0)}</td>
                <td class="cai-reason">${escapeHtml(compareTxt)}</td>
              </tr>`;
            })
            .join("")}
          </tbody>
        </table>
        <p class="cai-hint">${escapeHtml(data.row_count)} row(s) from tab ${escapeHtml(data.tab || "COMPETITOR_TRACKER")}</p>`;
    } catch (e) {
      trackerEl.innerHTML = emptyBlock(e.message);
    }
  }

  async function syncTracker() {
    if (syncStatusEl) syncStatusEl.textContent = "Syncing from COMPETITOR_TRACKER…";
    syncBtn?.setAttribute("disabled", "true");
    try {
      const data = await api("/api/assortment/sync-tracker", { method: "POST" });
      const msg = data.tab_empty
        ? data.tab_empty_message || "COMPETITOR_TRACKER tab has no data rows."
        : `Processed ${data.processed} rows · catalog OK ${data.catalog_ok} · NA ${data.catalog_na} · imported ${data.products_imported} products`;
      if (syncStatusEl) syncStatusEl.textContent = msg;
      await loadTracker();
      if (activeTab === "dashboard") await loadDashboard();
      else setTab(activeTab);
    } catch (e) {
      if (syncStatusEl) syncStatusEl.textContent = e.message;
    } finally {
      syncBtn?.removeAttribute("disabled");
    }
  }

  async function loadDashboard() {
    const m = await api("/api/assortment/dashboard");
    const priceGapCount = (m.higher_priced_products || 0) + (m.lower_priced_products || 0);
    const cards = [
      ["Total Products Compared", m.total_products_compared],
      ["Matched Products", m.matched_products],
      ["Missing Products", m.missing_products],
      ["Need Review", m.need_review_products],
      ["Price Gap", priceGapCount],
      ["New Listings", m.new_listings_recent ?? m.new_listings_today],
    ];
    let html = cards
      .map(
        ([label, value], i) => `
      <article class="cai-metric-card" style="animation-delay:${i * 0.06}s">
        <div class="label">${escapeHtml(label)}</div>
        <div class="value">${escapeHtml(value ?? 0)}</div>
      </article>`
      )
      .join("");
    if (!m.has_competitor_data) {
      html += emptyBlock(m.empty_message || "No competitor data available");
    }
    metricsEl.innerHTML = html;
  }

  function renderReconCards(groups) {
    return groups
      .map((g) => {
        const cards = (g.items || [])
          .map(
            (r) => `
        <article class="cc-recon-card">
          <div class="cc-recon-tag">RECON · MISSING FROM SHOPEE</div>
          ${imgCell(r.product_image_url, "cc-recon-img")}
          <h4 class="cc-recon-title">${escapeHtml(r.product_name)}</h4>
          <p class="cc-recon-shop">Shop: ${escapeHtml(g.seller_name || r.seller_name)}</p>
          <p>${linkCell(r.product_link, "PRODUCT INTEL")}</p>
          ${confidenceBar(r.confidence_score)}
          <p class="cai-reason cc-recon-reason">${escapeHtml(r.reason || "")}</p>
        </article>`
          )
          .join("");
        return `${shopSectorHeader(g)}<div class="cc-recon-grid">${cards}</div></div>`;
      })
      .join("");
  }

  async function loadMissing() {
    const el = document.getElementById("caiMissingTable");
    const data = await api("/api/assortment/missing");
    if (!data.has_competitor_data) {
      el.innerHTML = emptyBlock(data.empty_message);
      return;
    }
    const groups = data.groups || [];
    if (!groups.length) {
      el.innerHTML = '<p class="cai-empty">No TikTok products missing from Shopee.</p>';
      return;
    }
    el.innerHTML = renderReconCards(groups);
  }

  function renderVsPanel(r) {
    const shopee = r.shopee || {};
    const tiktok = r.tiktok || {};
    const sim = Math.min(100, Math.max(0, Number(r.similarity_score) || 0));
    return `
    <article class="cc-vs-panel">
      <div class="cc-vs-header">
        <div class="cc-vs-score">${escapeHtml(sim)}%</div>
        <p class="cai-hint">SIMILARITY INDEX · img ${escapeHtml(r.image_similarity)} · title ${escapeHtml(r.title_similarity)} · sku ${escapeHtml(r.sku_similarity)}</p>
        <div class="cc-vs-meter"><div class="cc-vs-meter-fill" style="width:${sim}%"></div></div>
      </div>
      <div class="cc-vs-grid">
        <div class="cc-vs-side">
          <h4>SHOPEE PRODUCT</h4>
          ${imgCell(shopee.product_image_url, "cc-vs-side-img")}
          <p class="cc-recon-title">${escapeHtml(shopee.product_name || "—")}</p>
          <p>${linkCell(shopee.product_link)}</p>
          <p class="cai-hint">SKU: ${skuList(shopee.sku_variations)}</p>
        </div>
        <div class="cc-vs-divider">VS</div>
        <div class="cc-vs-side">
          <h4>TIKTOK PRODUCT</h4>
          ${imgCell(tiktok.product_image_url, "cc-vs-side-img")}
          <p class="cc-recon-title">${escapeHtml(tiktok.product_name || "—")}</p>
          <p>${linkCell(tiktok.product_link)}</p>
          <p class="cai-hint">SKU: ${skuList(tiktok.sku_variations)}</p>
        </div>
      </div>
      <p class="cai-reason">${escapeHtml(r.reason || "")}</p>
      <p class="cai-hint"><strong>SKU comparison:</strong> Shopee [${skuList(r.sku_comparison?.shopee)}] vs TikTok [${skuList(r.sku_comparison?.tiktok)}]</p>
      <button type="button" class="btn btn-primary btn-sm" data-confirm-match="${r.match_id}">CONFIRM MATCH</button>
    </article>`;
  }

  async function loadReview() {
    const el = document.getElementById("caiReviewList");
    const data = await api("/api/assortment/need-review");
    if (!data.has_competitor_data) {
      el.innerHTML = emptyBlock(data.empty_message);
      return;
    }
    const groups = data.groups || [];
    if (!groups.length) {
      el.innerHTML = '<p class="cai-empty">Nothing needs review.</p>';
      return;
    }
    el.innerHTML = groups
      .map((g) => {
        const panels = (g.items || []).map(renderVsPanel).join("");
        return `${shopSectorHeader(g)}${panels}</div>`;
      })
      .join("");
    el.querySelectorAll("[data-confirm-match]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api(`/api/assortment/matches/${btn.dataset.confirmMatch}/confirm`, { method: "POST" });
        loadReview();
        loadDashboard();
      });
    });
  }

  function priceZoneMeta(band) {
    const b = (band || "").toLowerCase();
    if (b === "green") return { cls: "zone-green", badge: "competitive", label: "COMPETITIVE" };
    if (b === "yellow") return { cls: "zone-yellow", badge: "watch", label: "WATCH" };
    if (b === "red") return { cls: "zone-red", badge: "risk", label: "RISK" };
    return { cls: "", badge: "watch", label: "NA" };
  }

  async function loadPriceGap() {
    const el = document.getElementById("caiPriceGapTable");
    const data = await api("/api/assortment/price-gap");
    if (!data.has_competitor_data) {
      el.innerHTML = emptyBlock(data.empty_message);
      return;
    }
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = '<p class="cai-empty">No shop pairs for price gap analysis.</p>';
      return;
    }
    el.innerHTML = `<div class="cc-price-grid">${items
      .map((r) => {
        const zone = priceZoneMeta(r.price_gap_band);
        const gapTxt = r.price_gap_pct != null ? `${escapeHtml(r.price_gap_pct)}%` : "NA";
        return `
        <article class="cc-price-card ${zone.cls}">
          <span class="cc-heat-badge ${zone.badge}">${zone.label}</span>
          <h3>${escapeHtml(r.seller_name)}</h3>
          <p class="cai-hint">${linkCell(r.shopee_link, "SHOPEE")} · ${linkCell(r.tiktok_link, "TIKTOK")}</p>
          <dl class="cc-price-stats">
            <div><dt>Shopee avg (top)</dt><dd>${r.shopee_avg_price != null ? escapeHtml(r.shopee_avg_price) : "NA"}</dd></div>
            <div><dt>TikTok avg (top 10)</dt><dd>${r.tiktok_top10_avg_price != null ? escapeHtml(r.tiktok_top10_avg_price) : "NA"}</dd></div>
            <div><dt>Gap</dt><dd class="cc-gap-val">${gapTxt}</dd></div>
          </dl>
          <p class="cai-reason">${escapeHtml(r.reason || "—")}</p>
        </article>`;
      })
      .join("")}</div>`;
  }

  function renderSurveillanceFeed(groups) {
    return groups
      .map((g) => {
        const items = (g.items || [])
          .map((r) => {
            const when = formatRelativeTime(r.listed_at || r.first_detected_at);
            return `
          <div class="cc-feed-item">
            <div class="cc-feed-stamp">NEW DETECTED</div>
            <div class="cc-feed-time">${escapeHtml(when)}</div>
            <div class="cc-feed-body">
              ${imgCell(r.product_image_url, "cc-feed-img")}
              <div>
                <h4 class="cc-recon-title">${escapeHtml(r.product_name)}</h4>
                <p class="cc-recon-shop">Shop: ${escapeHtml(g.seller_name)}</p>
                <p>${linkCell(r.product_link, "TRACK PRODUCT")}</p>
                <p class="cai-reason">${escapeHtml(r.reason || "")}</p>
                <button type="button" class="btn btn-ghost btn-sm" data-dismiss-new="${r.competitor_product_id}">DISMISS ALERT</button>
              </div>
            </div>
          </div>`;
          })
          .join("");
        return `${shopSectorHeader(g)}<div class="cc-feed">${items}</div></div>`;
      })
      .join("");
  }

  async function loadNewListings() {
    const target = document.getElementById("caiNewListingsTable");
    const data = await api("/api/assortment/new-listings");
    if (!data.has_competitor_data) {
      target.innerHTML = emptyBlock(data.empty_message);
      return;
    }
    const groups = data.groups || [];
    if (!groups.length) {
      target.innerHTML = '<p class="cai-empty">No recent TikTok listings missing from Shopee (30 days).</p>';
      return;
    }
    target.innerHTML = renderSurveillanceFeed(groups);
    target.querySelectorAll("[data-dismiss-new]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api(`/api/assortment/new-listings/${btn.dataset.dismissNew}/dismiss`, { method: "POST" });
        loadNewListings();
        loadDashboard();
      });
    });
  }

  function parseImportJson(text) {
    const data = JSON.parse(text);
    if (Array.isArray(data)) return data;
    if (data.products && Array.isArray(data.products)) return data.products;
    throw new Error("JSON must be an array or { products: [...] }");
  }

  async function importOur() {
    const text = document.getElementById("caiImportOur").value.trim();
    const products = parseImportJson(text);
    const result = await api("/api/assortment/import/our-products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: "manual-ui", products }),
    });
    document.getElementById("caiImportStatus").textContent = `Imported ${result.imported} our products.`;
  }

  async function importCompetitor() {
    const text = document.getElementById("caiImportCompetitor").value.trim();
    const shopId = document.getElementById("caiImportShopId").value.trim() || null;
    const shopName = document.getElementById("caiImportShopName").value.trim() || null;
    const products = parseImportJson(text);
    const result = await api("/api/assortment/import/competitor-products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        label: "manual-ui",
        competitor_shop_id: shopId,
        competitor_shop_name: shopName,
        products,
        run_matching: true,
      }),
    });
    document.getElementById("caiImportStatus").textContent = `Imported ${result.imported} competitor products.`;
    setTab("dashboard");
  }

  document.getElementById("caiImportOurBtn")?.addEventListener("click", () => importOur().catch((e) => alert(e.message)));
  document.getElementById("caiImportCompetitorBtn")?.addEventListener("click", () => importCompetitor().catch((e) => alert(e.message)));
  document.getElementById("caiRunMatchingBtn")?.addEventListener("click", () =>
    api("/api/assortment/run-matching", { method: "POST" })
      .then((r) => {
        document.getElementById("caiImportStatus").textContent = `Matching done: ${JSON.stringify(r)}`;
        setTab("dashboard");
      })
      .catch((e) => alert(e.message))
  );
  syncBtn?.addEventListener("click", () => syncTracker().catch((e) => alert(e.message)));

  window.ShpAssortment = {
    onShow(tab) {
      setTab(tab || activeTab || "dashboard");
    },
    setTab,
  };
})();
