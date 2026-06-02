/**
 * Seller Performance Dashboard — data-first executive layout.
 */
(function () {
  const apiFetch = (url, options) =>
    window.SipApi ? window.SipApi.fetch(url, options) : fetch(url, { credentials: "same-origin", ...options });

  const shopSearchInput = document.getElementById("shopSearchInput");
  const shopSearchBtn = document.getElementById("shopSearchBtn");
  const shopSearchResults = document.getElementById("shopSearchResults");
  const dashboardContent = document.getElementById("dashboardContent");
  const dashboardEmpty = document.getElementById("dashboardEmpty");
  const dashHealthHero = document.getElementById("dashHealthHero");
  const shopKpiBar = document.getElementById("shopKpiBar");
  const dashSellerMeta = document.getElementById("dashSellerMeta");
  const dashPaidAdsTerminal = document.getElementById("dashPaidAdsTerminal");
  const dashboardSections = document.getElementById("dashboardSections");
  const insightsSection = document.getElementById("insightsSection");
  const recommendationsSection = document.getElementById("recommendationsSection");
  const sellerCountLabel = document.getElementById("sellerCountLabel");
  const dashboardEmptyText = document.getElementById("dashboardEmptyText");
  const dashHeaderMeta = document.getElementById("dashHeaderMeta");
  const dashTopHeader = document.querySelector(".dash-top-header");
  const dashSearchSticky = document.getElementById("dashSearchSticky");

  const SECTION_RENDER_ORDER = ["ams", "mpa", "fbs", "livestream", "video", "mdv"];

  const PRIMARY_KPIS = [
    { section: "commercial", key: "adgmv", label: "ADGMV" },
    { section: "commercial", key: "ado", label: "ADO" },
    { section: "commercial", key: "uv", label: "UV" },
    { section: "paid_ads", key: "roas", label: "ROAS" },
    { section: "commercial", key: "item_order", label: "Orders" },
    { section: "paid_ads", key: "take_rate", label: "Take Rate" },
  ];

  const PAID_ADS_HERO = [
    { key: "ads_spend", label: "Ad Spend" },
    { key: "ads_gmv", label: "GMV" },
    { key: "roas", label: "ROAS" },
    { key: "take_rate", label: "Take Rate" },
  ];

  const PAID_ADS_SUPPORT = [
    { key: "adg_pct", label: "Adg%" },
    { key: "ads_adopted", label: "Ads Adopted" },
  ];

  let selectedShopId = null;
  let sheetLoaded = false;
  let lastDashboardStatus = null;

  function i18n(key, fallback = "") {
    return window.SipI18n?.t(key, fallback) ?? fallback ?? key;
  }

  function localizedSectionTitle(section) {
    return window.SipI18n?.sectionTitle(section.key, section.title) ?? section.title;
  }

  function localizedMetricLabel(sectionKey, m) {
    return window.SipI18n?.metricLabel(sectionKey, m.key, m.label) ?? m.label;
  }

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

  function growthArrow(growth) {
    if (growth == null || Number.isNaN(growth)) return "";
    if (growth > 0.5) return "↑";
    if (growth < -0.5) return "↓";
    return "→";
  }

  function badgeClass(status) {
    return `badge badge-${status || "neutral"}`;
  }

  function displayVal(v) {
    if (v == null || v === "" || v === "N/A") return "N/A";
    return String(v);
  }

  function sectionByKey(sections, key) {
    return (sections || []).find((s) => s.key === key);
  }

  function metricByKey(sections, sectionKey, metricKey) {
    const sec = sectionByKey(sections, sectionKey);
    return (sec?.metrics || []).find((m) => m.key === metricKey);
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
        <span class="shop-result-meta">${escapeHtml(i18n("intel.openResult", "Open →"))}</span>`;
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
    lastDashboardStatus = status;
    sheetLoaded = Boolean(status.loaded);
    syncPlatformStats(status);
    dashTopHeader?.classList.toggle("is-loading", Boolean(status.loading));

    if (status.loading) {
      sellerCountLabel.textContent = "…";
      setSearchEnabled(false);
      return;
    }

    if (!status.loaded) {
      sellerCountLabel.textContent = "—";
      if (dashHeaderMeta) {
        dashHeaderMeta.textContent = i18n("intel.meta", "Performance command center");
      }
      setSearchEnabled(false);
      return;
    }

    sellerCountLabel.textContent = String(status.seller_count ?? 0);
    if (dashHeaderMeta) {
      dashHeaderMeta.textContent = i18n(
        "intel.metaLoading",
        "Executive seller performance"
      );
    }
    setSearchEnabled(true);
    if (dashboardEmptyText) {
      dashboardEmptyText.textContent = i18n(
        "intel.emptyTextReady",
        "Search by shop name or Shop ID to open the performance dashboard."
      );
    }
  }

  function onLocaleChange() {
    if (lastDashboardStatus) renderHeaderStatus(lastDashboardStatus);
    window.SipI18n?.apply?.(document.getElementById("viewDashboard"));
    if (selectedShopId) loadShop(selectedShopId);
  }

  async function fetchSheetStatus() {
    const res = await apiFetch("/api/seller/status");
    if (!res.ok) throw new Error("status failed");
    return res.json();
  }

  async function refreshSheetData() {
    if (window.ShpPlatform?.refreshAllSheetData) {
      return window.ShpPlatform.refreshAllSheetData();
    }
    setSearchEnabled(false);
    renderHeaderStatus({ loading: true, loaded: false });
    try {
      const res = await apiFetch("/api/intelligence/v1/refresh-sheets", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "refresh failed");
      const status = {
        loaded: true,
        loading: false,
        seller_count: data.ai_data_count,
        last_loaded_at: data.refreshed_at,
      };
      renderHeaderStatus(status);
      if (window.ShpPlatform?.updatePlatformLastSync) {
        window.ShpPlatform.updatePlatformLastSync(data.refreshed_at);
      }
      return data;
    } catch (err) {
      renderHeaderStatus({ loaded: false, loading: false });
      throw err;
    }
  }

  async function ensureSheetLoaded() {
    try {
      let status = await fetchSheetStatus();
      renderHeaderStatus(status);
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
      shopSearchResults.innerHTML = `<li><button type='button' disabled>${escapeHtml(
        i18n("intel.loadFirst", "Load sheet data first (Refresh)")
      )}</button></li>`;
      shopSearchResults.classList.remove("hidden");
      return;
    }
    try {
      const res = await apiFetch(`/api/seller/search?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      if (!res.ok) throw new Error("search failed");
      renderSearchResults(data.results || []);
    } catch {
      shopSearchResults.innerHTML = `<li><button type='button' disabled>${escapeHtml(
        i18n("intel.noShops", "No shops found")
      )}</button></li>`;
      shopSearchResults.classList.remove("hidden");
    }
  }

  function healthClass(label) {
    const l = String(label || "").toLowerCase();
    if (l.includes("healthy") || l.includes("good")) return "health-good";
    if (l.includes("risk") || l.includes("critical") || l.includes("attention")) return "health-risk";
    return "health-neutral";
  }

  function primaryTrend(sections) {
    const adgmv = metricByKey(sections, "commercial", "adgmv");
    const g = adgmv?.growth ?? adgmv?.growthPct;
    const disp = adgmv?.growth_display;
    if (disp && disp !== "N/A" && disp !== "—") {
      return {
        text: `${disp} vs ${i18n("intel.m1", "M-1")}`,
        cls: growthClass(g),
      };
    }
    return { text: i18n("intel.trendUnavailable", "Trend unavailable"), cls: "growth-flat" };
  }

  function renderHealthHero(shop, health, sections) {
    const score = health?.score ?? "—";
    const label = health?.label || i18n("intel.health", "Health");
    const trend = primaryTrend(sections);
    const shopLine = shop?.shop_name
      ? `<p class="dash-health-shop">${escapeHtml(shop.shop_name)} <span>${escapeHtml(shop.shop_id || "")}</span></p>`
      : "";

    dashHealthHero.innerHTML = `
      <div class="dash-health-hero-inner ${healthClass(label)}">
        <div class="dash-health-copy">
          <p class="dash-health-eyebrow">${escapeHtml(i18n("intel.healthScore", "Health Score"))}</p>
          ${shopLine}
        </div>
        <div class="dash-health-score-block">
          <div class="dash-health-value count-up" data-value="${escapeHtml(String(score))}">${escapeHtml(String(score))}</div>
          <div class="dash-health-status">${escapeHtml(label)}</div>
          <div class="dash-health-trend ${trend.cls}">${escapeHtml(trend.text)}</div>
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

  function renderKpiTile(m, label) {
    const g = m?.growth ?? m?.growthPct;
    const isNa = !m || displayVal(m.mtd_display) === "N/A";
    return `
      <article class="dash-kpi-card${isNa ? " dash-kpi-card-na" : ""}">
        <span class="dash-kpi-label">${escapeHtml(label)}</span>
        <div class="dash-kpi-value count-up">${escapeHtml(displayVal(m?.mtd_display))}</div>
        <div class="dash-kpi-growth ${growthClass(g)}">
          <span class="dash-kpi-arrow" aria-hidden="true">${growthArrow(g)}</span>
          ${escapeHtml(displayVal(m?.growth_display))}
        </div>
        <span class="dash-kpi-period">${escapeHtml(i18n("intel.mtd", "MTD"))}</span>
      </article>`;
  }

  function renderPrimaryKpis(sections) {
    if (!shopKpiBar) return;
    shopKpiBar.innerHTML = PRIMARY_KPIS.map(({ section, key, label }) => {
      const m = metricByKey(sections, section, key);
      return renderKpiTile(m, label);
    }).join("");
  }

  function renderSellerMeta(shop, sections) {
    if (!dashSellerMeta) return;
    const info = sectionByKey(sections, "shop_info");
    const fromInfo = (key) => {
      const m = (info?.metrics || []).find((x) => x.key === key);
      return displayVal(m?.mtd_display);
    };

    const cells = [
      [i18n("intel.shopId", "Shop ID"), shop?.shop_id || fromInfo("shop_id")],
      [i18n("intel.sellerName", "Seller Name"), shop?.shop_name || fromInfo("shop_name")],
      ["BU", shop?.bu || fromInfo("bu")],
      [i18n("intel.lead", "Lead"), shop?.lead || fromInfo("lead")],
      [i18n("intel.bdOwner", "BD Owner"), fromInfo("bd_category")],
    ];

    dashSellerMeta.innerHTML = `
      <h2 class="dash-block-title">${escapeHtml(i18n("intel.sellerInfo", "Seller Information"))}</h2>
      <div class="dash-meta-row">
        ${cells
          .map(
            ([lbl, val]) => `
          <div class="dash-meta-cell">
            <span class="dash-meta-label">${escapeHtml(lbl)}</span>
            <span class="dash-meta-value">${escapeHtml(val)}</span>
          </div>`
          )
          .join("")}
      </div>`;
  }

  function renderPaidAdsTerminal(sections) {
    if (!dashPaidAdsTerminal) return;
    const paid = sectionByKey(sections, "paid_ads");
    const metrics = paid?.metrics || [];

    const heroHtml = PAID_ADS_HERO.map(({ key, label }) => {
      const m = metrics.find((x) => x.key === key);
      const g = m?.growth ?? m?.growthPct;
      return `
        <article class="dash-terminal-hero${displayVal(m?.mtd_display) === "N/A" ? " is-na" : ""}">
          <span class="dash-terminal-label">${escapeHtml(label)}</span>
          <div class="dash-terminal-value">${escapeHtml(displayVal(m?.mtd_display))}</div>
          <div class="dash-terminal-growth ${growthClass(g)}">${escapeHtml(displayVal(m?.growth_display))}</div>
          <span class="dash-terminal-period">${escapeHtml(i18n("intel.mtd", "MTD"))}</span>
        </article>`;
    }).join("");

    const supportHtml = PAID_ADS_SUPPORT.map(({ key, label }) => {
      const m = metrics.find((x) => x.key === key);
      return `
        <div class="dash-terminal-support">
          <span class="dash-terminal-support-label">${escapeHtml(label)}</span>
          <span class="dash-terminal-support-value">${escapeHtml(displayVal(m?.mtd_display))}</span>
        </div>`;
    }).join("");

    dashPaidAdsTerminal.innerHTML = `
      <h2 class="dash-block-title">${escapeHtml(i18n("intel.paidAds", "Paid Ads"))}</h2>
      <div class="dash-terminal-hero-row">${heroHtml}</div>
      <div class="dash-terminal-support-row">${supportHtml}</div>`;
  }

  function renderInsights(insights, recommendations) {
    if (!insights) {
      insightsSection.innerHTML = "";
      return;
    }

    const block = (title, cls, items) => `
      <article class="dash-insight-card ${cls}">
        <h3>${escapeHtml(title)}</h3>
        <ul>${(items || []).length ? (items || []).map((i) => `<li>${escapeHtml(i)}</li>`).join("") : `<li class="dash-insight-empty">${escapeHtml(i18n("intel.none", "None identified"))}</li>`}</ul>
      </article>`;

    const actionItems = (recommendations || []).slice(0, 4).map((r) => {
      const action = r.recommended_action || r.issue_found || "";
      return action ? `${r.priority ? `[${r.priority}] ` : ""}${action}` : "";
    }).filter(Boolean);

    insightsSection.innerHTML = `
      <h2 class="dash-block-title">${escapeHtml(i18n("intel.aiInsights", "AI Insights"))}</h2>
      <div class="dash-insights-grid">
        ${block(i18n("intel.opportunities", "Opportunity"), "opportunity", insights.opportunities)}
        ${block(i18n("intel.risks", "Risk"), "risk", insights.risks)}
        ${block(i18n("intel.actionItems", "Action Items"), "actions", actionItems.length ? actionItems : insights.strengths)}
      </div>`;
  }

  function renderMetricCard(m, sectionKey) {
    const g = m.growth ?? m.growthPct;
    const health = m.healthStatus || "neutral";
    const isNa = displayVal(m.mtd_display) === "N/A";
    return `
      <article class="metric-card${isNa ? " metric-card-na" : ""}">
        <div class="metric-card-label">${escapeHtml(localizedMetricLabel(sectionKey, m))}</div>
        <div class="metric-card-mtd">${escapeHtml(displayVal(m.mtd_display))}</div>
        <div class="metric-card-compare">
          <span>${escapeHtml(i18n("intel.m1", "M-1"))}</span>
          <span>${escapeHtml(displayVal(m.m1_display))}</span>
        </div>
        <div class="metric-card-foot">
          <span class="kpi-tile-growth ${growthClass(g)}">${escapeHtml(displayVal(m.growth_display))}</span>
          <span class="${badgeClass(health)}">${escapeHtml(health)}</span>
        </div>
      </article>`;
  }

  function renderMetricTableRows(metrics, sectionKey) {
    return metrics
      .map((m) => {
        const g = m.growth ?? m.growthPct;
        const health = m.healthStatus || "neutral";
        const naRow = displayVal(m.mtd_display) === "N/A" ? " row-na" : "";
        return `
        <tr class="${naRow}">
          <td><strong>${escapeHtml(localizedMetricLabel(sectionKey, m))}</strong></td>
          <td class="num">${escapeHtml(displayVal(m.mtd_display))}</td>
          <td class="num">${escapeHtml(displayVal(m.m1_display))}</td>
          <td class="num ${growthClass(g)}">${escapeHtml(displayVal(m.growth_display))}</td>
          <td><span class="${badgeClass(health)}">${escapeHtml(health)}</span></td>
        </tr>`;
      })
      .join("");
  }

  function renderMetricSection(section) {
    const metrics = section.metrics || [];
    const sk = section.key;
    return `
      <section class="dash-section dash-section-collapsible is-open" id="section-${escapeHtml(section.key)}">
        <button type="button" class="dash-section-toggle" aria-expanded="true">
          <h2>${escapeHtml(localizedSectionTitle(section))}</h2>
          <span class="toggle-chevron" aria-hidden="true"></span>
        </button>
        <div class="dash-section-body">
          <div class="metric-cards">${metrics.map((m) => renderMetricCard(m, sk)).join("")}</div>
          <details class="metric-table-details">
            <summary>${escapeHtml(i18n("intel.viewTable", "View detailed table"))}</summary>
            <div class="metric-table-wrap">
              <table class="metric-table">
                <thead>
                  <tr>
                    <th>${escapeHtml(i18n("intel.metric", "Metric"))}</th>
                    <th>${escapeHtml(i18n("intel.mtd", "MTD"))}</th>
                    <th>${escapeHtml(i18n("intel.m1", "M-1"))}</th>
                    <th>${escapeHtml(i18n("intel.growth", "Growth %"))}</th>
                    <th>${escapeHtml(i18n("intel.status", "Status"))}</th>
                  </tr>
                </thead>
                <tbody>${renderMetricTableRows(metrics, sk)}</tbody>
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
    const html = SECTION_RENDER_ORDER.map((key) => {
      const section = byKey[key];
      if (!section) return "";
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

  function clearDashboardPanels() {
    const loading = `<p class="dash-loading">${escapeHtml(i18n("intel.loadingSeller", "Loading seller…"))}</p>`;
    if (dashHealthHero) dashHealthHero.innerHTML = loading;
    if (shopKpiBar) shopKpiBar.innerHTML = "";
    if (dashSellerMeta) dashSellerMeta.innerHTML = "";
    if (dashPaidAdsTerminal) dashPaidAdsTerminal.innerHTML = "";
    insightsSection.innerHTML = "";
    dashboardSections.innerHTML = "";
    if (recommendationsSection) recommendationsSection.innerHTML = "";
    document.getElementById("dashboardCharts").innerHTML = "";
  }

  async function loadShop(shopId) {
    selectedShopId = shopId;
    dashboardEmpty.classList.add("hidden");
    dashboardContent.classList.remove("hidden");
    shopSearchResults.classList.add("hidden");
    clearDashboardPanels();

    try {
      const res = await apiFetch(`/api/seller/${encodeURIComponent(shopId)}`);
      const data = await res.json();
      if (!res.ok) throw new Error("not found");

      const sections = data.sections || [];
      renderHealthHero(data.shop, data.health, sections);
      renderPrimaryKpis(sections);
      renderInsights(data.insights, data.recommendations);
      renderSellerMeta(data.shop, sections);
      renderPaidAdsTerminal(sections);
      renderSections(sections);

      if (window.renderDashboardCharts) {
        window.renderDashboardCharts(data.charts);
      }
    } catch {
      if (dashHealthHero) {
        dashHealthHero.innerHTML = `<p class="dash-loading">${escapeHtml(
          i18n("intel.loadFailed", "Could not load shop. Refresh sheet data and try again.")
        )}</p>`;
      }
      if (shopKpiBar) shopKpiBar.innerHTML = "";
      if (dashSellerMeta) dashSellerMeta.innerHTML = "";
      if (dashPaidAdsTerminal) dashPaidAdsTerminal.innerHTML = "";
      insightsSection.innerHTML = "";
      dashboardSections.innerHTML = "";
      document.getElementById("dashboardCharts").innerHTML = "";
    }
  }

  shopSearchBtn.addEventListener("click", searchShops);
  shopSearchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") searchShops();
  });

  if (dashSearchSticky) {
    const scrollEl = document.querySelector(".dashboard-scroll");
    scrollEl?.addEventListener("scroll", () => {
      dashSearchSticky.classList.toggle("is-stuck", (scrollEl.scrollTop || 0) > 8);
    });
  }

  window.SipI18n?.onChange?.(onLocaleChange);

  window.ShpDashboard = {
    async onShow() {
      setSearchEnabled(false);
      await ensureSheetLoaded();
      if (!selectedShopId) {
        dashboardEmpty.classList.remove("hidden");
        dashboardContent.classList.add("hidden");
      }
    },
    async onSheetRefreshed(data) {
      renderHeaderStatus({
        loaded: true,
        loading: false,
        seller_count: data.ai_data_count,
        last_loaded_at: data.refreshed_at,
      });
      if (selectedShopId) await loadShop(selectedShopId);
    },
    loadShop,
    refreshSheetData,
    onLocaleChange,
  };
})();
