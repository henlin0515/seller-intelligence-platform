/**
 * TikTok Competitor Voucher Tracker — profile → shop search → vouchers
 */
(function () {
  const tableBody = document.getElementById("cvtTableBody");
  const metaBar = document.getElementById("cvtMetaBar");
  const btnCheckSelected = document.getElementById("cvtCheckSelected");
  const btnCheckAll = document.getElementById("cvtCheckAll");
  const btnReload = document.getElementById("cvtReloadSheet");
  const selectAll = document.getElementById("cvtSelectAll");
  const debugModal = document.getElementById("cvtDebugModal");
  const debugShop = document.getElementById("cvtDebugShop");
  const debugBody = document.getElementById("cvtDebugBody");

  let competitors = [];

  const REASON_ORDER = [
    "summary",
    "profile_url",
    "extracted_profile_name",
    "profile_handle",
    "profile_followers",
    "profile_bio",
    "profile_external_links",
    "search_query_used",
    "search_results_count",
    "search_blocked",
    "selected_match",
    "match_confidence",
    "match_score",
    "matched_shop_name",
    "tiktok_shop_url",
    "voucher_detection_result",
    "voucher_status",
    "final_url",
    "http_status",
    "page_title",
    "html_loaded",
    "html_length",
    "visible_text_length",
    "tiktok_blocked",
    "login_required",
    "voucher_keywords_found",
    "matched_keywords",
    "dom_voucher_found",
    "dom_matches",
    "used_playwright",
    "used_http",
    "redirect_chain",
    "fetch_error",
  ];

  const REASON_LABELS = {
    profile_url: "Profile URL",
    extracted_profile_name: "Extracted Profile Name",
    profile_handle: "Handle",
    profile_followers: "Followers",
    profile_bio: "Bio",
    profile_external_links: "External links",
    search_query_used: "Search Query Used",
    search_results_count: "Search Results Count",
    search_blocked: "Search blocked",
    selected_match: "Selected Match",
    match_confidence: "Match Confidence",
    match_score: "Match score",
    matched_shop_name: "Matched TikTok Shop Name",
    tiktok_shop_url: "TikTok Shop URL",
    voucher_detection_result: "Voucher Detection Result",
    voucher_status: "Voucher status",
    final_url: "Final resolved URL",
    http_status: "HTTP status",
    page_title: "Page title",
    html_loaded: "Page HTML loaded",
    html_length: "HTML size (chars)",
    visible_text_length: "Visible text size (chars)",
    tiktok_blocked: "TikTok blocked access",
    login_required: "Login required",
    voucher_keywords_found: "Voucher keywords found",
    matched_keywords: "Matched keywords",
    dom_voucher_found: "DOM voucher elements found",
    dom_matches: "DOM matches",
    used_playwright: "Playwright used",
    used_http: "HTTP fallback used",
    redirect_chain: "Redirect chain",
    fetch_error: "Fetch error (safe)",
    summary: "Summary",
  };

  function i18n(key, fallback = "") {
    return window.SipI18n?.t(key, fallback) ?? fallback ?? key;
  }

  function reasonLabel(key) {
    const i18nKey = `tracker.reason.${key}`;
    const translated = i18n(i18nKey, "");
    if (translated && translated !== i18nKey) return translated;
    return REASON_LABELS[key] || key;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = String(text ?? "");
    return div.innerHTML;
  }

  function statusLabel(status) {
    const key = `tracker.status.${status || "unchecked"}`;
    return i18n(key, status || "unchecked");
  }

  function formatTime(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  function formatReasonValue(key, value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "boolean") return value ? i18n("tracker.yes", "Yes") : i18n("tracker.no", "No");
    if (Array.isArray(value)) {
      if (!value.length) return "—";
      return value.map((v) => String(v)).join(" · ");
    }
    return String(value);
  }

  function linkOrDash(url, label) {
    if (!url) return "—";
    return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label || i18n("tracker.link", "Link"))}</a>`;
  }

  function setMeta(text, isError = false) {
    if (!metaBar) return;
    metaBar.textContent = text;
    metaBar.classList.toggle("is-error", isError);
  }

  function setBusy(busy) {
    if (btnCheckSelected) btnCheckSelected.disabled = busy;
    if (btnCheckAll) btnCheckAll.disabled = busy;
    if (btnReload) btnReload.disabled = busy;
  }

  function getSelectedIds() {
    return Array.from(document.querySelectorAll(".cvt-row-check:checked")).map((el) => el.value);
  }

  function openDebugModal(shopId) {
    const c = competitors.find((x) => x.shop_id === shopId);
    if (!c || !debugModal) return;
    if (debugShop) {
      debugShop.textContent = `${c.shop_name} (${c.shop_id})`;
    }
    const reason = c.check_reason || {};
    if (debugBody) {
      debugBody.innerHTML = REASON_ORDER.filter(
        (k) => reason[k] !== undefined && reason[k] !== null && reason[k] !== ""
      )
        .map(
          (k) => `
        <dt>${escapeHtml(reasonLabel(k))}</dt>
        <dd>${escapeHtml(formatReasonValue(k, reason[k]))}</dd>`
        )
        .join("");
    }
    debugModal.classList.remove("hidden");
  }

  function closeDebugModal() {
    debugModal?.classList.add("hidden");
  }

  function renderTable() {
    if (!tableBody) return;
    const cols = 12;
    if (!competitors.length) {
      tableBody.innerHTML = `<tr><td colspan="${cols}" class="cvt-empty">${escapeHtml(
        i18n("tracker.empty", "No competitors loaded from COMPETITOR_TRACKER.")
      )}</td></tr>`;
      return;
    }

    tableBody.innerHTML = competitors
      .map((c) => {
        const status = c.voucher_status || "unchecked";
        const statusClass = `cvt-status cvt-status-${status}`;
        const profileUrl = c.profile_url || c.tiktok_link;
        const hasDetails = Boolean(c.check_reason && c.last_checked_at);
        return `
        <tr data-shop-id="${escapeHtml(c.shop_id)}">
          <td><input type="checkbox" class="cvt-row-check" value="${escapeHtml(c.shop_id)}" aria-label="Select ${escapeHtml(c.shop_name)}" /></td>
          <td>${escapeHtml(c.shop_id)}</td>
          <td>${escapeHtml(c.shop_name)}</td>
          <td>${escapeHtml(c.extracted_profile_name || "—")}</td>
          <td>${linkOrDash(profileUrl, i18n("tracker.profile", "Profile"))}</td>
          <td>${escapeHtml(c.matched_shop_name || "—")}</td>
          <td>${escapeHtml(c.match_confidence || "—")}</td>
          <td>${linkOrDash(c.tiktok_shop_url, i18n("tracker.shop", "Shop"))}</td>
          <td><span class="${statusClass}">${escapeHtml(statusLabel(status))}</span></td>
          <td class="cvt-voucher-text">${escapeHtml(c.voucher_text || "—")}</td>
          <td>${escapeHtml(formatTime(c.last_checked_at))}</td>
          <td>
            ${
              hasDetails
                ? `<button type="button" class="btn btn-ghost btn-sm cvt-details-btn" data-shop-id="${escapeHtml(c.shop_id)}">${escapeHtml(i18n("tracker.viewDetails", "Details"))}</button>`
                : "—"
            }
          </td>
        </tr>`;
      })
      .join("");

    tableBody.querySelectorAll(".cvt-details-btn").forEach((btn) => {
      btn.addEventListener("click", () => openDebugModal(btn.dataset.shopId));
    });
  }

  function mergeCheckResults(results) {
    const byId = Object.fromEntries((results || []).map((r) => [r.shop_id, r]));
    competitors = competitors.map((c) => {
      const u = byId[c.shop_id];
      if (!u) return c;
      return {
        ...c,
        ...u,
        profile_url: u.profile_url || c.tiktok_link,
        tiktok_link: c.tiktok_link,
      };
    });
    renderTable();
  }

  function markChecking(shopIds) {
    const set = new Set(shopIds);
    tableBody?.querySelectorAll("tr[data-shop-id]").forEach((tr) => {
      tr.classList.toggle("is-checking", set.has(tr.dataset.shopId));
    });
  }

  async function loadList(refresh = false) {
    setBusy(true);
    setMeta(i18n("tracker.loading", "Loading competitors from sheet…"));
    try {
      const q = refresh ? "?refresh=1" : "";
      const res = await (window.SipApi ? window.SipApi.fetch : fetch)(
        `/api/competitor-voucher/competitors${q}`,
        { credentials: "same-origin" }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "load failed");
      competitors = data.competitors || [];
      const meta = data.meta || {};
      setMeta(meta.error ? meta.error : i18n("tracker.metaLoaded", "{count} competitors").replace("{count}", String(competitors.length)), Boolean(meta.error));
      renderTable();
    } catch {
      setMeta(i18n("tracker.loadFailed", "Could not load competitor list."), true);
      competitors = [];
      renderTable();
    } finally {
      setBusy(false);
    }
  }

  async function runCheck(shopIds) {
    if (!shopIds.length) {
      alert(i18n("tracker.selectOne", "Select at least one shop."));
      return;
    }
    setBusy(true);
    markChecking(shopIds);
    setMeta(i18n("tracker.checking", "Checking TikTok profiles and shops…"));
    try {
      const res = await (window.SipApi ? window.SipApi.fetch : fetch)("/api/competitor-voucher/check", {
        credentials: "same-origin",
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shop_ids: shopIds }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "check failed");
      if (!data.ok && data.message) {
        setMeta(data.message, true);
        return;
      }
      mergeCheckResults(data.results);
      setMeta(i18n("tracker.checked", "Checked {n} shop(s).").replace("{n}", String(data.checked ?? 0)));
    } catch {
      setMeta(i18n("tracker.checkFailed", "Voucher check failed. Try again."), true);
    } finally {
      setBusy(false);
      markChecking([]);
    }
  }

  btnCheckSelected?.addEventListener("click", () => runCheck(getSelectedIds()));
  btnCheckAll?.addEventListener("click", () => {
    const ids = competitors.map((c) => c.shop_id);
    if (ids.length) runCheck(ids);
  });
  btnReload?.addEventListener("click", () => loadList(true));
  selectAll?.addEventListener("change", () => {
    document.querySelectorAll(".cvt-row-check").forEach((el) => {
      el.checked = selectAll.checked;
    });
  });
  debugModal?.querySelectorAll("[data-cvt-close-modal]").forEach((el) => {
    el.addEventListener("click", closeDebugModal);
  });

  window.ShpCompetitorTracker = { onShow: () => { if (!competitors.length) loadList(false); }, reload: loadList, openDebug: openDebugModal };
  window.SipI18n?.onChange?.(() => {
    window.SipI18n?.apply?.(document.getElementById("viewCompetitorTracker"));
    renderTable();
  });
})();
