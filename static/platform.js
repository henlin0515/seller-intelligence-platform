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
    intelligence: document.getElementById("viewDashboard"),
    assistant: document.getElementById("viewAssistant"),
    learning: document.getElementById("viewLearning"),
    settings: document.getElementById("viewSettings"),
  };

  const assistantSidebarTools = document.getElementById("assistantSidebarTools");
  const homeSellerCount = document.getElementById("homeSellerCount");
  const homeLastRefresh = document.getElementById("homeLastRefresh");
  const homeSheetStatus = document.getElementById("homeSheetStatus");
  const learningCategories = document.getElementById("learningCategories");
  const learningSearch = document.getElementById("learningSearch");
  const recentSearchesWrap = document.getElementById("recentSearchesWrap");
  const recentSearchesChips = document.getElementById("recentSearchesChips");
  const sellerContextBar = document.getElementById("sellerContextBar");
  const sellerContextName = document.getElementById("sellerContextName");
  const clearSellerContext = document.getElementById("clearSellerContext");

  let currentView = "home";
  let lastHomeStatus = null;

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

  function updateHomeStats(status) {
    if (!status) return;
    lastHomeStatus = status;
    if (homeSellerCount) {
      homeSellerCount.textContent =
        status.loaded && status.seller_count != null ? String(status.seller_count) : "—";
    }
    if (homeLastRefresh) {
      homeLastRefresh.textContent = status.loaded
        ? formatRefreshed(status.last_loaded_at)
        : status.loading
          ? i18n("home.statChecking", "Checking…")
          : "—";
    }
    if (homeSheetStatus) {
      if (status.loading) {
        homeSheetStatus.textContent = i18n("home.statRefreshing", "Refreshing…");
        homeSheetStatus.className = "stat-card-value status-warn";
      } else if (status.error) {
        homeSheetStatus.textContent = i18n("home.statError", "Error");
        homeSheetStatus.className = "stat-card-value";
      } else if (status.loaded) {
        homeSheetStatus.textContent = i18n("home.statConnected", "Connected");
        homeSheetStatus.className = "stat-card-value status-ok";
      } else if (status.live_sheets_configured === false) {
        homeSheetStatus.textContent = i18n("home.statMock", "Mock data");
        homeSheetStatus.className = "stat-card-value status-warn";
      } else {
        homeSheetStatus.textContent = i18n("home.statNotLoaded", "Not loaded");
        homeSheetStatus.className = "stat-card-value status-warn";
      }
    }
  }

  async function fetchAndUpdateHomeStats() {
    try {
      const res = await fetch("/api/seller/status");
      if (!res.ok) throw new Error("status failed");
      const status = await res.json();
      updateHomeStats(status);
      return status;
    } catch {
      if (homeSheetStatus) {
        homeSheetStatus.textContent = i18n("home.statUnavailable", "Unavailable");
        homeSheetStatus.className = "stat-card-value";
      }
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

    document.querySelectorAll(".nav-main").forEach((btn) => {
      const v = btn.dataset.view;
      btn.classList.toggle("active", v === viewKey || (view === "dashboard" && v === "intelligence"));
    });

    Object.entries(views).forEach(([key, el]) => {
      if (!el) return;
      el.classList.toggle("hidden", key !== viewKey);
    });

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

    if (options.focusSearch) {
      setTimeout(() => document.getElementById("shopSearchInput")?.focus(), 120);
    }
  }

  document.querySelectorAll(".nav-main").forEach((btn) => {
    btn.addEventListener("click", () => navigate(btn.dataset.view));
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
  };

  window.SipI18n?.onChange?.((locale) => {
    if (lastHomeStatus) updateHomeStats(lastHomeStatus);
    window.SipI18n?.apply?.(document);
    renderLearningCenter();
    window.ShpDashboard?.onLocaleChange?.();
    if (currentView === "assistant" && window.ShpChat?.refreshWelcome) {
      window.ShpChat.refreshWelcome();
    }
  });

  renderLearningCenter();
  fetchAndUpdateHomeStats();
  navigate("home");
})();
