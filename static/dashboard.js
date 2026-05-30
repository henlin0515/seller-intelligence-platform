/**
 * Seller Performance Dashboard — fixed executive layout for all sellers.
 */
(function () {
  const shopSearchInput = document.getElementById("shopSearchInput");
  const shopSearchBtn = document.getElementById("shopSearchBtn");
  const shopSearchResults = document.getElementById("shopSearchResults");
  const dashboardContent = document.getElementById("dashboardContent");
  const dashboardEmpty = document.getElementById("dashboardEmpty");
  const sellerSummaryCard = document.getElementById("sellerSummaryCard");
  const shopKpiBar = document.getElementById("shopKpiBar");
  const dashboardSections = document.getElementById("dashboardSections");
  const insightsSection = document.getElementById("insightsSection");
  const recommendationsSection = document.getElementById("recommendationsSection");
  const sellerCountLabel = document.getElementById("sellerCountLabel");
  const sheetLoadMeta = document.getElementById("sheetLoadMeta");
  const refreshSheetBtn = document.getElementById("refreshSheetBtn");
  const dashboardEmptyText = document.getElementById("dashboardEmptyText");
  const dashHeaderMeta = document.getElementById("dashHeaderMeta");
  const dashTopHeader = document.querySelector(".dash-top-header");
  const dashSearchSticky = document.getElementById("dashSearchSticky");

  const SECTION_RENDER_ORDER = [
    "shop_info",
    "paid_ads",
    "ams",
    "mpa",
    "fbs",
    "livestream",
    "video",
    "mdv",
  ];

  let selectedShopId = null;
  let sheetLoaded = false;

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = String(text ?? "");
    return div.innerHTML;
  }

  function growthClass(growth) {
    if (growth == null || Number.isNaN(growth)) return "growth-flat";
    if (growth > 0.5) return "growth-up";
    if (growth < -0.5) return "growth-down";
    return "growth-flat";
  }

  function badgeClass(status) {
    return `badge badge-${status || "neutral"}`;
  }

  function displayVal(v) {
    if (v == null || v === "" || v === "N/A") return "N/A";
    return String(v);
  }

  function renderSearchResults(results) {
    shopSearchResults.innerHTML = "";
    if (!results.length) {
      shopSearchResults.classList.add("hidden");
      return;
    }
    shopSearchResults.classList.remove("hidden");
    results.forEach((shop) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.innerHTML = `
        <span><strong>${escapeHtml(shop.shop_name)}</strong><br />
        <span class="shop-result-meta">${escapeHtml(shop.shop_id)} · ${escapeHtml(shop.category || "")}</span></span>
        <span class="shop-result-meta">Open →</span>`;
      btn.addEventListener("click", () => loadShop(shop.shop_id));
      li.appendChild(btn);
      shopSearchResults.appendChild(li);
    });
  }

  function setSearchEnabled(enabled) {
    shopSearchInput.disabled = !enabled;
    shopSearchBtn.disabled = !enabled;
  }

  function formatRefreshed(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return "—";
    }
  }

  function syncPlatformStats(status) {
    if (window.ShpPlatform?.updateHomeStats) window.ShpPlatform.updateHomeStats(status);
  }

  function renderHeaderStatus(status) {
    sheetLoaded = Boolean(status.loaded);
    syncPlatformStats(status);
    dashTopHeader?.classList.toggle("is-loading", Boolean(status.loading));

    if (status.loading) {
      sellerCountLabel.textContent = "…";
      sheetLoadMeta.textContent = "Loading…";
      setSearchEnabled(false);
      return;
    }

    if (status.error) {
      sellerCountLabel.textContent = "—";
      sheetLoadMeta.textContent = "Failed";
      if (dashHeaderMeta) dashHeaderMeta.textContent = status.error;
      setSearchEnabled(false);
      return;
    }

    if (status.loaded) {
      sellerCountLabel.textContent = String(status.seller_count ?? 0);
      sheetLoadMeta.textContent = formatRefreshed(status.last_loaded_at);
      if (dashHeaderMeta) {
        dashHeaderMeta.textContent = "Executive seller performance · live cache";
      }
      setSearchEnabled(true);
      if (dashboardEmptyText) {
        dashboardEmptyText.textContent =
          "Search by shop name or Shop ID to open the performance dashboard.";
      }
      return;
    }

    sellerCountLabel.textContent = "—";
    sheetLoadMeta.textContent = "Not loaded";
    setSearchEnabled(!status.live_sheets_configured);
  }

  async function fetchSheetStatus() {
    const res = await fetch("/api/seller/status");
    if (!res.ok) throw new Error("status failed");
    return res.json();
  }

  async function refreshSheetData() {
    setSearchEnabled(false);
    renderHeaderStatus({ loading: true, loaded: false });
    try {
      const res = await fetch("/api/seller/refresh", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "refresh failed");
      renderHeaderStatus(data);
      return data;
    } catch (err) {
      renderHeaderStatus({
        loaded: false,
        loading: false,
        error: String(err.message || err),
        live_sheets_configured: true,
      });
      throw err;
    }
  }

  async function ensureSheetLoaded() {
    try {
      let status = await fetchSheetStatus();
      renderHeaderStatus(status);
      if (!status.live_sheets_configured) {
        sheetLoaded = true;
        return status;
      }
      if (!status.loaded && !status.loading) {
        status = await refreshSheetData();
      }
      return status;
    } catch {
      return null;
    }
  }

  async function searchShops() {
    const q = shopSearchInput.value.trim();
    if (!q) return;
    if (!sheetLoaded) {
      shopSearchResults.innerHTML =
        "<li><button type='button' disabled>Load sheet data first (Refresh)</button></li>";
      shopSearchResults.classList.remove("hidden");
      return;
    }
    try {
      const res = await fetch(`/api/seller/search?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      if (!res.ok) throw new Error("search failed");
      renderSearchResults(data.results || []);
    } catch {
      shopSearchResults.innerHTML =
        "<li><button type='button' disabled>No shops found</button></li>";
      shopSearchResults.classList.remove("hidden");
    }
  }

  function healthClass(label) {
    const l = String(label || "").toLowerCase();
    if (l.includes("healthy") || l.includes("good")) return "health-good";
    if (l.includes("risk") || l.includes("critical")) return "health-risk";
    return "health-neutral";
  }

  function renderSellerSummary(shop, health) {
    const score = health?.score ?? "—";
    const label = health?.label || "Health";
    sellerSummaryCard.innerHTML = `
      <div class="seller-hero-inner">
        <div class="seller-hero-main">
          <p class="seller-hero-eyebrow">Seller profile</p>
          <h2 class="seller-hero-name">${escapeHtml(shop.shop_name || "—")}</h2>
          <div class="seller-hero-meta">
            <div class="hero-meta-pill"><span>Shop ID</span><strong>${escapeHtml(shop.shop_id || "N/A")}</strong></div>
            <div class="hero-meta-pill"><span>Tier</span><strong>${escapeHtml(shop.tier || "N/A")}</strong></div>
            <div class="hero-meta-pill"><span>Category</span><strong>${escapeHtml(shop.category || "N/A")}</strong></div>
            <div class="hero-meta-pill"><span>Lead</span><strong>${escapeHtml(shop.lead || "N/A")}</strong></div>
            <div class="hero-meta-pill"><span>BU</span><strong>${escapeHtml(shop.bu || "N/A")}</strong></div>
          </div>
        </div>
        <div class="seller-health-ring ${healthClass(label)}">
          <div class="health-score count-up" data-value="${escapeHtml(String(score))}">${escapeHtml(String(score))}</div>
          <div class="health-label">${escapeHtml(label)}</div>
        </div>
      </div>`;
    if (window.ShpPlatform) {
      window.ShpPlatform.setSellerContext?.({
        shop_id: shop.shop_id,
        shop_name: shop.shop_name,
        category: shop.category,
      });
      window.ShpPlatform.addRecentSearch?.(shop);
    }
  }

  function renderCommercialKpis(section) {
    if (!section || !shopKpiBar) return;
    shopKpiBar.innerHTML = (section.metrics || [])
      .map((m) => {
        const g = m.growth ?? m.growthPct;
        const health = m.healthStatus || "neutral";
        const isNa = displayVal(m.mtd_display) === "N/A";
        return `
        <article class="kpi-tile${isNa ? " kpi-tile-na" : ""}">
          <div class="kpi-tile-head">
            <span class="kpi-tile-name">${escapeHtml(m.label)}</span>
            <span class="${badgeClass(health)}">${escapeHtml(health)}</span>
          </div>
          <div class="kpi-tile-mtd count-up">${escapeHtml(displayVal(m.mtd_display))}</div>
          <div class="kpi-tile-row">
            <span>M-1</span>
            <span>${escapeHtml(displayVal(m.m1_display))}</span>
          </div>
          <div class="kpi-tile-growth ${growthClass(g)}">${escapeHtml(displayVal(m.growth_display))}</div>
        </article>`;
      })
      .join("");
  }

  function renderInsights(insights) {
    if (!insights) {
      insightsSection.innerHTML = "";
      return;
    }
    const block = (title, cls, items) => `
      <article class="insight-card ${cls}">
        <h3>${escapeHtml(title)}</h3>
        <ul>${(items || []).map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>
      </article>`;

    insightsSection.innerHTML = `
      <h2 class="dash-block-title">Strengths / Opportunities / Risks</h2>
      <div class="insights-grid">
        ${block("Strengths", "strengths", insights.strengths)}
        ${block("Opportunities", "opportunities", insights.opportunities)}
        ${block("Risks", "risks", insights.risks)}
      </div>`;
  }

  function renderMetricCard(m) {
    const g = m.growth ?? m.growthPct;
    const health = m.healthStatus || "neutral";
    const isNa = displayVal(m.mtd_display) === "N/A";
    return `
      <article class="metric-card${isNa ? " metric-card-na" : ""}">
        <div class="metric-card-label">${escapeHtml(m.label)}</div>
        <div class="metric-card-mtd">${escapeHtml(displayVal(m.mtd_display))}</div>
        <div class="metric-card-compare">
          <span>M-1</span>
          <span>${escapeHtml(displayVal(m.m1_display))}</span>
        </div>
        <div class="metric-card-foot">
          <span class="kpi-tile-growth ${growthClass(g)}">${escapeHtml(displayVal(m.growth_display))}</span>
          <span class="${badgeClass(health)}">${escapeHtml(health)}</span>
        </div>
      </article>`;
  }

  function renderMetricTableRows(metrics) {
    return metrics
      .map((m) => {
        const g = m.growth ?? m.growthPct;
        const health = m.healthStatus || "neutral";
        const naRow = displayVal(m.mtd_display) === "N/A" ? " row-na" : "";
        return `
        <tr class="${naRow}">
          <td><strong>${escapeHtml(m.label)}</strong></td>
          <td class="num">${escapeHtml(displayVal(m.mtd_display))}</td>
          <td class="num">${escapeHtml(displayVal(m.m1_display))}</td>
          <td class="num ${growthClass(g)}">${escapeHtml(displayVal(m.growth_display))}</td>
          <td><span class="${badgeClass(health)}">${escapeHtml(health)}</span></td>
        </tr>`;
      })
      .join("");
  }

  function renderShopInfoSection(section) {
    const items = (section.metrics || [])
      .map(
        (m) => `
        <div class="shop-info-item${displayVal(m.mtd_display) === "N/A" ? " shop-info-na" : ""}">
          <span>${escapeHtml(m.label)}</span>
          <strong>${escapeHtml(displayVal(m.mtd_display))}</strong>
        </div>`
      )
      .join("");

    return `
      <section class="dash-section dash-section-collapsible is-open" id="section-${escapeHtml(section.key)}">
        <button type="button" class="dash-section-toggle" aria-expanded="true">
          <h2>${escapeHtml(section.title)}</h2>
          <span class="toggle-chevron" aria-hidden="true"></span>
        </button>
        <div class="dash-section-body">
          <div class="shop-info-grid">${items}</div>
        </div>
      </section>`;
  }

  function renderMetricSection(section) {
    const metrics = section.metrics || [];
    return `
      <section class="dash-section dash-section-collapsible is-open" id="section-${escapeHtml(section.key)}">
        <button type="button" class="dash-section-toggle" aria-expanded="true">
          <h2>${escapeHtml(section.title)}</h2>
          <span class="toggle-chevron" aria-hidden="true"></span>
        </button>
        <div class="dash-section-body">
          <div class="metric-cards">${metrics.map(renderMetricCard).join("")}</div>
          <details class="metric-table-details">
            <summary>View detailed table</summary>
            <div class="metric-table-wrap">
              <table class="metric-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>MTD</th>
                    <th>M-1</th>
                    <th>Growth %</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>${renderMetricTableRows(metrics)}</tbody>
              </table>
            </div>
          </details>
        </div>
      </section>`;
  }

  function bindSectionToggles() {
    dashboardSections.querySelectorAll(".dash-section-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const section = btn.closest(".dash-section-collapsible");
        const open = section.classList.toggle("is-open");
        btn.setAttribute("aria-expanded", open ? "true" : "false");
      });
    });
  }

  function renderSections(sections) {
    const byKey = Object.fromEntries((sections || []).map((s) => [s.key, s]));
    const commercial = byKey.commercial;
    renderCommercialKpis(commercial);

    const html = SECTION_RENDER_ORDER.map((key) => {
      const section = byKey[key];
      if (!section) return "";
      if (key === "shop_info") return renderShopInfoSection(section);
      return renderMetricSection(section);
    }).join("");

    dashboardSections.innerHTML = html;
    bindSectionToggles();
    requestAnimationFrame(() => {
      document.querySelectorAll(".count-up").forEach((el) => {
        el.classList.add("count-up-done");
      });
    });
  }

  function renderRecommendations(recs) {
    const list = (recs || []).slice(0, 4);
    if (!list.length) {
      recommendationsSection.innerHTML = "";
      return;
    }
    recommendationsSection.innerHTML = `
      <h2 class="dash-block-title">AI Recommendation</h2>
      <div class="rec-grid">${list
        .map((r) => {
          const pri = (r.priority || "low").toLowerCase();
          return `
        <article class="rec-card priority-${pri}">
          <div class="rec-priority">${escapeHtml(r.priority)} priority</div>
          <h4>${escapeHtml(r.issue_found)}</h4>
          <p><strong>Action</strong><br />${escapeHtml(r.recommended_action)}</p>
          <p>${escapeHtml(r.supporting_data)}</p>
        </article>`;
        })
        .join("")}</div>`;
  }

  async function loadShop(shopId) {
    selectedShopId = shopId;
    dashboardEmpty.classList.add("hidden");
    dashboardContent.classList.remove("hidden");
    shopSearchResults.classList.add("hidden");

    sellerSummaryCard.innerHTML = '<p class="dash-loading">Loading seller…</p>';
    shopKpiBar.innerHTML = "";
    insightsSection.innerHTML = "";
    dashboardSections.innerHTML = "";
    recommendationsSection.innerHTML = "";
    document.getElementById("dashboardCharts").innerHTML = "";

    try {
      const res = await fetch(`/api/seller/${encodeURIComponent(shopId)}`);
      const data = await res.json();
      if (!res.ok) throw new Error("not found");

      renderSellerSummary(data.shop, data.health);
      renderSections(data.sections || []);
      renderInsights(data.insights);
      renderRecommendations(data.recommendations);

      if (window.renderDashboardCharts) {
        window.renderDashboardCharts(data.charts);
      }
    } catch {
      sellerSummaryCard.innerHTML =
        '<p class="dash-loading">Could not load shop. Refresh sheet data and try again.</p>';
      shopKpiBar.innerHTML = "";
      insightsSection.innerHTML = "";
      dashboardSections.innerHTML = "";
      recommendationsSection.innerHTML = "";
      document.getElementById("dashboardCharts").innerHTML = "";
    }
  }

  shopSearchBtn.addEventListener("click", searchShops);
  shopSearchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") searchShops();
  });

  refreshSheetBtn.addEventListener("click", async () => {
    refreshSheetBtn.disabled = true;
    try {
      await refreshSheetData();
      if (selectedShopId) await loadShop(selectedShopId);
    } finally {
      refreshSheetBtn.disabled = false;
    }
  });

  if (dashSearchSticky) {
    const scrollEl = document.querySelector(".dashboard-scroll");
    scrollEl?.addEventListener("scroll", () => {
      dashSearchSticky.classList.toggle("is-stuck", (scrollEl.scrollTop || 0) > 8);
    });
  }

  window.ShpDashboard = {
    async onShow() {
      setSearchEnabled(false);
      await ensureSheetLoaded();
      if (!selectedShopId) {
        dashboardEmpty.classList.remove("hidden");
        dashboardContent.classList.add("hidden");
      }
    },
    loadShop,
    refreshSheetData,
  };
})();
