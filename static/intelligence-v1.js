/**
 * Seller Intelligence V1 — command center UI (business + assortment).
 */
(function () {
  const API = {
    dashboard: "/api/intelligence/v1/dashboard",
    business: "/api/intelligence/v1/business",
    businessRefreshData: "/api/intelligence/v1/business/refresh-data",
    businessRefreshStatus: "/api/intelligence/v1/business/refresh-status",
    assortment: "/api/intelligence/v1/assortment",
    assortmentRefreshProducts: "/api/intelligence/v1/assortment/refresh-products",
    voucher: "/api/intelligence/v1/voucher",
  };

  const SLA_POLL_INTERVAL_MS = 1500;
  const SLA_POLL_MAX_MS = 3600000;

  const RADAR_LOAD_TIMEOUT_MS = 45000;
  const RADAR_POLL_INTERVAL_MS = 8000;
  const RADAR_POLL_MAX_MS = 900000;

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
      shopDetail: new Map(),
      shellReady: false,
      page: 1,
      pageSize: 20,
    },
    assortment: {
      raw: null,
      filters: defaultAssortmentFilters(),
      expanded: new Set(),
      shellReady: false,
    },
  };

  function defaultBusinessFilters() {
    return { q: "", rm: "all", gp: "all", status: "all", risk: "all", sort: "shop_name" };
  }

  function businessSheetFilters(data) {
    return {
      rm: data?.rm_filter || data?.sheet_filters?.rm_filter || { options: [{ value: "all", label: "All RM" }], by_rm: {} },
      gp: data?.gp_filter || data?.sheet_filters?.gp_filter || {
        options: [{ value: "all", label: "All GP" }],
        by_gp: {},
        gp_names_by_rm: {},
      },
    };
  }

  function businessGpFilterForRm(gpFilter, rmValue) {
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

  function coerceBusinessGpForRm(filters, sheetFilters) {
    const rm = filters.rm || "all";
    const gp = filters.gp || "all";
    if (rm === "all" || gp === "all") return filters;
    const allowed = sheetFilters.gp?.gp_names_by_rm?.[rm] || [];
    if (!allowed.includes(gp)) {
      return { ...filters, gp: "all" };
    }
    return filters;
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
    const keys = [normalizeShopKey(s.shop_name), normalizeShopKey(s.tiktok_shop_name)].filter(
      Boolean
    );
    return keys.some((k) => set.has(k));
  }

  function matchesGpFilter(s, gpValue, gpFilter) {
    if (!gpValue || gpValue === "all") return true;
    const gpNeedle = normalizeShopKey(gpValue);
    if (gpNeedle && normalizeShopKey(s.gp_shop_name) === gpNeedle) return true;
    const allowed = gpFilter?.by_gp?.[gpValue];
    if (!allowed || !allowed.length) return false;
    const set = new Set(allowed);
    const keys = [normalizeShopKey(s.shop_name), normalizeShopKey(s.tiktok_shop_name)].filter(
      Boolean
    );
    return keys.some((k) => set.has(k));
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

  function defaultAssortmentFilters() {
    return {
      q: "",
      rm: "all",
      gp: "all",
      shop: "all",
      productType: "top",
      dateRange: "all",
    };
  }

  function radarSheetFilters(data) {
    return businessSheetFilters(data);
  }

  function radarShopFilterRecord(shop) {
    return {
      shop_name: shop?.shop_name || "",
      tiktok_shop_name: shop?.tiktok_shop_name || "",
    };
  }

  function radarFilteredShops(shops, f, sheetFilters) {
    const sf = sheetFilters || {};
    return (shops || []).filter((shop) => {
      const rec = radarShopFilterRecord(shop);
      if (!matchesRmFilter(rec, f.rm, sf.rm)) return false;
      if (!matchesGpFilter(rec, f.gp, sf.gp)) return false;
      return true;
    });
  }

  function coerceRadarFilters(filters, data) {
    const sheetFilters = radarSheetFilters(data || {});
    let f = coerceBusinessGpForRm({ ...filters }, sheetFilters);
    const shops = radarFilteredShops(data?.filters?.shops || [], f, sheetFilters);
    const allowed = new Set(shops.map((s) => String(s.shop_id)));
    if (f.shop !== "all" && !allowed.has(String(f.shop))) {
      f = { ...f, shop: "all" };
    }
    return f;
  }

  function assortmentFiltersActive(f) {
    const d = defaultAssortmentFilters();
    return (
      Boolean((f.q || "").trim()) ||
      f.rm !== d.rm ||
      f.gp !== d.gp ||
      f.shop !== d.shop ||
      f.productType !== d.productType ||
      f.dateRange !== d.dateRange
    );
  }

  function radarEmptyMessage(raw, { filteredEmpty = false } = {}) {
    if (filteredEmpty) {
      return i18n(
        "si.radarEmptyFiltered",
        "No matching records after filters."
      );
    }
    const v = raw?.validation || {};
    if (v.data_status === "refreshing" || v.refresh_running) {
      return escapeHtml(v.message || "Product catalog refresh in progress…");
    }
    if (v.data_status === "pending_catalog") {
      return escapeHtml(
        v.message ||
          "No FastMoss product data yet. Click Update Data to refresh the TikTok product catalog."
      );
    }
    if ((v.approved_shop_count || 0) === 0) {
      return escapeHtml(
        "No mapped shop. Approve FastMoss mappings in Mapping Center, then click Update Data."
      );
    }
    if (v.data_status === "mapping_error") {
      return escapeHtml(v.message || "Column mapping error. Check headers.");
    }
    if (v.data_status === "source_error") {
      return escapeHtml(v.message || "Sheet source loaded but no rows found. Check tab/range.");
    }
    return i18n("si.radarEmptyCatalog", "No shop catalog data available.");
  }

  function logRadarDebug(data, label = "load") {
    const v = data?.validation || {};
    const portfolio = data?.portfolio || {};
    const shops = data?.filters?.shops || [];
    const categories = data?.category_dashboard?.categories || [];
    const shopView = data?.shop_view?.shops || [];
    console.log(`[TikTok Product Radar] ${label}`);
    console.log("Radar raw rows:", v.raw_record_count ?? v.sheet_row_count ?? 0);
    console.log("Radar mapped products:", v.mapped_product_count ?? portfolio.total_products ?? 0);
    console.log("Radar shops:", v.shop_count ?? shops.length ?? shopView.length);
    console.log("Radar categories:", v.category_count ?? categories.length);
    console.log("Radar data_status:", v.data_status);
    if (v.message) console.log("Radar message:", v.message);
  }

  async function loadWithTimeout(path, options = {}, timeoutMs = RADAR_LOAD_TIMEOUT_MS) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetchApi(path, { ...options, signal: controller.signal });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Request failed (${res.status})`);
      }
      return res.json();
    } catch (err) {
      if (err.name === "AbortError") {
        throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function pollRadarUntilReady() {
    const deadline = Date.now() + RADAR_POLL_MAX_MS;
    while (Date.now() < deadline) {
      const data = await loadWithTimeout(API.assortment, {}, RADAR_LOAD_TIMEOUT_MS);
      logRadarDebug(data, "poll");
      const v = data?.validation || {};
      const refresh = data?.refresh_status || {};
      if (!refresh.running && !v.refresh_running) {
        if ((v.mapped_product_count || 0) > 0 || v.data_status !== "refreshing") {
          return data;
        }
      }
      await sleep(RADAR_POLL_INTERVAL_MS);
    }
    throw new Error("Product catalog refresh timed out. Try Update Data again.");
  }

  async function startRadarProductRefresh() {
    const res = await fetchApi(API.assortmentRefreshProducts, { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Refresh failed (${res.status})`);
    }
    return res.json();
  }

  function fetchApi(path, options = {}) {
    const fn = window.SipApi?.fetch || fetch;
    return fn(path, { credentials: "same-origin", ...options });
  }

  function i18n(key, fallback = "") {
    return window.SipI18n?.t?.(key, fallback) ?? fallback ?? key;
  }

  const slaRefreshUi = {
    panel: document.getElementById("siBusinessRefreshProgress"),
    headerLastUpdated: document.getElementById("siBusinessLastUpdated"),
    stepLabel: document.getElementById("siBusinessRefreshStepLabel"),
    percent: document.getElementById("siBusinessRefreshPercent"),
    barFill: document.getElementById("siBusinessRefreshBarFill"),
    stats: document.getElementById("siBusinessRefreshStats"),
    time: document.getElementById("siBusinessRefreshTime"),
    error: document.getElementById("siBusinessRefreshError"),
    details: document.querySelector("[data-sla-refresh-details]"),
    collapsedSummary: document.querySelector("[data-sla-refresh-collapsed-summary]"),
    toggleBtn: document.querySelector("[data-sla-refresh-toggle]"),
  };

  const slaRefreshState = {
    collapsed: false,
    lastComplete: null,
  };

  function formatElapsedSeconds(sec) {
    const n = Math.max(0, Math.floor(Number(sec) || 0));
    const m = Math.floor(n / 60);
    const s = n % 60;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function formatSlaCompletionSummary(result) {
    const mapping = result?.mapping || {};
    const summary = mapping.summary || {};
    const mapped = summary.mapped ?? "—";
    const pending = summary.need_review ?? mapping.pending_review_count ?? "—";
    const notFound = summary.not_found ?? mapping.still_not_found_count ?? "—";
    const newly = mapping.newly_mapped_count ?? 0;
    const at = result?.refreshed_at || "—";
    return (
      `FastMoss mapped: ${mapped} · Pending review: ${pending} · ` +
      `Not found: ${notFound} · Newly mapped: ${newly} · Updated at: ${at}`
    );
  }

  function setSlaProgressVisible(visible) {
    slaRefreshUi.panel?.classList.toggle("hidden", !visible);
  }

  function formatSlaLastUpdatedHeader(iso) {
    if (!iso || iso === "—") return "";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return String(iso);
      const y = d.getFullYear();
      const m = d.getMonth() + 1;
      const day = d.getDate();
      const h = String(d.getHours()).padStart(2, "0");
      const min = String(d.getMinutes()).padStart(2, "0");
      const s = String(d.getSeconds()).padStart(2, "0");
      return `${y}/${m}/${day} ${h}:${min}:${s}`;
    } catch {
      return String(iso);
    }
  }

  function slaRefreshMappingCounts(result, status) {
    const mapping = result?.mapping || {};
    const summary = mapping.summary || status || {};
    return {
      mapped: summary.mapped ?? summary.total ?? 0,
      pending: summary.need_review ?? mapping.pending_review_count ?? status?.pending_review_count ?? 0,
      notFound: summary.not_found ?? mapping.still_not_found_count ?? status?.still_not_found_count ?? 0,
      newlyMapped: mapping.newly_mapped_count ?? status?.newly_mapped_count ?? 0,
      refreshedAt: result?.refreshed_at || status?.refreshed_at || status?.finished_at || "—",
    };
  }

  function setSharedSlaLastUpdatedHeader(iso, targetEl) {
    const el = targetEl || slaRefreshUi.headerLastUpdated;
    if (!el) return;
    const formatted = formatSlaLastUpdatedHeader(iso);
    if (!formatted) {
      el.textContent = "";
      return;
    }
    const prefix = i18n("si.lastUpdated", "Last updated:");
    el.textContent = `${prefix} ${formatted}`;
  }

  function applySharedSlaUpdateState(slaState, { headerEl } = {}) {
    if (!slaState?.completed) return;
    const iso = slaState.refreshed_at || slaState.finished_at;
    setSharedSlaLastUpdatedHeader(iso, headerEl || slaRefreshUi.headerLastUpdated);
  }

  function renderSlaRefreshCollapsedSummary() {
    const el = slaRefreshUi.collapsedSummary;
    const lc = slaRefreshState.lastComplete;
    if (!el || !lc) return;
    const counts = slaRefreshMappingCounts(lc.result, lc.status);
    const pct = Math.min(100, Math.max(0, Number(lc.status?.percent) || 100));
    const lastLabel = formatSlaLastUpdatedHeader(counts.refreshedAt) || counts.refreshedAt;
    el.textContent =
      `${i18n("si.lastUpdated", "Last updated:")} ${lastLabel} · ` +
      `${i18n("si.refreshCompletedPct", "Completed")} ${pct.toFixed(0)}% · ` +
      `FastMoss mapped: ${counts.mapped} · ` +
      `Pending review: ${counts.pending} · ` +
      `Not found: ${counts.notFound} · ` +
      `Newly mapped: ${counts.newlyMapped}`;
  }

  function slaStatusFromPersisted(ps) {
    const status = ps?.status || {};
    const summary = ps?.mapping_summary || {};
    return {
      step_label: status.step_label || i18n("si.refreshComplete", "Completed"),
      percent: ps?.percent ?? status.percent ?? 100,
      shops_processed: ps?.shops_processed ?? status.shops_processed ?? summary.total ?? 0,
      shops_total: ps?.shops_total ?? status.shops_total ?? summary.total ?? 0,
      newly_mapped_count: ps?.newly_mapped_count ?? status.newly_mapped_count ?? 0,
      pending_review_count: ps?.pending_review_count ?? summary.need_review ?? 0,
      still_not_found_count: ps?.still_not_found_count ?? summary.not_found ?? 0,
      failed_count: ps?.failed_count ?? 0,
      preserved_mapped_count: ps?.preserved_mapped_count ?? 0,
      changed_tiktok_count: ps?.changed_tiktok_count ?? 0,
      refreshed_at: ps?.refreshed_at,
      finished_at: ps?.finished_at,
    };
  }

  function applyPersistedSlaUpdateState(data) {
    const ps = data?.sla_update_state;
    if (!ps?.completed) return;
    const result = ps.result || {};
    const status = slaStatusFromPersisted(ps);
    markSlaRefreshComplete(result, status);
    setSlaProgressVisible(true);
    renderSlaProgress(status);
    setSlaRefreshCollapseAvailable(true);
    setSlaRefreshCollapsed(true);
    applySharedSlaUpdateState(ps);
    const summaryEl = document.getElementById("siBusinessActionSummary");
    if (summaryEl) summaryEl.classList.add("hidden");
  }

  function setSlaRefreshCollapsed(collapsed) {
    slaRefreshState.collapsed = collapsed;
    const panel = slaRefreshUi.panel;
    if (!panel) return;
    panel.classList.toggle("is-collapsed", collapsed);
    slaRefreshUi.details?.classList.toggle("hidden", collapsed);
    slaRefreshUi.collapsedSummary?.classList.toggle("hidden", !collapsed);
    const btn = slaRefreshUi.toggleBtn;
    if (btn) {
      btn.textContent = collapsed
        ? i18n("si.refreshExpandDetails", "Expand details")
        : i18n("si.refreshCollapse", "Collapse");
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }
    if (collapsed) renderSlaRefreshCollapsedSummary();
  }

  function setSlaRefreshCollapseAvailable(available) {
    slaRefreshUi.panel?.classList.toggle("has-update-toolbar", !!available);
    slaRefreshUi.toggleBtn?.classList.toggle("hidden", !available);
  }

  function resetSlaRefreshPanelForRun() {
    slaRefreshState.lastComplete = null;
    setSlaRefreshCollapsed(false);
    setSlaRefreshCollapseAvailable(false);
    slaRefreshUi.collapsedSummary?.classList.add("hidden");
    slaRefreshUi.panel?.classList.remove("has-update-toolbar");
  }

  function markSlaRefreshComplete(result, status) {
    slaRefreshState.lastComplete = { result, status };
    setSlaRefreshCollapseAvailable(true);
  }

  function renderSlaProgress(status) {
    if (!slaRefreshUi.panel) return;
    const pct = Math.min(100, Math.max(0, Number(status.percent) || 0));
    if (slaRefreshUi.stepLabel) {
      slaRefreshUi.stepLabel.textContent = status.step_label || "—";
    }
    if (slaRefreshUi.percent) {
      slaRefreshUi.percent.textContent = `${pct.toFixed(0)}%`;
    }
    if (slaRefreshUi.barFill) {
      slaRefreshUi.barFill.style.width = `${pct}%`;
    }
    const lines = [
      `Shops processed: ${status.shops_processed ?? 0} / ${status.shops_total ?? 0}`,
      `Newly mapped: ${status.newly_mapped_count ?? 0}`,
      `Pending review: ${status.pending_review_count ?? 0}`,
      `Still not found: ${status.still_not_found_count ?? 0}`,
      `Failed: ${status.failed_count ?? 0}`,
    ];
    if (status.changed_tiktok_count != null) {
      lines.push(`TikTok names changed: ${status.changed_tiktok_count}`);
    }
    if (status.preserved_mapped_count != null) {
      lines.push(`MAPPED preserved: ${status.preserved_mapped_count}`);
    }
    if (slaRefreshUi.stats) {
      slaRefreshUi.stats.innerHTML = lines.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
    }
    if (slaRefreshUi.time) {
      const elapsed = formatElapsedSeconds(status.elapsed_sec);
      const est =
        pct > 2 && pct < 100
          ? formatElapsedSeconds((Number(status.elapsed_sec) || 0) * (100 / pct - 1))
          : "—";
      slaRefreshUi.time.textContent = `Elapsed: ${elapsed} · Est. remaining: ${est}`;
    }
    slaRefreshUi.error?.classList.add("hidden");
  }

  function showSlaProgressError(status) {
    if (!slaRefreshUi.error) return;
    const step = status.failed_step_label || status.step_label || "Update Data";
    const msg = status.error || "Refresh failed";
    slaRefreshUi.error.textContent = `${step}: ${msg}`;
    slaRefreshUi.error.classList.remove("hidden");
    if (slaRefreshUi.stepLabel) {
      slaRefreshUi.stepLabel.textContent = i18n("si.refreshFailedStep", "Update failed");
    }
  }

  async function pollSlaRefreshUntilDone() {
    const deadline = Date.now() + SLA_POLL_MAX_MS;
    while (Date.now() < deadline) {
      const res = await fetchApi(API.businessRefreshStatus);
      const status = await res.json();
      if (!res.ok) throw new Error(status.detail || "Could not read refresh status");
      renderSlaProgress(status);
      if (!status.running) {
        if (status.error) {
          showSlaProgressError(status);
          throw new Error(status.error);
        }
        return status.result || {};
      }
      await sleep(SLA_POLL_INTERVAL_MS);
    }
    throw new Error(i18n("si.refreshTimeout", "Update timed out. Try again."));
  }

  function formatMappingSummary(data) {
    const mapping = data.mapping || data;
    const review = data.review || {};
    const bi = data.tiktok_bi || {};
    const mapSummary = mapping.summary || {};
    const template = i18n(
      "si.refreshSummary",
      "Approved: {approved} · Pending: {pending} · Rejected: {rejected} · TikTok refreshed: {tiktok}"
    );
    let text = template
      .replace("{approved}", String(review.APPROVED ?? 0))
      .replace("{pending}", String(review.PENDING_REVIEW ?? 0))
      .replace("{rejected}", String(review.REJECTED ?? 0))
      .replace("{tiktok}", String(bi.tiktok_data_refreshed_count ?? mapping.tiktok_data_refreshed_count ?? 0));
    if (mapSummary.mapped != null) {
      text += ` · FastMoss mapped: ${mapSummary.mapped}`;
      if (mapSummary.not_found != null) {
        text += ` · Not found: ${mapSummary.not_found}`;
      }
      if (mapping.newly_mapped_count > 0) {
        text += ` · Newly mapped: ${mapping.newly_mapped_count}`;
      }
    }
    return text;
  }

  function mappingReviewBadge(seller) {
    const source = String(seller.platform_source || "NORMAL").toUpperCase();
    if (source === "SHOPEE_ONLY" || source === "TIKTOK_ONLY") {
      return platformSourceBadge(seller);
    }
    const review = String(seller.fastmoss_review_status || "").toUpperCase();
    if (review === "APPROVED") {
      return platformSourceBadge(seller);
    }
    const map = {
      PENDING_REVIEW: ["si-v1-badge--warn", "Pending review"],
      REJECTED: ["si-v1-badge--risk", "Rejected"],
    };
    if (map[review]) {
      const [cls, label] = map[review];
      return `<span class="si-v1-badge ${cls}">${escapeHtml(label)}</span>`;
    }
    return platformSourceBadge(seller);
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

  function fmtMomPct(n) {
    if (n == null || Number.isNaN(n)) return null;
    const sign = n > 0 ? "+" : "";
    return `${sign}${fmtNum(n, 1)}%`;
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

  function platformSourceBadge(s) {
    const source = String(s.platform_source || "NORMAL").toUpperCase();
    if (source === "SHOPEE_ONLY") {
      return `<span class="si-v1-badge si-v1-badge--shopee">Shopee only</span>`;
    }
    if (source === "TIKTOK_ONLY") {
      return `<span class="si-v1-badge si-v1-badge--tiktok">TikTok only</span>`;
    }
    return fastmossStatusBadge(s.fastmoss_match_status);
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

  function renderBusinessPeriodChips(periods) {
    if (!periods?.mtd || !periods?.m1) return "";
    return `
      <span class="si-sla-chip">MTD ${escapeHtml(periods.mtd.start)} → ${escapeHtml(periods.mtd.end)}</span>
      <span class="si-sla-chip">M-1 ${escapeHtml(periods.m1.start)} → ${escapeHtml(periods.m1.end)}</span>`;
  }

  function renderSlaSobLegendBar(shpPct, tkPct, { barClass = "hs-inline-sob-bar" } = {}) {
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
        <div class="si-sob-stack-bar ${barClass}" data-sob-animate="1" data-shp="${shp}" data-tk="${tk}">
          <div class="si-sob-stack-seg si-sob-stack-seg--shp" style="width:0%" aria-hidden="true"></div>
          <div class="si-sob-stack-seg si-sob-stack-seg--tk" style="width:0%" aria-hidden="true"></div>
        </div>`;
  }

  function renderBusinessInlineSobCell(shpPct, tkPct) {
    const shp = clampSobPct(shpPct);
    const tk = clampSobPct(tkPct);
    if (shp == null || tk == null) {
      return `<td class="si-sla-sob-cell">${fmtNa("SOB NA")}</td>`;
    }
    return `
      <td class="si-sla-sob-cell">
        <div class="hs-inline-sob">
          ${renderSlaSobLegendBar(shp, tk)}
        </div>
      </td>`;
  }

  /**
   * MTD ADGMV for summary totals. NA / missing platform GMV => 0 (not excluded from scope).
   */
  function slaMtdGmvUsd(s, platform) {
    const field = platform === "shp" ? "shopee_mtd_adgmv_usd" : "tiktok_mtd_adgmv_usd";
    const v = s[field];
    if (v == null || v === "" || (typeof v === "number" && Number.isNaN(v))) return 0;
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : 0;
  }

  /**
   * Summary SOB from summed MTD GMV in the current scope — never averages row SOB %.
   *
   * Shopee SOB = sum(Shopee MTD) / (sum(Shopee MTD) + sum(TikTok MTD))
   * TikTok SOB = sum(TikTok MTD) / (sum(Shopee MTD) + sum(TikTok MTD))
   */
  function computeSlaSummarySob(sellers) {
    let shopeeGmvUsd = 0;
    let tiktokGmvUsd = 0;
    for (const s of sellers || []) {
      shopeeGmvUsd += slaMtdGmvUsd(s, "shp");
      tiktokGmvUsd += slaMtdGmvUsd(s, "tk");
    }
    const totalGmv = shopeeGmvUsd + tiktokGmvUsd;
    if (totalGmv <= 0) return { kind: "na", shopCount: (sellers || []).length };
    return {
      kind: "values",
      shpPct: (shopeeGmvUsd / totalGmv) * 100,
      tkPct: (tiktokGmvUsd / totalGmv) * 100,
      shopeeGmvUsd,
      tiktokGmvUsd,
      shopCount: (sellers || []).length,
    };
  }

  function slaFilteredScopeLabel(filtered, filters) {
    const n = filtered.length;
    const bits = [`${n} shop${n === 1 ? "" : "s"}`];
    if (filters.gp && filters.gp !== "all") bits.push(`GP: ${filters.gp}`);
    if (filters.rm && filters.rm !== "all") bits.push(`RM: ${filters.rm}`);
    if (filters.q?.trim()) bits.push("search");
    if (filters.status && filters.status !== "all") bits.push(filters.status);
    if (filters.risk && filters.risk !== "all") bits.push(filters.risk);
    return bits.join(" · ");
  }

  function businessCategoryMapping(data) {
    return (
      data?.category_mapping || {
        categories: [],
        loaded: false,
      }
    );
  }

  function sellersForCategoryKeys(sellers, shopKeys) {
    const set = new Set(shopKeys || []);
    if (!set.size) return [];
    return (sellers || []).filter((s) => {
      const keys = [normalizeShopKey(s.shop_name), normalizeShopKey(s.tiktok_shop_name)].filter(
        Boolean
      );
      return keys.some((k) => set.has(k));
    });
  }

  function renderSlaCategorySobCard(categoryName, matchedCount, sob) {
    const head = `<h4 class="si-sla-summary-card__title">${escapeHtml(categoryName)}</h4>`;
    const countLine = `<p class="si-sla-summary-card__count">${fmtNum(matchedCount)} shops matched</p>`;
    if (sob?.kind === "na") {
      return `<article class="si-sla-summary-card si-sla-summary-card--category">${head}${countLine}<p class="si-sla-summary-card__na">${fmtNa("SOB N/A")}</p></article>`;
    }
    if (sob?.kind !== "values") {
      return `<article class="si-sla-summary-card si-sla-summary-card--category">${head}${countLine}<p class="si-sla-summary-card__na">${fmtNa("SOB N/A")}</p></article>`;
    }
    return `<article class="si-sla-summary-card si-sla-summary-card--category">
        ${head}${countLine}
        <div class="hs-inline-sob si-sla-summary-card__sob">
          ${renderSlaSobLegendBar(sob.shpPct, sob.tkPct, { barClass: "hs-inline-sob-bar si-sla-summary-sob-bar" })}
        </div>
      </article>`;
  }

  function renderSlaSummarySobCard(title, { prompt, selection, sob }) {
    const head = `<h3 class="si-sla-summary-card__title">${escapeHtml(title)}</h3>`;
    if (prompt) {
      return `<article class="si-sla-summary-card">${head}<p class="si-sla-summary-card__prompt">${escapeHtml(prompt)}</p></article>`;
    }
    const sel = selection
      ? `<p class="si-sla-summary-card__sel">${escapeHtml(selection)}</p>`
      : "";
    if (sob?.kind === "na") {
      return `<article class="si-sla-summary-card">${head}${sel}<p class="si-sla-summary-card__na">${fmtNa("SOB N/A")}</p></article>`;
    }
    if (sob?.kind !== "values") {
      return `<article class="si-sla-summary-card">${head}${sel}<p class="si-sla-summary-card__na">${fmtNa("SOB N/A")}</p></article>`;
    }
    return `<article class="si-sla-summary-card">
        ${head}${sel}
        <div class="hs-inline-sob si-sla-summary-card__sob">
          ${renderSlaSobLegendBar(sob.shpPct, sob.tkPct, { barClass: "hs-inline-sob-bar si-sla-summary-sob-bar" })}
        </div>
      </article>`;
  }

  function paintBusinessSummarySob() {
    const el = containers.siBusiness;
    const st = state.business;
    const summaryEl = el?.querySelector("[data-sla-summary-sob]");
    if (!summaryEl || !st.raw) return;

    const sheetFilters = businessSheetFilters(st.raw);
    const sellers = st.raw.sellers || [];
    const f = st.filters;
    const filtered = filterBusinessSellers(sellers, f, sheetFilters);
    const filteredIds = new Set(filtered.map((s) => String(s.shop_id)));
    const scopeSob = computeSlaSummarySob(filtered);
    const scopeLabel = slaFilteredScopeLabel(filtered, f);

    const overallCard = renderSlaSummarySobCard("Overall SOB", {
      selection: scopeLabel,
      sob: scopeSob,
    });

    let gpCard;
    if (!f.gp || f.gp === "all") {
      gpCard = renderSlaSummarySobCard("GP SOB", {
        prompt: "Select GP to view GP SOB",
      });
    } else {
      gpCard = renderSlaSummarySobCard("GP SOB", {
        selection: `${f.gp} · ${scopeLabel}`,
        sob: scopeSob,
      });
    }

    let rmCard;
    if (!f.rm || f.rm === "all") {
      rmCard = renderSlaSummarySobCard("RM SOB", {
        prompt: "Select RM to view RM SOB",
      });
    } else {
      rmCard = renderSlaSummarySobCard("RM SOB", {
        selection: `${f.rm} · ${scopeLabel}`,
        sob: scopeSob,
      });
    }

    const categoryMapping = businessCategoryMapping(st.raw);
    const categories = categoryMapping.categories || [];
    let categorySection = "";
    if (!categories.length) {
      categorySection = `<section class="si-sla-category-sob" data-sla-category-sob>
        <h3 class="si-sla-category-sob__heading">Category SOB</h3>
        <p class="si-sla-category-sob__empty">Category mapping not loaded from sheet.</p>
      </section>`;
    } else {
      const categoryCards = categories
        .map((cat) => {
          const matched = sellersForCategoryKeys(sellers, cat.shop_keys).filter((s) =>
            filteredIds.has(String(s.shop_id))
          );
          return renderSlaCategorySobCard(
            cat.name,
            matched.length,
            computeSlaSummarySob(matched)
          );
        })
        .join("");
      categorySection = `<section class="si-sla-category-sob" data-sla-category-sob>
        <h3 class="si-sla-category-sob__heading">Category SOB</h3>
        <div class="si-sla-category-grid">${categoryCards}</div>
      </section>`;
    }

    summaryEl.innerHTML = `${categorySection}<div class="si-sla-summary-grid">${overallCard}${gpCard}${rmCard}</div>`;
    animateSobBars(summaryEl);
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
      s.gp_shop_id,
      s.gp_shop_name,
      s.rm,
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

  function filterBusinessSellers(sellers, f, sheetFilters) {
    const sf = sheetFilters || {};
    let list = sellers.filter((s) => {
      if (!matchesQuery(s, f.q)) return false;
      if (!matchesRmFilter(s, f.rm, sf.rm)) return false;
      if (!matchesGpFilter(s, f.gp, sf.gp)) return false;
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
        case "shopee_mom_asc":
          return cmp(a.shopee_mom_percent ?? -999, b.shopee_mom_percent ?? -999);
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

  function productSearchBlob(p) {
    return [
      p.product_name,
      p.category,
      p.shop_name,
      p.tiktok_shop_name,
      p.seller_shop_id,
      p.product_id,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function filterRadarProducts(products, f) {
    return (products || []).filter((p) => {
      if (f.q && !productSearchBlob(p).includes(f.q.trim().toLowerCase())) return false;
      if (f.dateRange !== "all") {
        const days = p.days_since_launch;
        if (days == null) return false;
        if (days > Number(f.dateRange)) return false;
      }
      return true;
    });
  }

  function resolveDefaultShopId(data) {
    const shops = data?.filters?.shops || data?.shop_view?.shops || [];
    return shops[0]?.shop_id || "all";
  }

  function emptyRadarShop(shopId, shopName) {
    return {
      shop_id: shopId,
      shop_name: shopName,
      summary: {
        total_products: 0,
        new_products_20d: 0,
        growth_products: 0,
        opportunity_products: 0,
      },
      top_products: [],
      new_products: [],
      growth_products: [],
      opportunity_products: [],
    };
  }

  function resolveRadarShop(raw, shopId) {
    const shops = raw?.shop_view?.shops || [];
    const found = shops.find((s) => String(s.shop_id) === String(shopId));
    if (found) return found;
    const opt = (raw?.filters?.shops || []).find((s) => String(s.shop_id) === String(shopId));
    return opt ? emptyRadarShop(opt.shop_id, opt.shop_name) : null;
  }

  function resolveDefaultCategory(data) {
    const categories = data?.category_dashboard?.categories || [];
    return categories[0]?.category || "all";
  }

  function filterAssortmentSellers(sellers, f, sheetFilters) {
    const sf = sheetFilters || {};
    return (sellers || []).filter((s) => {
      if (!matchesRmFilter(s, f.rm, sf.rm)) return false;
      if (!matchesGpFilter(s, f.gp, sf.gp)) return false;
      return true;
    });
  }

  /* ---------- UI components ---------- */

  function renderMom(pct, label, naText = "N/A") {
    if (pct == null || Number.isNaN(pct)) {
      return `<span class="si-mom si-mom--na" title="${escapeHtml(label)}">${escapeHtml(naText)}</span>`;
    }
    const up = pct > 0.05;
    const down = pct < -0.05;
    const cls = up ? "si-mom--up" : down ? "si-mom--down" : "si-mom--flat";
    const arrow = up ? "▲" : down ? "▼" : "●";
    return `<span class="si-mom ${cls}" title="${escapeHtml(label)}"><span class="si-mom-arrow">${arrow}</span>${fmtMomPct(pct)}</span>`;
  }

  function renderBusinessMomBadges(s) {
    const shReason = s.shopee_na_reason || "Shopee ADGMV not found in Tracker";
    const tkReason = s.tiktok_na_reason || "TikTok data unavailable";
    const shMom =
      s.shopee_data_status === "available"
        ? renderMom(s.shopee_mom_percent, "Shopee MoM")
        : fmtNa(shReason);
    const tkMom =
      s.tiktok_data_status === "available"
        ? renderMom(s.tiktok_mom_percent, "TikTok MoM")
        : fmtNa(tkReason);
    return `
      <div class="si-biz-mom-badges">
        <article class="si-biz-mom-badge">
          <span class="si-biz-mom-badge-label">Shopee MoM</span>
          <span class="si-biz-mom-badge-value">${shMom}</span>
        </article>
        <article class="si-biz-mom-badge">
          <span class="si-biz-mom-badge-label">TikTok MoM</span>
          <span class="si-biz-mom-badge-value">${tkMom}</span>
        </article>
      </div>`;
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
          <div class="si-biz-sob-card-body">
            ${renderBusinessMomBadges(s)}
            ${fmtNa(sobReason)}
          </div>
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
          ${renderBusinessMomBadges(s)}
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

  function businessToolbarFieldsHtml(f, sheetFilters) {
    const sf = sheetFilters || {};
    const gpFilterDef = businessGpFilterForRm(sf.gp, f.rm);
    return `
          <div class="si-v1-toolbar-field si-v1-toolbar-field--search">
            <label for="siBizSearch">Seller search</label>
            <input id="siBizSearch" type="search" placeholder="Shop ID, name, Shopee link, TikTok shop…" value="${escapeHtml(f.q)}" data-f="q" />
          </div>
          <div class="si-v1-toolbar-field">
            <label for="siBizRm">RM</label>
            <select id="siBizRm" data-f="rm">${filterSelectOptionsHtml(sf.rm, f.rm, "All RM")}</select>
          </div>
          <div class="si-v1-toolbar-field">
            <label for="siBizGp">GP</label>
            <select id="siBizGp" data-f="gp">${filterSelectOptionsHtml(gpFilterDef, f.gp, "All GP")}</select>
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
              <option value="shopee_mom"${f.sort === "shopee_mom" ? " selected" : ""}>Shopee MoM % (high → low)</option>
              <option value="shopee_mom_asc"${f.sort === "shopee_mom_asc" ? " selected" : ""}>Shopee MoM % (low → high)</option>
              <option value="tiktok_mom"${f.sort === "tiktok_mom" ? " selected" : ""}>TikTok MoM</option>
              <option value="fastmoss"${f.sort === "fastmoss" ? " selected" : ""}>FastMoss status</option>
            </select>
          </div>
          <button type="button" class="si-sla-btn-reset" data-reset>Reset filters</button>`;
  }

  function businessFilterCardHtml(f, sheetFilters) {
    return `<div class="si-sla-filter-card" data-sla-filter-card>
        <div class="si-v1-toolbar si-sla-toolbar" data-toolbar="business">${businessToolbarFieldsHtml(f, sheetFilters)}</div>
        <p class="si-sla-result-count" data-result-count></p>
      </div>`;
  }

  function syncBusinessFilterControls(el) {
    const toolbar = el.querySelector("[data-toolbar='business']");
    if (!toolbar) return;
    const sheetFilters = businessSheetFilters(state.business.raw || {});
    state.business.filters = coerceBusinessGpForRm(state.business.filters, sheetFilters);
    const f = state.business.filters;
    const q = toolbar.querySelector("[data-f='q']");
    if (q) q.value = f.q || "";
    const map = { rm: "siBizRm", gp: "siBizGp", status: "siBizStatus", risk: "siBizRisk", sort: "siBizSort" };
    Object.entries(map).forEach(([key, id]) => {
      const node = toolbar.querySelector(`#${id}`);
      if (node) node.value = f[key] || "all";
    });
    const rmSel = toolbar.querySelector("#siBizRm");
    if (rmSel) rmSel.innerHTML = filterSelectOptionsHtml(sheetFilters.rm, f.rm, "All RM");
    const gpSel = toolbar.querySelector("#siBizGp");
    if (gpSel) {
      gpSel.innerHTML = filterSelectOptionsHtml(
        businessGpFilterForRm(sheetFilters.gp, f.rm),
        f.gp,
        "All GP"
      );
    }
  }

  function radarShopOptionsHtml(f, data) {
    const sheetFilters = radarSheetFilters(data);
    const shops = radarFilteredShops(data?.filters?.shops || [], f, sheetFilters);
    const opts = [
      `<option value="all"${f.shop === "all" ? " selected" : ""}>All shops</option>`,
      ...shops.map(
        (s) =>
          `<option value="${escapeHtml(s.shop_id)}"${String(f.shop) === String(s.shop_id) ? " selected" : ""}>${escapeHtml(s.shop_name)}</option>`
      ),
    ];
    return opts.join("");
  }

  function radarToolbarFieldsHtml(f, data) {
    const sheetFilters = radarSheetFilters(data);
    const gpFilterDef = businessGpFilterForRm(sheetFilters.gp, f.rm);
    return `
          <div class="si-v1-toolbar-field si-v1-toolbar-field--search">
            <label for="siRadarSearch">Product search</label>
            <input id="siRadarSearch" type="search" placeholder="Product name, category, shop…" value="${escapeHtml(f.q)}" data-f="q" />
          </div>
          <div class="si-v1-toolbar-field">
            <label for="siRadarRm">RM</label>
            <select id="siRadarRm" data-f="rm">${filterSelectOptionsHtml(sheetFilters.rm, f.rm, "All RM")}</select>
          </div>
          <div class="si-v1-toolbar-field">
            <label for="siRadarGp">GP</label>
            <select id="siRadarGp" data-f="gp">${filterSelectOptionsHtml(gpFilterDef, f.gp, "All GP")}</select>
          </div>
          <div class="si-v1-toolbar-field">
            <label for="siRadarShop">Shop</label>
            <select id="siRadarShop" data-f="shop">${radarShopOptionsHtml(f, data)}</select>
          </div>
          <div class="si-v1-toolbar-field">
            <label for="siRadarProductType">Category type</label>
            <select id="siRadarProductType" data-f="productType">
              <option value="all"${f.productType === "all" ? " selected" : ""}>All</option>
              <option value="top"${f.productType === "top" ? " selected" : ""}>Top 30</option>
              <option value="new"${f.productType === "new" ? " selected" : ""}>New 30 days</option>
              <option value="growth"${f.productType === "growth" ? " selected" : ""}>Growth products</option>
            </select>
          </div>
          <div class="si-v1-toolbar-field">
            <label for="siRadarDate">Upload window</label>
            <select id="siRadarDate" data-f="dateRange">
              <option value="all"${f.dateRange === "all" ? " selected" : ""}>All dates</option>
              <option value="30"${f.dateRange === "30" ? " selected" : ""}>Last 30 days</option>
              <option value="7"${f.dateRange === "7" ? " selected" : ""}>Last 7 days</option>
            </select>
          </div>
          <button type="button" class="si-sla-btn-reset" data-reset>Reset filters</button>`;
  }

  function radarFilterCardHtml(f, data) {
    return `<div class="si-sla-filter-card si-radar-filter-card" data-radar-filter-card>
        <div class="si-v1-toolbar si-sla-toolbar si-radar-toolbar" data-toolbar="radar">${radarToolbarFieldsHtml(f, data)}</div>
        <p class="si-sla-result-count" data-radar-result-count></p>
      </div>`;
  }

  function syncRadarFilterControls(el) {
    const toolbar = el.querySelector("[data-toolbar='radar']");
    if (!toolbar) return;
    const data = state.assortment.raw || {};
    const sheetFilters = radarSheetFilters(data);
    state.assortment.filters = coerceRadarFilters(state.assortment.filters, data);
    const f = state.assortment.filters;
    const q = toolbar.querySelector("[data-f='q']");
    if (q) q.value = f.q || "";
    const map = {
      rm: "siRadarRm",
      gp: "siRadarGp",
      shop: "siRadarShop",
      productType: "siRadarProductType",
      dateRange: "siRadarDate",
    };
    Object.entries(map).forEach(([key, id]) => {
      const node = toolbar.querySelector(`#${id}`);
      if (node) node.value = f[key] || (key === "shop" ? "all" : key === "productType" ? "top" : "all");
    });
    const rmSel = toolbar.querySelector("#siRadarRm");
    if (rmSel) rmSel.innerHTML = filterSelectOptionsHtml(sheetFilters.rm, f.rm, "All RM");
    const gpSel = toolbar.querySelector("#siRadarGp");
    if (gpSel) {
      gpSel.innerHTML = filterSelectOptionsHtml(
        businessGpFilterForRm(sheetFilters.gp, f.rm),
        f.gp,
        "All GP"
      );
    }
    const shopSel = toolbar.querySelector("#siRadarShop");
    if (shopSel) shopSel.innerHTML = radarShopOptionsHtml(f, data);
  }

  function radarSegmentHtml(productType) {
    const segments = [
      { id: "top", label: "Top 30 Products" },
      { id: "new", label: "New Products" },
      { id: "growth", label: "Growth Products" },
    ];
    return `<div class="si-radar-segments" data-radar-segments>
      ${segments
        .map(
          (s) =>
            `<button type="button" class="si-radar-segment${productType === s.id ? " is-active" : ""}" data-radar-segment="${s.id}">${escapeHtml(s.label)}</button>`
        )
        .join("")}
    </div>`;
  }

  function readFiltersFromToolbar(toolbar, defaults) {
    const f = { ...defaults };
    toolbar.querySelectorAll("[data-f]").forEach((node) => {
      f[node.dataset.f] = node.value;
    });
    return f;
  }

  /* ---------- Portfolio overview (Dashboard) ---------- */

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
    const p = data?.portfolio && typeof data.portfolio === "object" ? data.portfolio : {};
    const mapped = Number(p.mapped_sellers) || 0;
    const total = Number(p.total_sellers) || Number(data?.seller_count) || 0;
    const noApprovedBanner =
      total > 0 && mapped === 0
        ? `<div class="si-port-state si-port-state--info" role="status">
            <strong>No approved FastMoss mappings yet</strong>
            <p>Portfolio TikTok totals stay N/A until mappings are approved under Settings → Mapping Review.</p>
          </div>`
        : "";
    return `
      ${noApprovedBanner}
      <div class="si-port-overview">
        <div class="si-port-kpi-grid">
          ${renderPortfolioKpi("Total Sellers", fmtNum(total), `${fmtNum(mapped)} approved mapped`, "neutral")}
          ${renderPortfolioKpi("Mapping Rate", fmtPct(p.mapping_rate_percent), "Approved mapped / total", "accent")}
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
          <div class="si-detail-cell"><dt>FastMoss Match Status</dt><dd>${mappingReviewBadge(s)}</dd></div>
          <div class="si-detail-cell"><dt>TikTok raw MTD GMV PHP</dt><dd>${fmtDetailPhp(s.tiktok_mtd_gmv_php, tkReason)}</dd></div>
          <div class="si-detail-cell"><dt>TikTok raw M-1 GMV PHP</dt><dd>${fmtDetailPhp(s.tiktok_m1_gmv_php, tkReason)}</dd></div>
        </dl>
        ${renderBusinessSobAnalysis(s)}
      </div>`;
  }

  function renderBusinessTableRow(s, isOpen) {
    const tkReason = s.tiktok_na_reason || "TikTok data unavailable";
    const shReason = s.shopee_na_reason || "Shopee ADGMV not found in Tracker";
    const chevron = window.SlaShopDetail?.renderChevron(isOpen) || "";
    const tkMom =
      s.tiktok_data_status === "available"
        ? renderMom(s.tiktok_mom_percent, tkReason)
        : fmtNa(tkReason);
    const shMom =
      s.shopee_data_status === "available"
        ? renderMom(s.shopee_mom_percent, shReason)
        : fmtNa(shReason);
    const mtdSob = renderBusinessInlineSobCell(s.mtd_shopee_sob_percent, s.mtd_tiktok_sob_percent);
    const m1Sob = renderBusinessInlineSobCell(s.m1_shopee_sob_percent, s.m1_tiktok_sob_percent);
    return `
        <tr class="si-sla-row${isOpen ? " is-expanded" : ""}" data-shop-id="${escapeHtml(s.shop_id)}">
          <td class="si-sla-shop">
            <div class="si-sla-shop-cell">
              ${chevron}
              <div class="si-sla-shop-text">
                <span class="si-sla-shop-name">${escapeHtml(s.shop_name)}</span>
                <span class="si-sla-shop-meta">ID ${escapeHtml(s.shop_id)} · ${escapeHtml(s.tiktok_shop_name || "—")}</span>
                <span class="si-sla-shop-meta">${mappingReviewBadge(s)}</span>
              </div>
            </div>
          </td>
          <td class="si-v1-num">${fmtShopeeUsd(s.shopee_mtd_adgmv_usd, shReason)}</td>
          <td class="si-v1-num">${fmtTikTokUsd(s.tiktok_mtd_adgmv_usd, s.tiktok_mtd_gmv_php, tkReason)}</td>
          ${mtdSob}
          <td class="si-v1-num">${fmtShopeeUsd(s.shopee_m1_adgmv_usd, shReason)}</td>
          <td class="si-v1-num">${fmtTikTokUsd(s.tiktok_m1_adgmv_usd, s.tiktok_m1_gmv_php, tkReason)}</td>
          ${m1Sob}
          <td class="si-v1-num">${shMom}</td>
          <td class="si-v1-num">${tkMom}</td>
        </tr>`;
  }

  function renderBusinessTableBodyRows(sellers, expandedSet, detailCache) {
    const detail = window.SlaShopDetail;
    return sellers
      .map((s) => {
        const shopId = String(s.shop_id);
        const isOpen = expandedSet.has(shopId);
        const detailState =
          detailCache.get(shopId) || (detail?.defaultDetailState ? detail.defaultDetailState() : {});
        const main = renderBusinessTableRow(s, isOpen);
        const expand =
          detail?.ShopDetailExpandableRow?.(s, isOpen, detailState) || "";
        return main + expand;
      })
      .join("");
  }

  function renderBusinessTable(sellers, expandedSet, detailCache) {
    return `
      <div class="si-sla-table-card">
        <div class="si-v1-table-wrap si-sla-table-wrap">
          <table class="si-v1-table si-sla-table">
            <thead>
              <tr>
                <th class="si-sla-th-shop">Shop</th>
                <th class="si-v1-num">Shopee MTD ADGMV</th>
                <th class="si-v1-num">TikTok MTD ADGMV</th>
                <th class="si-sla-th-sob">MTD SOB</th>
                <th class="si-v1-num">Shopee M-1 ADGMV</th>
                <th class="si-v1-num">TikTok M-1 ADGMV</th>
                <th class="si-sla-th-sob">M-1 SOB</th>
                <th class="si-v1-num">Shopee MoM %</th>
                <th class="si-v1-num">TikTok MoM %</th>
              </tr>
            </thead>
            <tbody>${renderBusinessTableBodyRows(sellers, expandedSet, detailCache)}</tbody>
          </table>
        </div>
      </div>`;
  }

  function renderBusinessPagination(total, page, pageSize) {
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const safePage = Math.min(Math.max(1, page), totalPages);
    const start = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
    const end = Math.min(safePage * pageSize, total);
    const prevDisabled = safePage <= 1 ? " disabled" : "";
    const nextDisabled = safePage >= totalPages ? " disabled" : "";
    return `
      <div class="si-sla-pagination" data-sla-pagination>
        <label class="si-sla-pagination__size">
          <span>${escapeHtml(i18n("si.rowsPerPage", "Rows per page"))}</span>
          <select data-sla-page-size>
            <option value="20"${pageSize === 20 ? " selected" : ""}>20</option>
            <option value="50"${pageSize === 50 ? " selected" : ""}>50</option>
            <option value="100"${pageSize === 100 ? " selected" : ""}>100</option>
          </select>
        </label>
        <span class="si-sla-pagination__range">${start}–${end} ${escapeHtml(i18n("si.ofTotal", "of"))} ${total}</span>
        <div class="si-sla-pagination__nav">
          <button type="button" class="si-sla-pagination__btn" data-sla-page="prev"${prevDisabled}>‹</button>
          <button type="button" class="si-sla-pagination__btn" data-sla-page="next"${nextDisabled}>›</button>
        </div>
      </div>`;
  }

  function bindBusinessPagination(root, st, filteredLength) {
    const pager = root.querySelector("[data-sla-pagination]");
    if (!pager) return;
    pager.querySelector("[data-sla-page-size]")?.addEventListener("change", (ev) => {
      st.pageSize = parseInt(ev.target.value, 10) || 20;
      st.page = 1;
      paintBusinessList();
    });
    pager.querySelector('[data-sla-page="prev"]')?.addEventListener("click", () => {
      if (st.page > 1) {
        st.page -= 1;
        paintBusinessList();
      }
    });
    pager.querySelector('[data-sla-page="next"]')?.addEventListener("click", () => {
      const totalPages = Math.max(1, Math.ceil(filteredLength / st.pageSize));
      if (st.page < totalPages) {
        st.page += 1;
        paintBusinessList();
      }
    });
  }

  function paintBusinessList() {
    const el = containers.siBusiness;
    const st = state.business;
    if (!el || !st.raw) return;
    paintBusinessSummarySob();
    const listEl = el.querySelector("[data-si-list]");
    if (!listEl) return;
    const filtered = filterBusinessSellers(
      st.raw.sellers || [],
      st.filters,
      businessSheetFilters(st.raw)
    );
    const total = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / st.pageSize));
    if (st.page > totalPages) st.page = totalPages;
    if (st.page < 1) st.page = 1;
    const start = (st.page - 1) * st.pageSize;
    const pageRows = filtered.slice(start, start + st.pageSize);

    const countEl = el.querySelector("[data-sla-filter-card] [data-result-count]");
    if (countEl) {
      countEl.textContent = `Showing ${total} of ${(st.raw.sellers || []).length} sellers`;
    }
    if (!filtered.length) {
      listEl.innerHTML = '<p class="si-v1-empty">No sellers match the current filters.</p>';
      return;
    }
    listEl.innerHTML =
      renderBusinessTable(pageRows, st.expanded, st.shopDetail) +
      renderBusinessPagination(total, st.page, st.pageSize);
    bindBusinessPagination(listEl, st, total);
    window.SlaShopDetail?.bindTable?.(
      listEl.querySelector(".si-sla-table"),
      pageRows,
      st.expanded,
      st.shopDetail
    );
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
    const chipsEl = document.getElementById("siBusinessPeriodChips");
    if (chipsEl) {
      chipsEl.innerHTML = renderBusinessPeriodChips(data.periods);
    }
    if (metas.siBusiness) {
      metas.siBusiness.textContent = `${src}${collected} · USD/PHP ${data.usd_php_rate}`;
    }
    if (!state.business.shellReady) {
      el.innerHTML = `<div class="si-sla-shell">${businessFilterCardHtml(state.business.filters, businessSheetFilters(data))}<div class="si-sla-summary-sob" data-sla-summary-sob aria-live="polite"></div><div class="si-sla-list" data-si-list></div></div>`;
      const onToolbar = (ev) => {
        if (ev?.reset) {
          state.business.filters = defaultBusinessFilters();
        } else {
          state.business.filters = readFiltersFromToolbar(
            el.querySelector("[data-toolbar='business']"),
            defaultBusinessFilters()
          );
          state.business.filters = coerceBusinessGpForRm(
            state.business.filters,
            businessSheetFilters(state.business.raw || {})
          );
        }
        state.business.page = 1;
        syncBusinessFilterControls(el);
        paintBusinessList();
      };
      bindToolbar(el.querySelector("[data-toolbar='business']"), onToolbar);
      state.business.shellReady = true;
    } else {
      if (!el.querySelector("[data-sla-summary-sob]")) {
        const listEl = el.querySelector("[data-si-list]");
        if (listEl?.parentNode) {
          const summary = document.createElement("div");
          summary.className = "si-sla-summary-sob";
          summary.setAttribute("data-sla-summary-sob", "");
          summary.setAttribute("aria-live", "polite");
          listEl.parentNode.insertBefore(summary, listEl);
        }
      }
      syncBusinessFilterControls(el);
    }
    applyPersistedSlaUpdateState(data);
    paintBusinessList();
  }

  /* ---------- Assortment TikTok Product Radar ---------- */

  function renderRadarBadges(p, opts = {}) {
    const bits = [];
    if (p.new_badge) {
      bits.push(`<span class="si-radar-badge si-radar-badge--new">NEW · ${escapeHtml(p.new_badge)}</span>`);
    }
    if (opts.showGrowth && p.growth_score != null) {
      const arrow = p.trend_arrow === "up" ? "▲" : "●";
      bits.push(
        `<span class="si-radar-badge si-radar-badge--growth">${arrow} ${fmtNum(p.growth_score, 1)}</span>`
      );
    }
    if (opts.showOpportunity && p.opportunity_label) {
      bits.push(
        `<span class="si-radar-badge si-radar-badge--opp">${escapeHtml(p.opportunity_label)}</span>`
      );
    }
    return bits.length ? `<div class="si-radar-badges">${bits.join("")}</div>` : "";
  }

  function renderRadarProductCard(p, opts = {}) {
    const rank = p.rank != null ? `<span class="si-radar-rank">#${p.rank}</span>` : "";
    const days =
      p.days_since_launch != null
        ? `<span class="si-radar-meta">${p.days_since_launch}d since launch</span>`
        : "";
    return `
      <article class="si-radar-card">
        <div class="si-radar-card-media">
          ${rank}
          <img src="${escapeHtml(p.product_image || "")}" alt="" loading="lazy" />
          ${renderRadarBadges(p, opts)}
        </div>
        <div class="si-radar-card-body">
          <h4>${escapeHtml(p.product_name || "—")}</h4>
          <p class="si-radar-shop">${escapeHtml(p.shop_name || "—")}</p>
          <p class="si-radar-category">${escapeHtml(p.category || "Uncategorized")}</p>
          <div class="si-radar-metrics">
            <span><strong>${fmtPhp(p.product_price_php) || "—"}</strong></span>
            <span>Sold ${fmtNum(p.sold_count)}</span>
            <span>Sales ${fmtPhp(p.sales_amount) || "—"}</span>
          </div>
          <div class="si-radar-meta-row">
            ${days}
            <span>${escapeHtml(p.upload_date || "—")}</span>
          </div>
          ${
            opts.showGrowth
              ? `<p class="si-radar-score">Growth score <strong>${fmtNum(p.growth_score, 1)}</strong></p>`
              : ""
          }
          ${
            opts.showOpportunity
              ? `<p class="si-radar-score">Opportunity <strong>${fmtNum(p.opportunity_score, 1)}</strong></p>`
              : ""
          }
          <a class="si-radar-link" href="${escapeHtml(p.product_link || "#")}" target="_blank" rel="noopener noreferrer">View on TikTok</a>
        </div>
      </article>`;
  }

  function renderRadarSection(title, products, opts = {}) {
    if (!products.length) {
      return `<section class="si-radar-section"><h3 class="si-radar-section-title">${escapeHtml(title)}</h3><p class="si-v1-empty">No products in this section.</p></section>`;
    }
    return `
      <section class="si-radar-section" id="${escapeHtml(opts.anchor || "")}">
        <div class="si-radar-section-head">
          <h3 class="si-radar-section-title">${escapeHtml(title)}</h3>
          <span class="si-radar-section-count">${products.length} products</span>
        </div>
        <div class="si-radar-grid">${products.map((p) => renderRadarProductCard(p, opts)).join("")}</div>
      </section>`;
  }

  function renderRadarPortfolio(data) {
    const p = data.portfolio || {};
    const fm = data.fastmoss || {};
    return `
      <div class="si-radar-portfolio">
        <div class="si-port-kpi-grid">
          ${renderPortfolioKpi("Total Products", fmtNum(p.total_products), `${fmtNum(fm.shops_scanned)} shops scanned`, "hero")}
          ${renderPortfolioKpi("New Products (20D)", fmtNum(p.new_products_20d), "Upload ≤ 20 days", "accent")}
          ${renderPortfolioKpi("Growth Products", fmtNum(p.growth_products), "Top momentum picks", "tiktok")}
          ${renderPortfolioKpi("Opportunity Products", fmtNum(p.opportunity_products), "High opportunity radar", "shopee")}
        </div>
      </div>`;
  }

  function renderRadarShopSummary(summary, shopName) {
    const s = summary || {};
    return `
      <div class="si-radar-portfolio">
        <div class="si-port-kpi-grid">
          ${renderPortfolioKpi("Shop", escapeHtml(shopName || "—"), "Selected seller", "hero")}
          ${renderPortfolioKpi("Total Products", fmtNum(s.total_products), "FastMoss catalog", "neutral")}
          ${renderPortfolioKpi("New Products (20D)", fmtNum(s.new_products_20d), "Upload ≤ 20 days", "accent")}
          ${renderPortfolioKpi("Growth Products", fmtNum(s.growth_products), "Top momentum in shop", "tiktok")}
          ${renderPortfolioKpi("Opportunity Products", fmtNum(s.opportunity_products), "High opportunity picks", "shopee")}
        </div>
      </div>`;
  }

  function renderCategorySummaryCard(cat, activeCategory) {
    const active = cat.category === activeCategory ? " is-active" : "";
    const topShop = cat.top_shop?.shop_name || "—";
    const topProduct = cat.top_product?.product_name || "—";
    return `
      <article class="si-radar-cat-card${active}" data-category-card="${escapeHtml(cat.category)}">
        <div class="si-radar-cat-card-head">
          <h4>${escapeHtml(cat.category)}</h4>
          <span class="si-radar-section-count">${fmtNum(cat.total_products)} products</span>
        </div>
        <div class="si-radar-cat-metrics">
          <div><span>Sales</span><strong>${fmtPhp(cat.total_sales_amount) || "—"}</strong></div>
          <div><span>Sold</span><strong>${fmtNum(cat.total_sold_count)}</strong></div>
          <div><span>New (20D)</span><strong>${fmtNum(cat.new_products_20d)}</strong></div>
          <div><span>Growth</span><strong>${fmtNum(cat.growth_products)}</strong></div>
        </div>
        <div class="si-radar-cat-leaders">
          <p><span>Top shop</span> ${escapeHtml(topShop)}</p>
          <p><span>Top product</span> ${escapeHtml(topProduct)}</p>
        </div>
      </article>`;
  }

  function renderCategorySummaryGrid(categories, activeCategory, query) {
    const q = (query || "").trim().toLowerCase();
    const filtered = (categories || []).filter((c) => !q || String(c.category || "").toLowerCase().includes(q));
    if (!filtered.length) {
      return '<p class="si-v1-empty">No categories match the current search.</p>';
    }
    return `<div class="si-radar-cat-grid">${filtered.map((c) => renderCategorySummaryCard(c, activeCategory)).join("")}</div>`;
  }

  function renderCategoryTopShopsSection(shops) {
    if (!shops?.length) {
      return `<section class="si-radar-section"><h3 class="si-radar-section-title">Top Shops by Sales</h3><p class="si-v1-empty">No shop data for this category.</p></section>`;
    }
    const rows = shops
      .map(
        (s) => `<tr>
          <td class="si-port-rank">#${s.rank}</td>
          <td>${escapeHtml(s.shop_name || "—")}</td>
          <td class="si-v1-num">${fmtPhp(s.total_sales_amount) || "—"}</td>
          <td class="si-v1-num">${fmtNum(s.total_sold_count)}</td>
          <td class="si-v1-num">${fmtNum(s.product_count)}</td>
        </tr>`
      )
      .join("");
    return `
      <section class="si-radar-section" id="category-shops">
        <div class="si-radar-section-head">
          <h3 class="si-radar-section-title">Top Shops by Sales in Category</h3>
          <span class="si-radar-section-count">${shops.length} shops</span>
        </div>
        <div class="si-v1-table-wrap">
          <table class="si-v1-table si-v1-table--portfolio">
            <thead>
              <tr>
                <th>#</th>
                <th>Shop</th>
                <th>Sales Amount</th>
                <th>Sold Count</th>
                <th>Products</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>`;
  }

  function radarVisibleShopIds(data, f) {
    const sheetFilters = radarSheetFilters(data);
    const shops = radarFilteredShops(data?.filters?.shops || [], f, sheetFilters);
    if (f.shop && f.shop !== "all") {
      return shops.some((s) => String(s.shop_id) === String(f.shop)) ? [String(f.shop)] : [];
    }
    return shops.map((s) => String(s.shop_id));
  }

  function radarCollectProducts(data, shopIds, kind) {
    const rows = [];
    const seen = new Set();
    for (const shop of data?.shop_view?.shops || []) {
      if (shopIds.length && !shopIds.includes(String(shop.shop_id))) continue;
      let list = [];
      if (kind === "top") list = shop.top_products || [];
      else if (kind === "new") list = shop.new_products || [];
      else if (kind === "growth") list = shop.growth_products || [];
      else if (kind === "all") {
        list = [
          ...(shop.top_products || []),
          ...(shop.new_products || []),
          ...(shop.growth_products || []),
        ];
      }
      for (const p of list) {
        const key = String(p.product_id || p.product_link || "");
        if (!key || seen.has(key)) continue;
        seen.add(key);
        rows.push(p);
      }
    }
    const newLimit = shopIds.length === 1 ? 10 : 30;
    if (kind === "top") {
      return rows
        .sort(
          (a, b) =>
            (b.sales_amount ?? 0) - (a.sales_amount ?? 0) ||
            (b.sold_count ?? 0) - (a.sold_count ?? 0)
        )
        .slice(0, 30);
    }
    if (kind === "new") {
      return rows
        .sort(
          (a, b) =>
            (a.days_since_launch ?? 9999) - (b.days_since_launch ?? 9999) ||
            (b.sales_amount ?? 0) - (a.sales_amount ?? 0)
        )
        .slice(0, newLimit);
    }
    if (kind === "growth") {
      return rows
        .sort((a, b) => (b.growth_score ?? 0) - (a.growth_score ?? 0))
        .slice(0, 30);
    }
    return rows;
  }

  function radarActiveProductKind(f) {
    return f.productType || "top";
  }

  function radarTableKind(kind) {
    return kind === "all" ? "top" : kind;
  }

  function renderRadarProductLink(p) {
    const href = p.product_link || "#";
    if (!href || href === "#") return "—";
    return `<a class="si-radar-table-link" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Open</a>`;
  }

  function renderRadarProductsTable(products, kind) {
    if (!products.length) {
      return '<p class="si-v1-empty">No products in this view.</p>';
    }
    const baseHead = `
      <th>Shop</th>
      <th>TikTok shop</th>
      <th>Product</th>
      <th>Link</th>`;
    let extraHead = "";
    if (kind === "new") {
      extraHead = `<th>Upload date</th><th>Days</th>`;
    }
    if (kind === "growth") {
      extraHead = `<th>Growth %</th><th>Trend</th>`;
    }
    const tailHead = `
      <th class="si-v1-num">GMV</th>
      <th class="si-v1-num">Sales</th>
      <th class="si-v1-num">Price</th>
      ${kind === "top" || kind === "growth" ? '<th class="si-v1-num">Rank</th>' : ""}
      <th>Category</th>
      <th>Last updated</th>`;

    const rows = products
      .map((p) => {
        const growthPct =
          p.growth_percent != null ? `${fmtNum(p.growth_percent, 1)}%` : fmtNum(p.growth_score, 1);
        let extraCells = "";
        if (kind === "new") {
          extraCells = `<td>${escapeHtml(p.upload_date || "—")}</td><td class="si-v1-num">${p.days_since_launch != null ? fmtNum(p.days_since_launch) : "—"}</td>`;
        }
        if (kind === "growth") {
          extraCells = `<td class="si-v1-num">${growthPct}</td><td>${escapeHtml(p.rank_change || p.trend_arrow || "—")}</td>`;
        }
        return `<tr>
          <td>${escapeHtml(p.shop_name || "—")}</td>
          <td>${escapeHtml(p.tiktok_shop_name || "—")}</td>
          <td>${escapeHtml(p.product_name || "—")}</td>
          <td>${renderRadarProductLink(p)}</td>
          ${extraCells}
          <td class="si-v1-num">${fmtPhp(p.sales_amount) || "—"}</td>
          <td class="si-v1-num">${fmtNum(p.sold_count)}</td>
          <td class="si-v1-num">${fmtPhp(p.product_price_php) || "—"}</td>
          ${kind === "top" || kind === "growth" ? `<td class="si-v1-num">${p.rank != null ? fmtNum(p.rank) : "—"}</td>` : ""}
          <td>${escapeHtml(p.category || "—")}</td>
          <td>${escapeHtml(p.last_updated || "—")}</td>
        </tr>`;
      })
      .join("");

    return `
      <div class="si-sla-table-card si-radar-table-card">
        <div class="si-sla-table-wrap">
          <table class="si-sla-table si-radar-products-table">
            <thead><tr>${baseHead}${extraHead}${tailHead}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  }

  function paintAssortmentRadar() {
    const el = containers.siAssortment;
    const st = state.assortment;
    if (!el || !st.raw) return;
    const body = el.querySelector("[data-radar-body]");
    if (!body) return;
    const v = st.raw.validation || {};
    const refresh = st.raw.refresh_status || {};
    if (refresh.running || v.refresh_running) {
      body.innerHTML = `<div class="si-radar-loading" role="status"><div class="si-port-state-spinner" aria-hidden="true"></div><p>Loading TikTok product catalog…</p></div>`;
      return;
    }
    if ((v.mapped_product_count || 0) === 0) {
      body.innerHTML = `<p class="si-v1-empty">${radarEmptyMessage(st.raw)}</p>`;
      return;
    }

    const f = coerceRadarFilters(st.filters, st.raw);
    st.filters = f;
    const shopIds = radarVisibleShopIds(st.raw, f);
    if (!shopIds.length) {
      body.innerHTML = `<p class="si-v1-empty">No mapped shops match the current RM / GP / Shop filters.</p>`;
      return;
    }

    const kind = radarActiveProductKind(f);
    let products = radarCollectProducts(st.raw, shopIds, kind);
    products = filterRadarProducts(products, f);

    const countEl = el.querySelector("[data-radar-filter-card] [data-radar-result-count]");
    if (countEl) {
      const scope =
        f.shop !== "all"
          ? (st.raw.filters?.shops || []).find((s) => String(s.shop_id) === String(f.shop))?.shop_name ||
            f.shop
          : `${shopIds.length} shops`;
      countEl.textContent = `Showing ${products.length} products · ${scope}`;
    }

    el.querySelectorAll("[data-radar-segment]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.radarSegment === kind);
    });

    if (!products.length) {
      body.innerHTML = `<p class="si-v1-empty">${radarEmptyMessage(st.raw, { filteredEmpty: true })}</p>`;
      return;
    }
    body.innerHTML = renderRadarProductsTable(products, radarTableKind(kind));
  }

  function bindRadarSegments(el) {
    el.querySelectorAll("[data-radar-segment]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const seg = btn.dataset.radarSegment;
        if (!seg) return;
        state.assortment.filters.productType = seg;
        state.assortment.filters.productTypeSegment = seg;
        const typeSel = el.querySelector("#siRadarProductType");
        if (typeSel) typeSel.value = seg;
        el.querySelectorAll("[data-radar-segment]").forEach((b) => {
          b.classList.toggle("is-active", b.dataset.radarSegment === seg);
        });
        paintAssortmentRadar();
      });
    });
  }

  function setupAssortment(data) {
    const el = containers.siAssortment;
    if (!el) return;
    logRadarDebug(data, "render");
    state.assortment.raw = data;
    state.assortment.filters = coerceRadarFilters(state.assortment.filters, data);

    const fm = data.fastmoss || {};
    const p = data.portfolio || {};
    const v = data.validation || {};
    const ds = data.data_source || {};
    const shopCount = v.shop_count ?? (data.filters?.shops || []).length;
    const updated = data.last_updated || data.generated_at || "—";
    if (metas.siAssortment) {
      const tab = ds.seller_master_tab || data.tab || "shpoee link";
      metas.siAssortment.textContent = [
        `TikTok Product Radar · ${fmtNum(p.total_products)} products · ${fmtNum(shopCount)} mapped shops`,
        tab ? `Sheet: ${tab}` : "",
        `Last updated: ${updated}`,
        v.data_status && v.data_status !== "ok" ? v.data_status : "",
      ]
        .filter(Boolean)
        .join(" · ");
    }

    const onToolbar = (ev) => {
      if (ev?.reset) {
        state.assortment.filters = defaultAssortmentFilters();
      } else {
        state.assortment.filters = readFiltersFromToolbar(
          el.querySelector("[data-toolbar='radar']"),
          defaultAssortmentFilters()
        );
        state.assortment.filters = coerceRadarFilters(state.assortment.filters, state.assortment.raw);
      }
      syncRadarFilterControls(el);
      paintAssortmentRadar();
    };

    if (!state.assortment.shellReady) {
      el.innerHTML = `<div class="si-radar-shell">${radarFilterCardHtml(state.assortment.filters, data)}${radarSegmentHtml(state.assortment.filters.productType || "top")}<div class="si-radar-body-wrap" data-radar-body></div></div>`;
      bindToolbar(el.querySelector("[data-toolbar='radar']"), onToolbar);
      bindRadarSegments(el);
      state.assortment.shellReady = true;
    } else {
      if (!el.querySelector("[data-radar-filter-card]")) {
        state.assortment.shellReady = false;
        setupAssortment(data);
        return;
      }
      syncRadarFilterControls(el);
    }
    paintAssortmentRadar();
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

  function showDashboardLoading() {
    const el = containers.siDashboard;
    if (!el) return;
    el.innerHTML = `
      <div class="si-port-state si-port-state--loading" role="status" aria-live="polite">
        <div class="si-port-state-spinner" aria-hidden="true"></div>
        <p class="si-port-state-title">${escapeHtml(i18n("si.dashboardLoading", "Loading portfolio overview…"))}</p>
      </div>`;
    if (metas.siDashboard) {
      metas.siDashboard.textContent = i18n("si.dashboardLoadingMeta", "Loading…");
    }
  }

  function showDashboardError(message, detail) {
    const el = containers.siDashboard;
    if (!el) return;
    console.error("[Portfolio Overview] API/render error:", message, detail || "");
    el.innerHTML = `
      <div class="si-port-state si-port-state--error" role="alert">
        <p class="si-port-state-title">${escapeHtml(i18n("si.dashboardErrorTitle", "Could not load Portfolio Overview"))}</p>
        <p class="si-port-state-message">${escapeHtml(message || "Unknown error")}</p>
        ${detail ? `<pre class="si-port-state-detail">${escapeHtml(String(detail))}</pre>` : ""}
        <button type="button" class="btn si-v1-action-btn" data-dashboard-retry>${escapeHtml(i18n("si.dashboardRetry", "Retry"))}</button>
      </div>`;
    el.querySelector("[data-dashboard-retry]")?.addEventListener("click", () => {
      delete cache.siDashboard;
      loadDashboardView().catch(() => {});
    });
    if (metas.siDashboard) {
      metas.siDashboard.textContent = i18n("si.dashboardErrorMeta", "Load failed");
    }
  }

  function showDashboardEmpty(message) {
    const el = containers.siDashboard;
    if (!el) return;
    el.innerHTML = `
      <div class="si-port-state si-port-state--empty" role="status">
        <p class="si-port-state-title">${escapeHtml(i18n("si.dashboardEmptyTitle", "No portfolio data yet"))}</p>
        <p class="si-port-state-message">${escapeHtml(message || i18n("si.dashboardEmptyHint", "Refresh data after Seller Master sync."))}</p>
        <button type="button" class="btn si-v1-action-btn" data-dashboard-retry>${escapeHtml(i18n("si.dashboardRetry", "Retry"))}</button>
      </div>`;
    el.querySelector("[data-dashboard-retry]")?.addEventListener("click", () => {
      delete cache.siDashboard;
      loadDashboardView().catch(() => {});
    });
    if (metas.siDashboard) {
      metas.siDashboard.textContent = i18n("si.dashboardEmptyMeta", "No data");
    }
  }

  function isDashboardPayloadEmpty(data) {
    if (!data || typeof data !== "object") return true;
    const sellerCount = Number(data.seller_count ?? data.portfolio?.total_sellers);
    if (!Number.isFinite(sellerCount) || sellerCount <= 0) return true;
    return false;
  }

  function safeRenderDashboard(data) {
    const el = containers.siDashboard;
    if (!el) return;
    try {
      if (isDashboardPayloadEmpty(data)) {
        showDashboardEmpty(
          i18n(
            "si.dashboardEmptyHint",
            "No sellers loaded yet. Click Refresh Data after Seller Master sync."
          )
        );
        return;
      }
      renderDashboard(data);
    } catch (err) {
      console.error("[Portfolio Overview] render failed:", err);
      showDashboardError(err.message || "Could not render portfolio overview", err.stack);
    }
  }

  async function loadDashboardView() {
    const el = containers.siDashboard;
    if (!el) return;

    if (cache.siDashboard) {
      safeRenderDashboard(cache.siDashboard);
      return;
    }

    showDashboardLoading();
    try {
      const res = await fetchApi(API.dashboard);
      let data = {};
      try {
        data = await res.json();
      } catch (parseErr) {
        console.error("[Portfolio Overview] invalid JSON response:", parseErr);
        showDashboardError("Portfolio API returned invalid JSON.", parseErr.message);
        return;
      }
      if (!res.ok) {
        const detail = data.detail || data.message || `HTTP ${res.status}`;
        showDashboardError(String(detail), JSON.stringify(data, null, 2));
        return;
      }
      cache.siDashboard = data;
      safeRenderDashboard(data);
    } catch (err) {
      showDashboardError(err.message || "Failed to load portfolio overview", err.stack);
    }
  }

  function renderDashboard(data) {
    const el = containers.siDashboard;
    if (!el) return;
    const payload = data && typeof data === "object" ? data : {};
    const fm = payload.modules?.business_intelligence || {};
    const src = fm.fastmoss_connected ? "FastMoss TikTok" : "Seller master";
    if (metas.siDashboard) {
      metas.siDashboard.textContent = `${periodLabel(payload.periods)} · ${src} · USD/PHP ${payload.usd_php_rate ?? "—"}`;
    }
    el.innerHTML = renderPortfolioOverview(payload);
    animateSobBars(el);
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

  function showRadarLoading(message = "Loading…") {
    const el = containers.siAssortment;
    if (!el) return;
    el.innerHTML = `<p class="si-v1-loading">${escapeHtml(message)}</p>`;
    state.assortment.shellReady = false;
  }

  async function loadAssortmentView({ refreshProducts = false } = {}) {
    showRadarLoading(
      refreshProducts
        ? i18n("si.radarRefreshing", "Refreshing product catalog…")
        : i18n("si.radarLoading", "Loading TikTok Product Radar…")
    );
    try {
      if (refreshProducts) {
        await startRadarProductRefresh();
        cache.siAssortment = await pollRadarUntilReady();
      } else {
        cache.siAssortment = await loadWithTimeout(API.assortment, {}, RADAR_LOAD_TIMEOUT_MS);
      }
      setupAssortment(cache.siAssortment);
    } catch (err) {
      console.error("[TikTok Product Radar] load failed:", err);
      showError("siAssortment", err.message || "Failed to load TikTok Product Radar");
      if (metas.siAssortment) {
        metas.siAssortment.textContent = i18n("si.radarLoadFailed", "Load failed");
      }
    }
  }

  async function onShow(view) {
    if (view === "siDashboard") {
      await loadDashboardView();
      return;
    }

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
      if (view === "siVoucher") renderVoucher(cache[view]);
      return;
    }

    if (view === "siAssortment") {
      await loadAssortmentView({ refreshProducts: false });
      return;
    }

    if (!cache[view]) showLoading(view);

    try {
      if (!cache[view]) {
        cache[view] = await load(path);
      }
      const data = cache[view];
      if (view === "siBusiness") setupBusiness(data);
      else if (view === "siVoucher") renderVoucher(data);
    } catch (err) {
      showError(view, err.message || "Failed to load");
    }
  }

  async function refreshBusinessData() {
    const btn = document.getElementById("siBusinessRefreshDataBtn");
    const defaultLabel = i18n("si.refreshData", "Update Data");
    if (btn) {
      btn.disabled = true;
      btn.classList.add("is-loading");
      btn.textContent = i18n("si.dataRefreshing", "Updating…");
    }
    resetSlaRefreshPanelForRun();
    setSlaProgressVisible(true);
    renderSlaProgress({
      step_label: i18n("si.refreshStarting", "Starting update…"),
      percent: 0,
      shops_processed: 0,
      shops_total: 0,
      elapsed_sec: 0,
    });
    try {
      const startRes = await fetchApi(API.businessRefreshData, { method: "POST" });
      const started = await startRes.json();
      if (!startRes.ok) {
        throw new Error(started.detail || "Could not start update");
      }
      if (started.running || started.step_label) {
        renderSlaProgress(started);
      }
      const result = await pollSlaRefreshUntilDone();
      window.ShpPlatform?.showPlatformToast?.(
        i18n("si.dataRefreshSuccess", "Seller Level Analysis updated")
      );
      const mapSum = result.mapping?.summary || {};
      const finalStatus = {
        step_label: i18n("si.refreshComplete", "Completed"),
        percent: 100,
        shops_processed: mapSum.total ?? 0,
        shops_total: mapSum.total ?? 0,
        newly_mapped_count: result.mapping?.newly_mapped_count ?? 0,
        pending_review_count: mapSum.need_review ?? 0,
        still_not_found_count: mapSum.not_found ?? 0,
        refreshed_at: result.refreshed_at,
      };
      renderSlaProgress(finalStatus);
      markSlaRefreshComplete(result, finalStatus);
      setSlaRefreshCollapsed(true);
      setSharedSlaLastUpdatedHeader(result.refreshed_at);
      const summaryEl = document.getElementById("siBusinessActionSummary");
      if (summaryEl) summaryEl.classList.add("hidden");
      window.ShpHistoricalSob?.clearCache?.();
      document.dispatchEvent(
        new CustomEvent("sla-update-complete", { detail: { result, status: finalStatus } })
      );
      delete cache.siBusiness;
      state.business.shellReady = false;
      await onShow("siBusiness");
      return result;
    } catch (err) {
      window.ShpPlatform?.showPlatformToast?.(err.message || "Refresh failed", "error");
      throw err;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.classList.remove("is-loading");
        btn.textContent = defaultLabel;
      }
    }
  }

  document.getElementById("siBusinessRefreshDataBtn")?.addEventListener("click", () => {
    refreshBusinessData().catch(() => {});
  });

  slaRefreshUi.toggleBtn?.addEventListener("click", () => {
    setSlaRefreshCollapsed(!slaRefreshState.collapsed);
  });

  document.getElementById("siRadarRefreshDataBtn")?.addEventListener("click", () => {
    delete cache.siAssortment;
    state.assortment.shellReady = false;
    loadAssortmentView({ refreshProducts: true }).catch(() => {});
  });

  window.ShpIntelligenceV1 = {
    onShow,
    loadDashboardView,
    loadAssortmentView,
    clearCache: () => {
      Object.keys(cache).forEach((k) => delete cache[k]);
      state.business.shellReady = false;
      state.assortment.shellReady = false;
      state.business.expanded.clear();
      state.business.shopDetail.clear();
      state.assortment.expanded.clear();
    },
    refreshBusinessData,
    refreshRadarProducts: () => loadAssortmentView({ refreshProducts: true }),
    formatSlaLastUpdatedHeader,
    applySharedSlaUpdateState,
    setSharedSlaLastUpdatedHeader,
  };
})();
