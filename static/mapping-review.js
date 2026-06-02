(function () {
  "use strict";

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

  function reviewBadge(status) {
    const map = {
      APPROVED: ["si-v1-badge--ok", "Approved"],
      PENDING_REVIEW: ["si-v1-badge--warn", "Pending review"],
      REJECTED: ["si-v1-badge--risk", "Rejected"],
    };
    const [cls, label] = map[status] || ["si-v1-badge--muted", status || "—"];
    return `<span class="si-v1-badge ${cls}">${escapeHtml(label)}</span>`;
  }

  async function fetchApi(path, options) {
    const fn = window.SipApi?.fetch || fetch;
    return fn(path, { credentials: "same-origin", ...options });
  }

  function formatUpdated(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString();
  }

  function renderSummary(summaryEl, summary) {
    if (!summaryEl || !summary) return;
    summaryEl.innerHTML = `
      <div class="mapping-review-summary-grid">
        <div><span class="mapping-review-summary-label">${escapeHtml(i18n("mappingReview.total", "Total"))}</span><strong>${summary.total ?? 0}</strong></div>
        <div><span class="mapping-review-summary-label">${escapeHtml(i18n("mappingReview.approved", "Approved"))}</span><strong>${summary.APPROVED ?? 0}</strong></div>
        <div><span class="mapping-review-summary-label">${escapeHtml(i18n("mappingReview.pending", "Pending"))}</span><strong>${summary.PENDING_REVIEW ?? 0}</strong></div>
        <div><span class="mapping-review-summary-label">${escapeHtml(i18n("mappingReview.rejected", "Rejected"))}</span><strong>${summary.REJECTED ?? 0}</strong></div>
      </div>`;
  }

  function renderTable(tbody, rows) {
    if (!tbody) return;
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="10">${escapeHtml(i18n("mappingReview.empty", "No mapping reviews yet."))}</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map(
        (row) => `
      <tr data-shop-id="${escapeHtml(row.shop_id)}">
        <td>${escapeHtml(row.shop_id)}</td>
        <td>${escapeHtml(row.shop_name)}</td>
        <td>${escapeHtml(row.tiktok_shop_name)}</td>
        <td>${escapeHtml(row.fastmoss_shop_name || "—")}</td>
        <td class="si-v1-num">${fmtConfidence(row.confidence)}</td>
        <td>${escapeHtml(row.audit_status || "—")}</td>
        <td>${reviewBadge(row.review_status)}</td>
        <td>${escapeHtml(formatUpdated(row.updated_at || row.reviewed_at))}</td>
        <td class="mapping-review-actions">
          <button type="button" class="btn btn-sm" data-action="approve">${escapeHtml(i18n("mappingReview.approve", "Approve"))}</button>
          <button type="button" class="btn btn-sm" data-action="reject">${escapeHtml(i18n("mappingReview.reject", "Reject"))}</button>
          <button type="button" class="btn btn-sm" data-action="search">${escapeHtml(i18n("mappingReview.searchAgain", "Search Again"))}</button>
        </td>
      </tr>`
      )
      .join("");
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

      body.querySelectorAll("[data-select-candidate]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const index = Number(btn.getAttribute("data-select-candidate"));
          const candidate = candidates[index];
          if (!candidate) return;
          btn.disabled = true;
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
            window.ShpPlatform?.showPlatformToast?.(
              i18n("mappingReview.selectSuccess", "Mapping approved")
            );
            closeModal();
            await loadMappingReview();
          } catch (err) {
            window.ShpPlatform?.showPlatformToast?.(err.message || "Select failed", "error");
          } finally {
            btn.disabled = false;
          }
        });
      });
    }

    modal.classList.remove("hidden");
    modal._candidates = candidates;
    modal._shopId = shopId;
  }

  async function postDecision(shopId, action) {
    const res = await fetchApi(`/api/intelligence/v1/mapping-review/${encodeURIComponent(shopId)}/${action}`, {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `${action} failed`);
    return data;
  }

  async function loadMappingReview() {
    const summaryEl = document.getElementById("mappingReviewSummary");
    const tbody = document.getElementById("mappingReviewTableBody");
    const statusEl = document.getElementById("mappingReviewStatus");
    if (statusEl) statusEl.textContent = i18n("mappingReview.loading", "Loading…");
    try {
      const res = await fetchApi("/api/intelligence/v1/mapping-review");
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Load failed");
      renderSummary(summaryEl, data.summary);
      renderTable(tbody, data.rows || []);
      if (statusEl) statusEl.textContent = "";
    } catch (err) {
      if (statusEl) statusEl.textContent = err.message || "Load failed";
      if (tbody) tbody.innerHTML = "";
    }
  }

  function bindMappingReviewTable() {
    const tbody = document.getElementById("mappingReviewTableBody");
    if (!tbody || tbody.dataset.bound) return;
    tbody.dataset.bound = "1";
    tbody.addEventListener("click", async (event) => {
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
          await loadMappingReview();
        }
      } catch (err) {
        window.ShpPlatform?.showPlatformToast?.(err.message || "Action failed", "error");
      } finally {
        btn.disabled = false;
      }
    });
  }

  function bindModal() {
    const modal = document.getElementById("mappingReviewModal");
    if (!modal || modal.dataset.bound) return;
    modal.dataset.bound = "1";
    modal.querySelectorAll("[data-close-modal]").forEach((el) => {
      el.addEventListener("click", closeModal);
    });
  }

  function initMappingReview() {
    bindMappingReviewTable();
    bindModal();
    return loadMappingReview();
  }

  window.ShpMappingReview = {
    load: loadMappingReview,
    init: initMappingReview,
  };
})();
