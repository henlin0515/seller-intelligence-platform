/**
 * Seller Intelligence Platform — shell navigation, home, learning center.
 */
(function () {
  const STORAGE_RECENT = "sip_recent_seller_searches_v1";
  const STORAGE_CONTEXT = "sip_seller_context_v1";

  const LEARNING_DATA = [
    {
      category: "Ads",
      items: [
        { title: "Paid Ads fundamentals", desc: "Spend, GMV, ROAS, take rate, and ADG% for RM reviews." },
        { title: "Campaign structure", desc: "How to plan and evaluate paid search and discovery ads." },
        { title: "ROAS optimization", desc: "When to scale, pause, or restructure ad accounts." },
      ],
    },
    {
      category: "MDV",
      items: [
        { title: "Joining MDV", desc: "Eligibility, onboarding steps, and seller education paths." },
        { title: "MDV ADGMV & ADG%", desc: "Contribution metrics and growth signals." },
        { title: "MDV best practices", desc: "Catalog, pricing, and promo alignment." },
      ],
    },
    {
      category: "AMS",
      items: [
        { title: "AMS overview", desc: "Affiliate Marketing Solutions spend and take rate." },
        { title: "AMS adoption", desc: "How to drive affiliate GMV contribution." },
      ],
    },
    {
      category: "MPA",
      items: [
        { title: "MPA / CPAS", desc: "Marketplace performance ads and GMV contribution." },
        { title: "Take rate benchmarks", desc: "Understanding MPA efficiency vs category norms." },
      ],
    },
    {
      category: "FBS",
      items: [
        { title: "FBS program guide", desc: "Fulfillment by Shopee benefits and requirements." },
        { title: "FBS GMV & ADO", desc: "How logistics metrics appear on the seller dashboard." },
      ],
    },
    {
      category: "Livestream",
      items: [
        { title: "Livestream hours", desc: "Seller LS hours and engagement drivers." },
        { title: "LS campaign playbooks", desc: "Peak-day and themed livestream strategies." },
      ],
    },
    {
      category: "Video",
      items: [
        { title: "Video commerce", desc: "Video ADGMV, ADG%, and new uploads." },
        { title: "Content cadence", desc: "Upload frequency and quality guidelines." },
      ],
    },
    {
      category: "Campaigns",
      items: [
        { title: "DDay & Payday ATC", desc: "Add-to-cart campaign participation." },
        { title: "Mega campaigns", desc: "9.9, 11.11, and seasonal seller readiness." },
        { title: "Voucher & bundle promos", desc: "Stacking rules and seller communication." },
      ],
    },
  ];

  const views = {
    home: document.getElementById("viewHome"),
    siDashboard: document.getElementById("viewSiDashboard"),
    siBusiness: document.getElementById("viewSiBusiness"),
    siHistoricalSob: document.getElementById("viewSiHistoricalSob"),
    siMapping: document.getElementById("viewSiMapping"),
    siAssortment: document.getElementById("viewSiAssortment"),
    siVoucher: document.getElementById("viewSiVoucher"),
    intelligence: document.getElementById("viewDashboard"),
    assistant: document.getElementById("viewAssistant"),
    learning: document.getElementById("viewLearning"),
    competitorTracker: document.getElementById("viewCompetitorTracker"),
    assortment: document.getElementById("viewAssortment"),
    settings: document.getElementById("viewSettings"),
  };

  const assistantSidebarTools = document.getElementById("assistantSidebarTools");
  const homeSellerCount = document.getElementById("homeSellerCount");
  const homeLastRefresh = document.getElementById("homeLastRefresh");
  const learningCategories = document.getElementById("learningCategories");
  const learningSearch = document.getElementById("learningSearch");
  const recentSearchesWrap = document.getElementById("recentSearchesWrap");
  const recentSearchesChips = document.getElementById("recentSearchesChips");
  const sellerContextBar = document.getElementById("sellerContextBar");
  const sellerContextName = document.getElementById("sellerContextName");
  const clearSellerContext = document.getElementById("clearSellerContext");
  const globalRefreshSheetBtn = document.getElementById("globalRefreshSheetBtn");
  const platformLastSync = document.getElementById("platformLastSync");
  const platformToast = document.getElementById("platformToast");

  let currentView = "home";
  let lastHomeStatus = null;
  let toastTimer = null;

  function i18n(key, fallback = "") {
    return window.SipI18n?.t(key, fallback) ?? fallback ?? key;
  }

  function formatRefreshed(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return "—";
    }
  }

  function updatePlatformLastSync(iso, loading = false) {
    if (!platformLastSync) return;
    platformLastSync.textContent = loading
      ? i18n("platform.refreshing", "Refreshing…")
      : formatRefreshed(iso);
    platformLastSync.dateTime = iso || "";
  }

  function showPlatformToast(message, kind = "success") {
    if (!platformToast || !message) return;
    platformToast.textContent = message;
    platformToast.classList.remove("hidden", "is-error");
    if (kind === "error") platformToast.classList.add("is-error");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      platformToast.classList.add("hidden");
    }, 4000);
  }

  async function fetchPlatformLastSync() {
    try {
      const res = await (window.SipApi ? window.SipApi.fetch : fetch)(
        "/api/intelligence/v1/seller-master/status",
        { credentials: "same-origin" }
      );
      if (!res.ok) return;
      const data = await res.json();
      updatePlatformLastSync(data.last_sync_at);
    } catch {
      /* ignore */
    }
  }

  async function reloadCurrentViewAfterRefresh(data) {
    window.ShpIntelligenceV1?.clearCache?.();

    const view = currentView;
    if (view === "home") {
      updateHomeStats({
        loaded: true,
        seller_count: data.ai_data_count,
        last_loaded_at: data.refreshed_at,
        loading: false,
      });
      return;
    }
    if (view === "intelligence" && window.ShpDashboard?.onSheetRefreshed) {
      await window.ShpDashboard.onSheetRefreshed(data);
      return;
    }
    if (view === "settings") {
      await loadSellerMasterSyncStatus();
      return;
    }
    if (view === "siMapping" && window.ShpMappingCenter?.init) {
      await window.ShpMappingCenter.init();
      return;
    }
    if (view === "siHistoricalSob" && window.ShpHistoricalSob?.load) {
      await window.ShpHistoricalSob.load(true);
      return;
    }
    if (
      (view === "siDashboard" ||
        view === "siBusiness" ||
        view === "siAssortment" ||
        view === "siVoucher") &&
      window.ShpIntelligenceV1?.onShow
    ) {
      await window.ShpIntelligenceV1.onShow(view);
    }
  }

  async function refreshAllSheetData() {
    if (globalRefreshSheetBtn) {
      globalRefreshSheetBtn.disabled = true;
      globalRefreshSheetBtn.classList.add("is-loading");
    }
    updatePlatformLastSync(null, true);
    try {
      const res = await (window.SipApi ? window.SipApi.fetch : fetch)(
        "/api/intelligence/v1/refresh-data",
        { method: "POST", credentials: "same-origin" }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || i18n("platform.refreshFailed"));
      updatePlatformLastSync(data.refreshed_at || data.sheets?.refreshed_at);
      showPlatformToast(i18n("platform.refreshSuccess", "Data updated"));
      window.ShpHistoricalSob?.clearCache?.();
      if (currentView === "siAssortment" && window.ShpIntelligenceV1?.refreshRadarProducts) {
        window.ShpIntelligenceV1.clearCache?.();
        await window.ShpIntelligenceV1.refreshRadarProducts();
      } else {
        await reloadCurrentViewAfterRefresh(data);
      }
      window.ShpMappingCenter?.load?.();
      return data;
    } catch (err) {
      showPlatformToast(
        err.message || i18n("platform.refreshFailed", "Could not refresh sheet data"),
        "error"
      );
      await fetchPlatformLastSync();
      throw err;
    } finally {
      if (globalRefreshSheetBtn) {
        globalRefreshSheetBtn.disabled = false;
        globalRefreshSheetBtn.classList.remove("is-loading");
      }
    }
  }

  function updateHomeStats(status) {
    if (!status) return;
    lastHomeStatus = status;
    if (homeSellerCount) {
      homeSellerCount.textContent =
        status.loaded && status.seller_count != null ? String(status.seller_count) : "—";
    }
    if (homeLastRefresh) {
      homeLastRefresh.textContent = status.loading
        ? i18n("home.statChecking", "Updating…")
        : status.loaded
          ? formatRefreshed(status.last_loaded_at)
          : "—";
    }
  }

  async function fetchAndUpdateHomeStats() {
    try {
      const res = await (window.SipApi ? window.SipApi.fetch : fetch)("/api/seller/status", {
        credentials: "same-origin",
      });
      if (!res.ok) throw new Error("status failed");
      const status = await res.json();
      updateHomeStats(status);
      return status;
    } catch {
      return null;
    }
  }

  function renderLearningCenter() {
    if (!learningCategories) return;
    learningCategories.innerHTML = LEARNING_DATA.map((cat) => {
      const cards = cat.items
        .map(
          (item) => `
        <article class="kb-card" data-search="${escapeAttr(
          `${cat.category} ${item.title} ${item.desc}`.toLowerCase()
        )}">
          <span class="kb-card-tag">${escapeHtml(cat.category)}</span>
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.desc)}</p>
        </article>`
        )
        .join("");
      return `
        <section class="learning-category" data-category="${escapeAttr(cat.category)}">
          <h2>${escapeHtml(cat.category)}</h2>
          <div class="kb-grid">${cards}</div>
        </section>`;
    }).join("");
  }

  function filterLearning(q) {
    const query = (q || "").trim().toLowerCase();
    document.querySelectorAll(".kb-card").forEach((card) => {
      const text = card.dataset.search || "";
      card.classList.toggle("hidden-by-filter", query.length > 0 && !text.includes(query));
    });
    document.querySelectorAll(".learning-category").forEach((sec) => {
      const visible = sec.querySelectorAll(".kb-card:not(.hidden-by-filter)").length;
      sec.style.display = visible === 0 && query ? "none" : "";
    });
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = String(text ?? "");
    return div.innerHTML;
  }

  function escapeAttr(text) {
    return String(text ?? "").replace(/"/g, "&quot;");
  }

  function getRecentSearches() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_RECENT) || "[]");
    } catch {
      return [];
    }
  }

  function addRecentSearch(shop) {
    if (!shop?.shop_name) return;
    const entry = {
      shop_id: shop.shop_id,
      shop_name: shop.shop_name,
      category: shop.category || "",
    };
    let list = getRecentSearches().filter((s) => String(s.shop_id) !== String(entry.shop_id));
    list.unshift(entry);
    list = list.slice(0, 8);
    localStorage.setItem(STORAGE_RECENT, JSON.stringify(list));
    renderRecentSearches();
  }

  function renderRecentSearches() {
    const list = getRecentSearches();
    if (!recentSearchesWrap || !recentSearchesChips) return;
    if (!list.length) {
      recentSearchesWrap.classList.add("hidden");
      return;
    }
    recentSearchesWrap.classList.remove("hidden");
    recentSearchesChips.innerHTML = list
      .map(
        (s) =>
          `<button type="button" class="recent-chip" data-shop-id="${escapeAttr(s.shop_id)}" data-shop-name="${escapeAttr(s.shop_name)}">${escapeHtml(s.shop_name)}</button>`
      )
      .join("");
    recentSearchesChips.querySelectorAll(".recent-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigate("intelligence");
        const input = document.getElementById("shopSearchInput");
        if (input) input.value = btn.dataset.shopName || "";
        if (window.ShpDashboard?.loadShop) {
          window.ShpDashboard.loadShop(btn.dataset.shopId);
        }
      });
    });
  }

  function setSellerContext(shop) {
    if (!shop) {
      localStorage.removeItem(STORAGE_CONTEXT);
      sellerContextBar?.classList.add("hidden");
      return;
    }
    localStorage.setItem(STORAGE_CONTEXT, JSON.stringify(shop));
    if (sellerContextName) sellerContextName.textContent = `${shop.shop_name} (${shop.shop_id})`;
    sellerContextBar?.classList.remove("hidden");
  }

  function loadSellerContext() {
    try {
      const raw = localStorage.getItem(STORAGE_CONTEXT);
      if (!raw) return;
      setSellerContext(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  }

  function navigate(view, options = {}) {
    currentView = view;
    const viewKey = view === "dashboard" ? "intelligence" : view;
    const caiTab = options.caiTab || null;

    document.querySelectorAll(".nav-main").forEach((btn) => {
      const v = btn.dataset.view;
      const tab = btn.dataset.caiTab;
      let active = v === viewKey || (view === "dashboard" && v === "intelligence");
      if (viewKey === "assortment" && v === "assortment") {
        active = tab === (caiTab || "dashboard");
      }
      btn.classList.toggle("active", active);
    });

    Object.entries(views).forEach(([key, el]) => {
      if (!el) return;
      el.classList.toggle("hidden", key !== viewKey);
    });

    const platformTopBar = document.getElementById("platformTopBar");
    if (platformTopBar) {
      platformTopBar.classList.toggle(
        "hidden",
        viewKey === "siBusiness" || viewKey === "siHistoricalSob"
      );
    }

    if (assistantSidebarTools) {
      assistantSidebarTools.classList.toggle("hidden", viewKey !== "assistant");
    }

    if (viewKey === "home") fetchAndUpdateHomeStats();
    if (viewKey === "intelligence" && window.ShpDashboard?.onShow) window.ShpDashboard.onShow();
    if (viewKey === "assistant") {
      renderRecentSearches();
      loadSellerContext();
    }
    if (viewKey === "learning" && !learningCategories?.innerHTML) renderLearningCenter();
    if (viewKey === "competitorTracker" && window.ShpCompetitorTracker?.onShow) {
      window.ShpCompetitorTracker.onShow();
    }
    if (viewKey === "settings") {
      loadSellerMasterSyncStatus();
    }
    if (viewKey === "assortment" && window.ShpAssortment?.onShow) {
      window.ShpAssortment.onShow(caiTab || "dashboard");
    }
    if (
      (viewKey === "siDashboard" ||
        viewKey === "siBusiness" ||
        viewKey === "siAssortment" ||
        viewKey === "siVoucher") &&
      window.ShpIntelligenceV1?.onShow
    ) {
      window.ShpIntelligenceV1.onShow(viewKey);
    }
    if (viewKey === "siMapping" && window.ShpMappingCenter?.init) {
      window.ShpMappingCenter.init();
    }
    if (viewKey === "siHistoricalSob" && window.ShpHistoricalSob?.init) {
      window.ShpHistoricalSob.init();
    }

    if (options.focusSearch) {
      setTimeout(() => document.getElementById("shopSearchInput")?.focus(), 120);
    }
  }

  document.querySelectorAll(".nav-main").forEach((btn) => {
    btn.addEventListener("click", () =>
      navigate(btn.dataset.view, { caiTab: btn.dataset.caiTab || null })
    );
  });

  document.querySelector(".sidebar-brand")?.addEventListener("click", () => navigate("home"));

  document.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.action;
      if (action === "open-intelligence") navigate("intelligence");
      else if (action === "search-seller") navigate("intelligence", { focusSearch: true });
      else if (action === "ask-ai") navigate("assistant");
    });
  });

  learningSearch?.addEventListener("input", () => filterLearning(learningSearch.value));

  clearSellerContext?.addEventListener("click", () => setSellerContext(null));

  learningCategories?.addEventListener("click", (e) => {
    const card = e.target.closest(".kb-card");
    if (!card) return;
    const title = card.querySelector("h3")?.textContent;
    if (!title) return;
    navigate("assistant");
    const input = document.getElementById("questionInput");
    if (input) {
      input.value = `Tell me about ${title} for Shopee sellers`;
      input.focus();
    }
  });

  window.ShpPlatform = {
    navigate,
    updateHomeStats,
    addRecentSearch,
    setSellerContext,
    getCurrentView: () => currentView,
    refreshAllSheetData,
    updatePlatformLastSync,
    showPlatformToast,
  };

  globalRefreshSheetBtn?.addEventListener("click", () => {
    refreshAllSheetData().catch(() => {});
  });

  window.SipI18n?.onChange?.((locale) => {
    if (lastHomeStatus) updateHomeStats(lastHomeStatus);
    fetchPlatformLastSync();
    window.SipI18n?.apply?.(document);
    renderLearningCenter();
    window.ShpDashboard?.onLocaleChange?.();
    if (currentView === "assistant" && window.ShpChat?.refreshWelcome) {
      window.ShpChat.refreshWelcome();
    }
  });

  function formatSellerMasterSyncTime(isoValue) {
    if (!isoValue) return null;
    const parsed = new Date(isoValue);
    if (Number.isNaN(parsed.getTime())) return isoValue;
    return parsed.toLocaleString();
  }

  async function loadSellerMasterSyncStatus() {
    const syncEl = document.getElementById("settingsSellerMasterSync");
    const metaEl = document.getElementById("settingsSellerMasterMeta");
    if (!syncEl) return;
    const pending =
      window.SipI18n?.t?.("settings.sellerMasterSyncPending", "Not synced yet") || "Not synced yet";
    syncEl.textContent = pending;
    if (metaEl) metaEl.textContent = "";
    try {
      const res = await (window.SipApi ? window.SipApi.fetch : fetch)(
        "/api/intelligence/v1/seller-master/status",
        { credentials: "same-origin" }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "status failed");
      syncEl.textContent = formatSellerMasterSyncTime(data.last_sync_at) || pending;
      if (metaEl) {
        const sellers = data.seller_count != null ? `${data.seller_count} sellers` : "";
        const tab = data.tab ? `tab: ${data.tab}` : "";
        const ttl = data.cache_ttl_sec ? `TTL: ${Math.round(data.cache_ttl_sec / 60)} min` : "";
        metaEl.textContent = [sellers, tab, ttl].filter(Boolean).join(" · ");
      }
    } catch {
      syncEl.textContent = pending;
    }
  }

  async function initAuthUi() {
    const logoutBtn = document.getElementById("logoutBtn");
    const authUserEl = document.getElementById("settingsAuthUser");
    try {
      const res = await (window.SipApi ? window.SipApi.fetch : fetch)("/api/auth/me", {
        credentials: "same-origin",
      });
      const data = await res.json();
      if (!data.authenticated) {
        window.location.replace("/login");
        return;
      }
      if (authUserEl && data.username) {
        authUserEl.textContent = `Signed in as ${data.username}`;
        authUserEl.classList.remove("hidden");
      }
    } catch {
      window.location.replace("/login");
      return;
    }
    logoutBtn?.addEventListener("click", async () => {
      try {
        await (window.SipApi ? window.SipApi.fetch : fetch)("/api/auth/logout", {
          method: "POST",
          credentials: "same-origin",
        });
      } finally {
        window.location.replace("/login");
      }
    });
  }

  renderLearningCenter();
  initAuthUi().then(() => {
    fetchAndUpdateHomeStats();
    fetchPlatformLastSync();
    navigate("siDashboard");
  });
})();
