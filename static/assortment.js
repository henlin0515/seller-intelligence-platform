/**
 * Competitor Assortment Intelligence — Tracker-backed UI.
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

  function imgCell(url) {
    if (!url) return "—";
    return `<img class="cai-thumb" src="${escapeHtml(url)}" alt="" loading="lazy" onerror="this.style.display='none'" />`;
  }

  function linkCell(url) {
    if (!url || url === "NA") return "NA";
    return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Link</a>`;
  }

  function skuList(arr) {
    if (!arr || !arr.length) return "—";
    return escapeHtml(arr.join(", "));
  }

  async function api(path, options = {}) {
    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.sheet_error || "Request failed");
    return data;
  }

  function emptyBlock(message) {
    return `<p class="cai-empty">${escapeHtml(message || "No competitor data available")}</p>`;
  }

  function shopGroupHeader(g) {
    return `<header class="cai-shop-header">
      <h3>${escapeHtml(g.seller_name)} <small>(${escapeHtml(g.seller_id)})</small></h3>
      <p>Shopee: ${linkCell(g.shopee_link)} · TikTok: ${linkCell(g.tiktok_link)}</p>
    </header>`;
  }

  function renderGroupedTables(groups, rowHtml) {
    if (!groups.length) return "";
    return groups
      .map(
        (g) => `${shopGroupHeader(g)}
      <table class="cai-table">
        <tbody>${(g.items || []).map(rowHtml).join("")}</tbody>
      </table>`
      )
      .join("");
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

  function statusBadge(status) {
    const s = (status || "na").toLowerCase();
    const cls = s === "ok" ? "sip-badge sip-badge-ok" : "sip-badge sip-badge-na";
    const label = s === "ok" ? "OK" : "NA";
    return `<span class="${cls}">${label}</span>`;
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
    const cards = [
      ["Total Products Compared", m.total_products_compared],
      ["Matched Products", m.matched_products],
      ["Missing Products", m.missing_products],
      ["Need Review Products", m.need_review_products],
      ["Higher Priced Products", m.higher_priced_products],
      ["Lower Priced Products", m.lower_priced_products],
      ["Recent New Listings (30d, not on Shopee)", m.new_listings_recent ?? m.new_listings_today],
    ];
    let html = cards
      .map(
        ([label, value]) => `
      <article class="cai-metric-card">
        <div class="label">${escapeHtml(label)}</div>
        <div class="value">${escapeHtml(value)}</div>
      </article>`
      )
      .join("");
    if (!m.has_competitor_data) {
      html += emptyBlock(m.empty_message || "No competitor data available");
    }
    metricsEl.innerHTML = html;
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
    el.innerHTML = renderGroupedTables(groups, (r) => `<tr>
      <td>${imgCell(r.product_image_url)}</td>
      <td>${escapeHtml(r.product_name)}</td>
      <td>${linkCell(r.product_link)}</td>
      <td>${skuList(r.sku_variations)}</td>
      <td>${escapeHtml(r.confidence_score)}%</td>
      <td class="cai-reason">${escapeHtml(r.reason || "")}</td>
    </tr>`);
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
        const cards = (g.items || [])
          .map((r) => {
            const shopee = r.shopee || {};
            const tiktok = r.tiktok || {};
            return `
        <article class="cai-review-card">
          <p><strong>Similarity:</strong> ${escapeHtml(r.similarity_score)}%
            (img ${escapeHtml(r.image_similarity)} · title ${escapeHtml(r.title_similarity)} · sku ${escapeHtml(r.sku_similarity)})</p>
          <p class="cai-reason">${escapeHtml(r.reason || "")}</p>
          <div class="cai-compare-grid">
            <div class="cai-compare-col">
              <h4>Shopee product</h4>
              ${imgCell(shopee.product_image_url)}
              <p>${escapeHtml(shopee.product_name || "—")}</p>
              <p>${linkCell(shopee.product_link)}</p>
              <p>SKU: ${skuList(shopee.sku_variations)}</p>
            </div>
            <div class="cai-compare-col">
              <h4>TikTok product</h4>
              ${imgCell(tiktok.product_image_url)}
              <p>${escapeHtml(tiktok.product_name || "—")}</p>
              <p>${linkCell(tiktok.product_link)}</p>
              <p>SKU: ${skuList(tiktok.sku_variations)}</p>
            </div>
          </div>
          <p><strong>SKU comparison:</strong> Shopee [${skuList(r.sku_comparison?.shopee)}] vs TikTok [${skuList(r.sku_comparison?.tiktok)}]</p>
          <button type="button" class="btn btn-primary btn-sm" data-confirm-match="${r.match_id}">Confirm match</button>
        </article>`;
          })
          .join("");
        return `${shopGroupHeader(g)}${cards}`;
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
    el.innerHTML = `
      <table class="cai-table">
        <thead><tr>
          <th>Shop</th><th>Shopee Link</th><th>TikTok Link</th>
          <th>Shopee Avg (top)</th><th>TikTok Avg (top 10)</th><th>Gap %</th><th>Status</th><th>Reason</th>
        </tr></thead>
        <tbody>
        ${items
          .map((r) => {
            const cls =
              r.price_gap_band === "green"
                ? "cai-gap-green"
                : r.price_gap_band === "yellow"
                  ? "cai-gap-yellow"
                  : r.price_gap_band === "red"
                    ? "cai-gap-red"
                    : "";
            return `<tr>
              <td>${escapeHtml(r.seller_name)}</td>
              <td>${linkCell(r.shopee_link)}</td>
              <td>${linkCell(r.tiktok_link)}</td>
              <td>${r.shopee_avg_price != null ? escapeHtml(r.shopee_avg_price) : "NA"}</td>
              <td>${r.tiktok_top10_avg_price != null ? escapeHtml(r.tiktok_top10_avg_price) : "NA"}</td>
              <td class="${cls}">${r.price_gap_pct != null ? escapeHtml(r.price_gap_pct) + "%" : "NA"}</td>
              <td>${escapeHtml(r.price_gap_band || r.status || "—")}</td>
              <td class="cai-reason">${escapeHtml(r.reason || "—")}</td>
            </tr>`;
          })
          .join("")}
        </tbody>
      </table>`;
  }

  async function loadNewListings() {
    const el = document.getElementById("caiNewListingsTable");
    const data = await api("/api/assortment/new-listings");
    if (!data.has_competitor_data) {
      el.innerHTML = emptyBlock(data.empty_message);
      return;
    }
    const groups = data.groups || [];
    if (!groups.length) {
      el.innerHTML = '<p class="cai-empty">No recent TikTok listings missing from Shopee (30 days).</p>';
      return;
    }
    el.innerHTML = renderGroupedTables(groups, (r) => `<tr>
      <td>${imgCell(r.product_image_url)}</td>
      <td>${escapeHtml(r.product_name)}</td>
      <td>${linkCell(r.product_link)}</td>
      <td>${escapeHtml(r.listed_at || r.first_detected_at || "—")}</td>
      <td class="cai-reason">${escapeHtml(r.reason || "")}</td>
      <td><button type="button" class="btn btn-ghost btn-sm" data-dismiss-new="${r.competitor_product_id}">Dismiss</button></td>
    </tr>`);
    el.querySelectorAll("[data-dismiss-new]").forEach((btn) => {
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
