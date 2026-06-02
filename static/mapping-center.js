(function () {
  "use strict";

  const STATUS_PENDING = "PENDING_REVIEW";
  const STATUS_APPROVED = "APPROVED";
  const STATUS_REJECTED = "REJECTED";

  const state = {
    rows: [],
    summary: {},
    filters: { q: "", status: "all", confidenceMin: "" },
    loading: false,
    error: null,
    bound: false,
  };

  function i18n(key, fallback) {
    return window.SipI18n?.t?.(key, fallback) ?? fallback ?? key;
  }

  function escapeHtml(text) {
    const d = document.createElement("div");
    d.textContent = String(text ?? "");
    return d.innerHTML;
  }

  function fmtConfidence(value) {
    if (value == null || Number.isNaN(value)) return "—";
    return `${(Number(value) * 100).toFixed(1)}%`;
  }

  function fmtPct(value) {
    if (value == null || Number.isNaN(value)) return "—";
    return `${Number(value).toFixed(1)}%`;
  }

  function reviewBadge(status) {
    const map = {
      APPROVED: ["si-v1-badge--ok", "Approved"],
      PENDING_REVIEW: ["si-v1-badge--warn", "Pending review"],
      REJECTED: ["si-v1-badge--risk", "Rejected"],
    };
    const [cls, label] = map[status] || ["si-v1-badge--muted", status || "—"];
    return `<span class="si-v1-badge ${cls}">${escapeHtml(label)}</span>`;
  }

  function formatUpdated(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString();
  }

  async function fetchApi(path, options) {
    const fn = window.SipApi?.fetch || fetch;
    return fn(path, { credentials: "same-origin", ...options });
  }

  function rootEl() {
    return document.getElementById("siMappingContent");
  }

  function metaEl() {
    return document.getElementById("siMappingMeta");
  }

  function approvalRate(summary) {
    const total = Number(summary?.total) || 0;
    const approved = Number(summary?.APPROVED) || 0;
    if (!total) return null;
    return (approved / total) * 100;
  }

  function filterRows(rows) {
    const q = state.filters.q.trim().toLowerCase();
    const status = state.filters.status;
    const confMin = state.filters.confidenceMin === "" ? null : Number(state.filters.confidenceMin);

    return rows.filter((row) => {
      if (status !== "all" && String(row.review_status || "") !== status) return false;
      if (confMin != null && !Number.isNaN(confMin)) {
        const conf = Number(row.confidence);
        if (Number.isNaN(conf) || conf < confMin) return false;
      }
      if (!q) return true;
      const blob = [row.shop_id, row.shop_name, row.tiktok_shop_name, row.fastmoss_shop_name]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return blob.includes(q);
    });
  }

  function renderKpiCards(summary) {
    const rate = approvalRate(summary);
    return `
      <div class="mc-kpi-grid">
        <article class="si-port-kpi mc-kpi">
          <div class="si-port-kpi-label">${escapeHtml(i18n("mappingCenter.kpiTotal", "Total Mappings"))}</div>
          <div class="si-port-kpi-value">${summary.total ?? 0}</div>
        </article>
        <article class="si-port-kpi mc-kpi mc-kpi--ok">
          <div class="si-port-kpi-label">${escapeHtml(i18n("mappingCenter.kpiApproved", "Approved"))}</div>
          <div class="si-port-kpi-value">${summary.APPROVED ?? 0}</div>
        </article>
        <article class="si-port-kpi mc-kpi mc-kpi--warn">
          <div class="si-port-kpi-label">${escapeHtml(i18n("mappingCenter.kpiPending", "Pending Review"))}</div>
          <div class="si-port-kpi-value">${summary.PENDING_REVIEW ?? 0}</div>
        </article>
        <article class="si-port-kpi mc-kpi mc-kpi--risk">
          <div class="si-port-kpi-label">${escapeHtml(i18n("mappingCenter.kpiRejected", "Rejected"))}</div>
          <div class="si-port-kpi-value">${summary.REJECTED ?? 0}</div>
        </article>
        <article class="si-port-kpi mc-kpi mc-kpi--accent">
          <div class="si-port-kpi-label">${escapeHtml(i18n("mappingCenter.kpiApprovalRate", "Approval Rate"))}</div>
          <div class="si-port-kpi-value">${rate == null ? "—" : fmtPct(rate)}</div>
        </article>
      </div>`;
  }

  function renderToolbar() {
    const f = state.filters;
    return `
      <div class="mc-toolbar" data-mc-toolbar>
        <div class="mc-toolbar-field mc-toolbar-field--search">
          <label for="mcSearch">${escapeHtml(i18n("mappingCenter.filterSearch", "Search"))}</label>
          <input id="mcSearch" type="search" data-mc-filter="q" placeholder="${escapeHtml(i18n("mappingCenter.filterSearchPh", "Shop ID, Shopee, TikTok…"))}" value="${escapeHtml(f.q)}" />
        </div>
        <div class="mc-toolbar-field">
          <label for="mcStatus">${escapeHtml(i18n("mappingCenter.filterStatus", "Status"))}</label>
          <select id="mcStatus" data-mc-filter="status">
            <option value="all"${f.status === "all" ? " selected" : ""}>${escapeHtml(i18n("mappingCenter.statusAll", "All"))}</option>
            <option value="${STATUS_PENDING}"${f.status === STATUS_PENDING ? " selected" : ""}>${escapeHtml(i18n("mappingCenter.statusPending", "Pending Review"))}</option>
            <option value="${STATUS_APPROVED}"${f.status === STATUS_APPROVED ? " selected" : ""}>${escapeHtml(i18n("mappingCenter.statusApproved", "Approved"))}</option>
            <option value="${STATUS_REJECTED}"${f.status === STATUS_REJECTED ? " selected" : ""}>${escapeHtml(i18n("mappingCenter.statusRejected", "Rejected"))}</option>
          </select>
        </div>
        <div class="mc-toolbar-field">
          <label for="mcConfidence">${escapeHtml(i18n("mappingCenter.filterConfidence", "Min Confidence"))}</label>
          <select id="mcConfidence" data-mc-filter="confidenceMin">
            <option value=""${f.confidenceMin === "" ? " selected" : ""}>${escapeHtml(i18n("mappingCenter.confidenceAny", "Any"))}</option>
            <option value="0.7"${f.confidenceMin === "0.7" ? " selected" : ""}>≥ 70%</option>
            <option value="0.85"${f.confidenceMin === "0.85" ? " selected" : ""}>≥ 85%</option>
            <option value="0.95"${f.confidenceMin === "0.95" ? " selected" : ""}>≥ 95%</option>
          </select>
        </div>
        <button type="button" class="si-v1-btn-reset" data-mc-reset>${escapeHtml(i18n("mappingCenter.resetFilters", "Reset filters"))}</button>
        <p class="mc-result-count" data-mc-count></p>
      </div>`;
  }

  function renderTableRows(rows, { showActions = true, emptyMessage }) {
    if (!rows.length) {
      return `<p class="si-v1-empty">${escapeHtml(emptyMessage)}</p>`;
    }
    const actionCol = showActions
      ? `<th>${escapeHtml(i18n("mappingReview.colActions", "Actions"))}</th>`
      : "";
    const body = rows
      .map((row) => {
        const actions = showActions
          ? `<td class="mapping-review-actions">
              <button type="button" class="btn btn-sm" data-action="approve">${escapeHtml(i18n("mappingReview.approve", "Approve"))}</button>
              <button type="button" class="btn btn-sm" data-action="reject">${escapeHtml(i18n("mappingReview.reject", "Reject"))}</button>
              <button type="button" class="btn btn-sm" data-action="search">${escapeHtml(i18n("mappingReview.searchAgain", "Search Again"))}</button>
            </td>`
          : "";
        return `
          <tr data-shop-id="${escapeHtml(row.shop_id)}">
            <td>${escapeHtml(row.shop_id)}</td>
            <td>${escapeHtml(row.shop_name)}</td>
            <td>${escapeHtml(row.tiktok_shop_name)}</td>
            <td>${escapeHtml(row.fastmoss_shop_name || "—")}</td>
            <td class="si-v1-num">${fmtConfidence(row.confidence)}</td>
            <td>${escapeHtml(row.audit_status || "—")}</td>
            <td>${reviewBadge(row.review_status)}</td>
            <td>${escapeHtml(formatUpdated(row.updated_at || row.reviewed_at))}</td>
            ${actions}
          </tr>`;
      })
      .join("");
    return `
      <div class="mapping-review-table-wrap">
        <table class="mapping-review-table mc-table">
          <thead>
            <tr>
              <th>${escapeHtml(i18n("mappingReview.colShopId", "Shop ID"))}</th>
              <th>${escapeHtml(i18n("mappingReview.colShopee", "Shopee Shop Name"))}</th>
              <th>${escapeHtml(i18n("mappingReview.colTiktok", "TikTok Shop Name"))}</th>
              <th>${escapeHtml(i18n("mappingReview.colFastmoss", "FastMoss Matched Shop"))}</th>
              <th>${escapeHtml(i18n("mappingReview.colConfidence", "Confidence"))}</th>
              <th>${escapeHtml(i18n("mappingReview.colAudit", "Audit Status"))}</th>
              <th>${escapeHtml(i18n("mappingReview.colReview", "Review Status"))}</th>
              <th>${escapeHtml(i18n("mappingReview.colUpdated", "Last Updated"))}</th>
              ${actionCol}
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function renderSection(title, rows, options) {
    return `
      <section class="mc-section">
        <div class="mc-section-head">
          <h2 class="mc-section-title">${escapeHtml(title)}</h2>
          <span class="mc-section-count">${rows.length}</span>
        </div>
        ${renderTableRows(rows, options)}
      </section>`;
  }

  function paint() {
    const el = rootEl();
    if (!el) return;

    if (state.loading) {
      el.innerHTML = `<div class="mc-state mc-state--loading"><div class="si-port-state-spinner"></div><p>${escapeHtml(i18n("mappingReview.loading", "Loading…"))}</p></div>`;
      if (metaEl()) metaEl().textContent = i18n("mappingReview.loading", "Loading…");
      return;
    }

    if (state.error) {
      el.innerHTML = `
        <div class="mc-state mc-state--error" role="alert">
          <p class="mc-state-title">${escapeHtml(i18n("mappingCenter.loadError", "Could not load Mapping Center"))}</p>
          <p>${escapeHtml(state.error)}</p>
          <button type="button" class="btn si-v1-action-btn" data-mc-retry>${escapeHtml(i18n("si.dashboardRetry", "Retry"))}</button>
        </div>`;
      if (metaEl()) metaEl().textContent = i18n("mappingCenter.loadErrorMeta", "Load failed");
      return;
    }

    const filtered = filterRows(state.rows);
    const pending = filtered.filter((r) => r.review_status === STATUS_PENDING);
    const approved = filtered.filter((r) => r.review_status === STATUS_APPROVED);
    const rejected = filtered.filter((r) => r.review_status === STATUS_REJECTED);

    if (metaEl()) {
      metaEl().textContent = i18n(
        "mappingCenter.meta",
        "{total} mappings · {approved} approved · {pending} pending"
      )
        .replace("{total}", String(state.summary.total ?? 0))
        .replace("{approved}", String(state.summary.APPROVED ?? 0))
        .replace("{pending}", String(state.summary.PENDING_REVIEW ?? 0));
    }

    el.innerHTML = `
      <div class="mc-page" data-mc-page>
        ${renderKpiCards(state.summary)}
        ${renderToolbar()}
        ${renderSection(i18n("mappingCenter.sectionPending", "Pending Review Queue"), pending, {
          showActions: true,
          emptyMessage: i18n("mappingCenter.emptyPending", "No pending mappings match your filters."),
        })}
        ${renderSection(i18n("mappingCenter.sectionApproved", "Approved Mappings"), approved, {
          showActions: true,
          emptyMessage: i18n("mappingCenter.emptyApproved", "No approved mappings match your filters."),
        })}
        ${renderSection(i18n("mappingCenter.sectionRejected", "Rejected Mappings"), rejected, {
          showActions: true,
          emptyMessage: i18n("mappingCenter.emptyRejected", "No rejected mappings match your filters."),
        })}
      </div>`;

    const countEl = el.querySelector("[data-mc-count]");
    if (countEl) {
      countEl.textContent = i18n("mappingCenter.resultCount", "{n} rows shown").replace(
        "{n}",
        String(filtered.length)
      );
    }
  }

  function bindPageEvents() {
    const el = rootEl();
    if (!el || state.bound) return;
    state.bound = true;

    el.addEventListener("input", (event) => {
      const node = event.target.closest("[data-mc-filter]");
      if (!node) return;
      state.filters[node.dataset.mcFilter] = node.value;
      paint();
    });

    el.addEventListener("change", (event) => {
      const node = event.target.closest("[data-mc-filter]");
      if (!node) return;
      state.filters[node.dataset.mcFilter] = node.value;
      paint();
    });

    el.addEventListener("click", async (event) => {
      if (event.target.closest("[data-mc-reset]")) {
        state.filters = { q: "", status: "all", confidenceMin: "" };
        paint();
        return;
      }
      if (event.target.closest("[data-mc-retry]")) {
        await loadMappingCenter();
        return;
      }

      const btn = event.target.closest("[data-action]");
      if (!btn) return;
      const row = btn.closest("tr[data-shop-id]");
      if (!row) return;
      const shopId = row.getAttribute("data-shop-id");
      const action = btn.getAttribute("data-action");
      btn.disabled = true;
      try {
        if (action === "search") {
          const res = await fetchApi(`/api/intelligence/v1/mapping-review/${encodeURIComponent(shopId)}/search`);
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail || "Search failed");
          showCandidatesModal(shopId, data);
        } else if (action === "approve" || action === "reject") {
          await postDecision(shopId, action);
          window.ShpPlatform?.showPlatformToast?.(
            i18n(
              action === "approve" ? "mappingReview.approveSuccess" : "mappingReview.rejectSuccess",
              action === "approve" ? "Mapping approved" : "Mapping rejected"
            )
          );
          await loadMappingCenter();
        }
      } catch (err) {
        window.ShpPlatform?.showPlatformToast?.(err.message || "Action failed", "error");
      } finally {
        btn.disabled = false;
      }
    });
  }

  function closeModal() {
    document.getElementById("mappingReviewModal")?.classList.add("hidden");
  }

  function showCandidatesModal(shopId, payload) {
    const modal = document.getElementById("mappingReviewModal");
    const title = document.getElementById("mappingReviewModalTitle");
    const body = document.getElementById("mappingReviewModalBody");
    if (!modal || !body) return;

    const candidates = payload.candidates || [];
    if (title) {
      title.textContent = i18n("mappingReview.searchTitle", "Select FastMoss match for {name}").replace(
        "{name}",
        payload.tiktok_shop_name || shopId
      );
    }

    if (!candidates.length) {
      body.innerHTML = `<p>${escapeHtml(i18n("mappingReview.noCandidates", "No candidates found."))}</p>`;
    } else {
      body.innerHTML = `
        <div class="mapping-review-candidates">
          ${candidates
            .map(
              (c, index) => `
            <div class="mapping-review-candidate" data-index="${index}">
              <div class="mapping-review-candidate-head">
                <strong>${escapeHtml(c.fastmoss_shop_name)}</strong>
                <span>${escapeHtml(i18n("mappingReview.confidence", "Confidence"))}: ${fmtConfidence(c.confidence)}</span>
              </div>
              <dl class="mapping-review-candidate-meta">
                <div><dt>${escapeHtml(i18n("mappingReview.company", "Seller Company"))}</dt><dd>${escapeHtml(c.seller_company || "—")}</dd></div>
                <div><dt>${escapeHtml(i18n("mappingReview.category", "Category"))}</dt><dd>${escapeHtml(c.category || "—")}</dd></div>
                <div><dt>${escapeHtml(i18n("mappingReview.totalSales", "Total Sales"))}</dt><dd>${escapeHtml(c.total_sales ?? "—")}</dd></div>
                <div><dt>${escapeHtml(i18n("mappingReview.totalSold", "Total Sold"))}</dt><dd>${escapeHtml(c.total_sold ?? "—")}</dd></div>
                <div><dt>${escapeHtml(i18n("mappingReview.region", "Region"))}</dt><dd>${escapeHtml(c.region || "—")}</dd></div>
              </dl>
              <button type="button" class="btn btn-primary btn-sm" data-select-candidate="${index}">
                ${escapeHtml(i18n("mappingReview.selectApprove", "Select & Approve"))}
              </button>
            </div>`
            )
            .join("")}
        </div>`;

      body.querySelectorAll("[data-select-candidate]").forEach((selectBtn) => {
        selectBtn.addEventListener("click", async () => {
          const index = Number(selectBtn.getAttribute("data-select-candidate"));
          const candidate = candidates[index];
          if (!candidate) return;
          selectBtn.disabled = true;
          try {
            const params = new URLSearchParams({
              fastmoss_shop_id: candidate.fastmoss_shop_id,
              fastmoss_shop_name: candidate.fastmoss_shop_name,
            });
            if (candidate.fastmoss_shop_url) params.set("fastmoss_shop_url", candidate.fastmoss_shop_url);
            if (candidate.confidence != null) params.set("confidence", String(candidate.confidence));
            const res = await fetchApi(
              `/api/intelligence/v1/mapping-review/${encodeURIComponent(shopId)}/select?${params}`,
              { method: "POST" }
            );
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Select failed");
            window.ShpPlatform?.showPlatformToast?.(i18n("mappingReview.selectSuccess", "Mapping approved"));
            closeModal();
            await loadMappingCenter();
          } catch (err) {
            window.ShpPlatform?.showPlatformToast?.(err.message || "Select failed", "error");
          } finally {
            selectBtn.disabled = false;
          }
        });
      });
    }

    modal.classList.remove("hidden");
  }

  async function postDecision(shopId, action) {
    const res = await fetchApi(`/api/intelligence/v1/mapping-review/${encodeURIComponent(shopId)}/${action}`, {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `${action} failed`);
    return data;
  }

  function bindModal() {
    const modal = document.getElementById("mappingReviewModal");
    if (!modal || modal.dataset.bound) return;
    modal.dataset.bound = "1";
    modal.querySelectorAll("[data-close-modal]").forEach((node) => {
      node.addEventListener("click", closeModal);
    });
  }

  async function loadMappingCenter() {
    state.loading = true;
    state.error = null;
    paint();
    try {
      const res = await fetchApi("/api/intelligence/v1/mapping-review");
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Load failed");
      state.rows = data.rows || [];
      state.summary = data.summary || {};
      state.loading = false;
      paint();
    } catch (err) {
      state.loading = false;
      state.error = err.message || "Load failed";
      paint();
    }
  }

  function initMappingCenter() {
    bindModal();
    bindPageEvents();
    return loadMappingCenter();
  }

  window.ShpMappingCenter = {
    init: initMappingCenter,
    load: loadMappingCenter,
  };

  window.ShpMappingReview = window.ShpMappingCenter;
})();
