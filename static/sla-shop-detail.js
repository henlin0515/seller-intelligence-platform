/**
 * SLA expandable shop detail — DateRangeSelector, ShopDetailMetricsCards, row binding.
 * Vanilla JS modules exposed as window.SlaShopDetail.
 */
(function () {
  const API = "/api/seller-level-analysis/shop-detail";
  const COL_COUNT = 9;
  const PRESETS = [
    { id: "7", label: "近7天", days: 7 },
    { id: "28", label: "近28天", days: 28 },
    { id: "90", label: "近90天", days: 90 },
    { id: "180", label: "近180天", days: 180 },
  ];
  const METRICS = [
    { key: "sales_volume", label: "銷量", format: "compact" },
    { key: "sales_amount", label: "銷售額", format: "php" },
    { key: "creator_count", label: "帶貨達人數", format: "compact" },
    { key: "live_count", label: "帶貨直播數", format: "compact" },
    { key: "video_count", label: "帶貨視頻數", format: "compact" },
    { key: "active_product_count", label: "動銷商品數", format: "compact" },
  ];

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isoToday() {
    return new Date().toISOString().slice(0, 10);
  }

  function isoDaysAgo(days) {
    const d = new Date();
    d.setDate(d.getDate() - (days - 1));
    return d.toISOString().slice(0, 10);
  }

  function defaultDetailState() {
    return {
      preset: "7",
      startDate: isoDaysAgo(7),
      endDate: isoToday(),
      customStart: "",
      customEnd: "",
      selected: new Set(["sales_volume", "sales_amount"]),
      loading: false,
      error: null,
      data: null,
      fetchedKey: null,
    };
  }

  function hasTikTokData(seller) {
    if (!seller) return false;
    if (String(seller.platform_source || "").toUpperCase() === "SHOPEE_ONLY") return false;
    const status = String(seller.fastmoss_match_status || "").toUpperCase();
    if (status === "NOT_FOUND") return false;
    return Boolean(String(seller.fastmoss_shop_id || "").trim());
  }

  function fmtCompact(n) {
    const num = Number(n);
    if (!Number.isFinite(num)) return "—";
    if (Math.abs(num) >= 1_000_000) return `${(num / 1_000_000).toFixed(2).replace(/\.?0+$/, "")}m`;
    if (Math.abs(num) >= 10_000) return `${(num / 10_000).toFixed(2).replace(/\.?0+$/, "")}万`;
    if (Math.abs(num) >= 1_000) return `${(num / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
    return String(Math.round(num));
  }

  function fmtPhp(n) {
    const num = Number(n);
    if (!Number.isFinite(num)) return "—";
    if (Math.abs(num) >= 1_000_000) return `₱${(num / 1_000_000).toFixed(2)}m`;
    if (Math.abs(num) >= 10_000) return `₱${(num / 10_000).toFixed(2)}万`;
    return `₱${num.toLocaleString("en-PH", { maximumFractionDigits: 0 })}`;
  }

  function formatMetricValue(key, value) {
    const spec = METRICS.find((m) => m.key === key);
    if (!spec) return escapeHtml(String(value ?? "—"));
    if (spec.format === "php") return escapeHtml(fmtPhp(value));
    return escapeHtml(fmtCompact(value));
  }

  function rangeKey(startDate, endDate) {
    return `${startDate}|${endDate}`;
  }

  function applyPreset(presetId) {
    const preset = PRESETS.find((p) => p.id === presetId);
    if (!preset) return { startDate: isoDaysAgo(7), endDate: isoToday() };
    return { startDate: isoDaysAgo(preset.days), endDate: isoToday() };
  }

  /** @returns {string} DateRangeSelector HTML */
  function DateRangeSelector(shopId, detailState) {
    const preset = detailState.preset || "7";
    const customActive = preset === "custom";
    const presetBtns = PRESETS.map(
      (p) =>
        `<button type="button" class="si-sla-detail-range__btn${
          preset === p.id ? " is-active" : ""
        }" data-sla-detail-preset="${p.id}" data-shop-id="${escapeHtml(shopId)}">${escapeHtml(
          p.label
        )}</button>`
    ).join("");

    return `
      <div class="si-sla-detail-range" data-sla-detail-range data-shop-id="${escapeHtml(shopId)}">
        <div class="si-sla-detail-range__presets">${presetBtns}</div>
        <div class="si-sla-detail-range__custom${customActive ? " is-active" : ""}">
          <input type="date" class="si-sla-detail-range__date" data-sla-detail-start value="${escapeHtml(
            detailState.startDate || ""
          )}" aria-label="Start date" />
          <span class="si-sla-detail-range__sep">→</span>
          <input type="date" class="si-sla-detail-range__date" data-sla-detail-end value="${escapeHtml(
            detailState.endDate || ""
          )}" aria-label="End date" />
          <button type="button" class="si-sla-detail-range__btn si-sla-detail-range__btn--custom${
            customActive ? " is-active" : ""
          }" data-sla-detail-preset="custom" data-shop-id="${escapeHtml(shopId)}">自訂</button>
        </div>
      </div>`;
  }

  /** @returns {string} ShopDetailMetricsCards HTML */
  function ShopDetailMetricsCards(metrics, selectedSet) {
    if (!metrics) {
      return `<div class="si-sla-detail-metrics si-sla-detail-metrics--empty"><p>No metrics for this range.</p></div>`;
    }
    const cards = METRICS.map((m) => {
      const isSelected = selectedSet.has(m.key);
      return `
        <button type="button" class="si-sla-detail-metric${isSelected ? " is-selected" : ""}" data-sla-detail-metric="${m.key}" aria-pressed="${isSelected ? "true" : "false"}">
          <span class="si-sla-detail-metric__check" aria-hidden="true">${isSelected ? "✓" : ""}</span>
          <span class="si-sla-detail-metric__value">${formatMetricValue(m.key, metrics[m.key])}</span>
          <span class="si-sla-detail-metric__label">${escapeHtml(m.label)}</span>
        </button>`;
    }).join("");
    return `<div class="si-sla-detail-metrics">${cards}</div>`;
  }

  function renderDetailBody(seller, detailState) {
    if (!hasTikTokData(seller)) {
      return `
        <div class="si-sla-detail-panel__state si-sla-detail-panel__state--empty">
          <p>No TikTok / FastMoss data available for this shop.</p>
        </div>`;
    }

    if (detailState.loading) {
      return `
        <div class="si-sla-detail-panel__state si-sla-detail-panel__state--loading" role="status">
          <div class="si-sla-detail-spinner" aria-hidden="true"></div>
          <p>Loading trend data…</p>
        </div>`;
    }

    if (detailState.error) {
      return `
        <div class="si-sla-detail-panel__state si-sla-detail-panel__state--error" role="alert">
          <p>${escapeHtml(detailState.error)}</p>
          <button type="button" class="si-sla-detail-retry" data-sla-detail-retry data-shop-id="${escapeHtml(
            seller.shop_id
          )}">Retry</button>
        </div>`;
    }

    const data = detailState.data;
    if (!data || !data.available) {
      const msg = data?.message || "No TikTok / FastMoss data available for this shop.";
      return `
        <div class="si-sla-detail-panel__state si-sla-detail-panel__state--empty">
          <p>${escapeHtml(msg)}</p>
        </div>`;
    }

    if (data.empty) {
      return `
        <div class="si-sla-detail-panel__header">
          <h4 class="si-sla-detail-panel__title">數據趨勢</h4>
          ${DateRangeSelector(seller.shop_id, detailState)}
        </div>
        <div class="si-sla-detail-panel__state si-sla-detail-panel__state--empty">
          <p>${escapeHtml(data.message || "No trend data for this date range.")}</p>
        </div>`;
    }

    return `
      <div class="si-sla-detail-panel__header">
        <h4 class="si-sla-detail-panel__title">數據趨勢</h4>
        ${DateRangeSelector(seller.shop_id, detailState)}
      </div>
      <p class="si-sla-detail-panel__meta">${escapeHtml(data.fastmoss_shop_name || seller.fastmoss_matched_shop || "")} · ${escapeHtml(
      detailState.startDate
    )} → ${escapeHtml(detailState.endDate)}</p>
      ${ShopDetailMetricsCards(data.metrics, detailState.selected)}`;
  }

  /** Expandable detail row placed directly under the shop row. */
  function ShopDetailExpandableRow(seller, isOpen, detailState) {
    const openClass = isOpen ? " is-open" : "";
    return `
      <tr class="si-sla-detail-row${openClass}" data-sla-detail-row data-shop-id="${escapeHtml(
      seller.shop_id
    )}" aria-hidden="${isOpen ? "false" : "true"}">
        <td colspan="${COL_COUNT}">
          <div class="si-sla-detail-panel${openClass}">
            ${renderDetailBody(seller, detailState)}
          </div>
        </td>
      </tr>`;
  }

  function renderChevron(isOpen) {
    return `<button type="button" class="si-sla-row-toggle" data-sla-row-toggle aria-expanded="${
      isOpen ? "true" : "false"
    }" aria-label="${isOpen ? "Collapse shop detail" : "Expand shop detail"}">
      <svg class="si-sla-row-toggle__icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <path fill="currentColor" d="M9.29 6.71a1 1 0 0 1 1.42 0L15 11l-4.29 4.29a1 1 0 0 1-1.42-1.42L12.17 11 9.29 8.12a1 1 0 0 1 0-1.41z"/>
      </svg>
    </button>`;
  }

  async function fetchShopDetail(seller, startDate, endDate) {
    const params = new URLSearchParams({
      shopee_shop_id: String(seller.shop_id || ""),
      start_date: startDate,
      end_date: endDate,
    });
    if (seller.fastmoss_shop_id) params.set("fastmoss_shop_id", String(seller.fastmoss_shop_id));
    if (seller.tiktok_shop_name) params.set("tiktok_shop_id", String(seller.tiktok_shop_name));
    if (seller.platform_source) params.set("platform_source", String(seller.platform_source));

    const fetchFn = window.SipApi?.fetch || fetch;
    const res = await fetchFn(`${API}?${params.toString()}`, { credentials: "same-origin" });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body.detail || body.message || `Request failed (${res.status})`);
    }
    return body;
  }

  function getSellerMap(sellers) {
    const map = new Map();
    (sellers || []).forEach((s) => {
      if (s?.shop_id) map.set(String(s.shop_id), s);
    });
    return map;
  }

  function refreshDetailRowDOM(tableRoot, seller, detailState, isOpen) {
    const row = tableRoot.querySelector(`[data-sla-detail-row][data-shop-id="${CSS.escape(String(seller.shop_id))}"]`);
    if (!row) return;
    row.classList.toggle("is-open", isOpen);
    row.setAttribute("aria-hidden", isOpen ? "false" : "true");
    const panel = row.querySelector(".si-sla-detail-panel");
    if (panel) {
      panel.classList.toggle("is-open", isOpen);
      panel.innerHTML = renderDetailBody(seller, detailState);
    }
  }

  async function loadDetailForShop(seller, detailState, tableRoot, isOpen) {
    if (!hasTikTokData(seller)) {
      refreshDetailRowDOM(tableRoot, seller, detailState, isOpen);
      return;
    }

    const key = rangeKey(detailState.startDate, detailState.endDate);
    if (detailState.fetchedKey === key && detailState.data && !detailState.error) {
      refreshDetailRowDOM(tableRoot, seller, detailState, isOpen);
      return;
    }

    detailState.loading = true;
    detailState.error = null;
    refreshDetailRowDOM(tableRoot, seller, detailState, isOpen);

    try {
      const data = await fetchShopDetail(seller, detailState.startDate, detailState.endDate);
      detailState.data = data;
      detailState.fetchedKey = key;
      detailState.error = data.error ? data.message || "Could not load trend data." : null;
    } catch (err) {
      detailState.error = err.message || "Could not load trend data.";
      detailState.data = null;
    } finally {
      detailState.loading = false;
      refreshDetailRowDOM(tableRoot, seller, detailState, isOpen);
    }
  }

  function bindDetailPanelEvents(tableRoot, sellerMap, expandedSet, detailCache) {
    tableRoot.querySelectorAll("[data-sla-row-toggle]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const row = btn.closest("[data-shop-id]");
        const shopId = row?.dataset?.shopId;
        if (!shopId) return;
        const seller = sellerMap.get(shopId);
        if (!seller) return;

        if (expandedSet.has(shopId)) {
          expandedSet.delete(shopId);
          row.classList.remove("is-expanded");
          btn.setAttribute("aria-expanded", "false");
          const detailRow = tableRoot.querySelector(
            `[data-sla-detail-row][data-shop-id="${CSS.escape(shopId)}"]`
          );
          detailRow?.classList.remove("is-open");
          detailRow?.setAttribute("aria-hidden", "true");
          detailRow?.querySelector(".si-sla-detail-panel")?.classList.remove("is-open");
          return;
        }

        expandedSet.add(shopId);
        row.classList.add("is-expanded");
        btn.setAttribute("aria-expanded", "true");
        if (!detailCache.has(shopId)) detailCache.set(shopId, defaultDetailState());
        const detailState = detailCache.get(shopId);
        loadDetailForShop(seller, detailState, tableRoot, true);
      });
    });

    tableRoot.addEventListener("click", (ev) => {
      const metricBtn = ev.target.closest("[data-sla-detail-metric]");
      if (metricBtn) {
        const shopId = metricBtn.closest("[data-sla-detail-row]")?.dataset?.shopId;
        if (!shopId || !detailCache.has(shopId)) return;
        const key = metricBtn.dataset.slaDetailMetric;
        const detailState = detailCache.get(shopId);
        if (detailState.selected.has(key)) detailState.selected.delete(key);
        else detailState.selected.add(key);
        const seller = sellerMap.get(shopId);
        if (seller) refreshDetailRowDOM(tableRoot, seller, detailState, true);
        return;
      }

      const presetBtn = ev.target.closest("[data-sla-detail-preset]");
      if (presetBtn) {
        const shopId = presetBtn.dataset.shopId;
        if (!shopId || !detailCache.has(shopId)) return;
        const seller = sellerMap.get(shopId);
        if (!seller) return;
        const detailState = detailCache.get(shopId);
        const presetId = presetBtn.dataset.slaDetailPreset;
        detailState.preset = presetId;
        if (presetId === "custom") {
          const wrap = presetBtn.closest("[data-sla-detail-range]");
          const startInput = wrap?.querySelector("[data-sla-detail-start]");
          const endInput = wrap?.querySelector("[data-sla-detail-end]");
          if (startInput?.value && endInput?.value) {
            detailState.startDate = startInput.value;
            detailState.endDate = endInput.value;
          }
        } else {
          const range = applyPreset(presetId);
          detailState.startDate = range.startDate;
          detailState.endDate = range.endDate;
        }
        loadDetailForShop(seller, detailState, tableRoot, true);
        return;
      }

      const retryBtn = ev.target.closest("[data-sla-detail-retry]");
      if (retryBtn) {
        const shopId = retryBtn.dataset.shopId;
        const seller = sellerMap.get(shopId);
        const detailState = detailCache.get(shopId);
        if (seller && detailState) {
          detailState.fetchedKey = null;
          loadDetailForShop(seller, detailState, tableRoot, true);
        }
      }
    });

    tableRoot.addEventListener("change", (ev) => {
      const input = ev.target.closest("[data-sla-detail-start], [data-sla-detail-end]");
      if (!input) return;
      const wrap = input.closest("[data-sla-detail-range]");
      const shopId = wrap?.dataset?.shopId;
      if (!shopId || !detailCache.has(shopId)) return;
      const seller = sellerMap.get(shopId);
      if (!seller) return;
      const detailState = detailCache.get(shopId);
      const startInput = wrap.querySelector("[data-sla-detail-start]");
      const endInput = wrap.querySelector("[data-sla-detail-end]");
      if (!startInput?.value || !endInput?.value) return;
      if (startInput.value > endInput.value) return;
      detailState.preset = "custom";
      detailState.startDate = startInput.value;
      detailState.endDate = endInput.value;
      loadDetailForShop(seller, detailState, tableRoot, true);
    });
  }

  function bindTable(tableRoot, sellers, expandedSet, detailCache) {
    if (!tableRoot) return;
    const sellerMap = getSellerMap(sellers);
    bindDetailPanelEvents(tableRoot, sellerMap, expandedSet, detailCache);
    sellers.forEach((seller) => {
      const shopId = String(seller.shop_id);
      if (!expandedSet.has(shopId)) return;
      if (!detailCache.has(shopId)) detailCache.set(shopId, defaultDetailState());
      const detailState = detailCache.get(shopId);
      const mainRow = tableRoot.querySelector(
        `.si-sla-row[data-shop-id="${CSS.escape(shopId)}"]`
      );
      mainRow?.classList.add("is-expanded");
      mainRow?.querySelector("[data-sla-row-toggle]")?.setAttribute("aria-expanded", "true");
      if (!detailState.data && !detailState.loading && !detailState.error) {
        loadDetailForShop(seller, detailState, tableRoot, true);
      } else {
        refreshDetailRowDOM(tableRoot, seller, detailState, true);
      }
    });
  }

  window.SlaShopDetail = {
    COL_COUNT,
    hasTikTokData,
    renderChevron,
    DateRangeSelector,
    ShopDetailMetricsCards,
    ShopDetailExpandableRow,
    bindTable,
    defaultDetailState,
  };
})();
