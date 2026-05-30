/**
 * TikTok Competitor Voucher Tracker V1
 */
(function () {
  const tableBody = document.getElementById("cvtTableBody");
  const metaBar = document.getElementById("cvtMetaBar");
  const btnCheckSelected = document.getElementById("cvtCheckSelected");
  const btnCheckAll = document.getElementById("cvtCheckAll");
  const btnReload = document.getElementById("cvtReloadSheet");
  const selectAll = document.getElementById("cvtSelectAll");

  let competitors = [];

  function i18n(key, fallback = "") {
    return window.SipI18n?.t(key, fallback) ?? fallback ?? key;
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
    return Array.from(
      document.querySelectorAll(".cvt-row-check:checked")
    ).map((el) => el.value);
  }

  function renderTable() {
    if (!tableBody) return;
    if (!competitors.length) {
      tableBody.innerHTML = `<tr><td colspan="8" class="cvt-empty">${escapeHtml(
        i18n("tracker.empty", "No competitors loaded from COMPETITOR_TRACKER.")
      )}</td></tr>`;
      return;
    }

    tableBody.innerHTML = competitors
      .map((c) => {
        const status = c.voucher_status || "unchecked";
        const statusClass = `cvt-status cvt-status-${status}`;
        return `
        <tr data-shop-id="${escapeHtml(c.shop_id)}">
          <td><input type="checkbox" class="cvt-row-check" value="${escapeHtml(c.shop_id)}" aria-label="Select ${escapeHtml(c.shop_name)}" /></td>
          <td>${escapeHtml(c.shop_id)}</td>
          <td>${escapeHtml(c.shop_name)}</td>
          <td>${c.shopee_link ? `<a href="${escapeHtml(c.shopee_link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(i18n("tracker.link", "Link"))}</a>` : "—"}</td>
          <td>${c.tiktok_link ? `<a href="${escapeHtml(c.tiktok_link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(i18n("tracker.link", "Link"))}</a>` : "—"}</td>
          <td><span class="${statusClass}">${escapeHtml(statusLabel(status))}</span></td>
          <td class="cvt-voucher-text">${escapeHtml(c.voucher_text || "—")}</td>
          <td>${escapeHtml(formatTime(c.last_checked_at))}</td>
        </tr>`;
      })
      .join("");
  }

  function mergeCheckResults(results) {
    const byId = Object.fromEntries((results || []).map((r) => [r.shop_id, r]));
    competitors = competitors.map((c) => {
      const u = byId[c.shop_id];
      if (!u) return c;
      return { ...c, ...u };
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
      const res = await fetch(`/api/competitor-voucher/competitors${q}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "load failed");
      competitors = data.competitors || [];
      const meta = data.meta || {};
      if (meta.error) {
        setMeta(meta.error, true);
      } else {
        setMeta(
          i18n("tracker.metaLoaded", "{count} competitors · tab {tab}").replace(
            "{count}",
            String(competitors.length)
          ).replace("{tab}", meta.tab || "COMPETITOR_TRACKER")
        );
      }
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
    setMeta(i18n("tracker.checking", "Checking TikTok shops…"));
    try {
      const res = await fetch("/api/competitor-voucher/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shop_ids: shopIds.length ? shopIds : null }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "check failed");
      if (!data.ok && data.message) {
        setMeta(data.message, true);
        return;
      }
      mergeCheckResults(data.results);
      setMeta(
        i18n("tracker.checked", "Checked {n} shop(s).").replace("{n}", String(data.checked ?? 0))
      );
    } catch {
      setMeta(i18n("tracker.checkFailed", "Voucher check failed. Try again."), true);
    } finally {
      setBusy(false);
      markChecking([]);
    }
  }

  btnCheckSelected?.addEventListener("click", () => {
    const ids = getSelectedIds();
    runCheck(ids);
  });

  btnCheckAll?.addEventListener("click", () => {
    const ids = competitors.map((c) => c.shop_id);
    if (!ids.length) return;
    runCheck(ids);
  });

  btnReload?.addEventListener("click", () => loadList(true));

  selectAll?.addEventListener("change", () => {
    const on = selectAll.checked;
    document.querySelectorAll(".cvt-row-check").forEach((el) => {
      el.checked = on;
    });
  });

  window.ShpCompetitorTracker = {
    onShow() {
      if (!competitors.length) loadList(false);
    },
    reload: loadList,
  };

  window.SipI18n?.onChange?.(() => {
    window.SipI18n?.apply?.(document.getElementById("viewCompetitorTracker"));
    renderTable();
  });
})();
