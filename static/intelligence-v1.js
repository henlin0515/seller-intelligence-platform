/**
 * Seller Intelligence V1 — dashboard, business, assortment, voucher views.
 */
(function () {
  const API = {
    dashboard: "/api/intelligence/v1/dashboard",
    business: "/api/intelligence/v1/business",
    assortment: "/api/intelligence/v1/assortment",
    voucher: "/api/intelligence/v1/voucher",
  };

  const containers = {
    siDashboard: document.getElementById("siDashboardContent"),
    siBusiness: document.getElementById("siBusinessContent"),
    siAssortment: document.getElementById("siAssortmentContent"),
    siVoucher: document.getElementById("siVoucherContent"),
  };

  const metas = {
    siDashboard: document.getElementById("siDashboardMeta"),
    siBusiness: document.getElementById("siBusinessMeta"),
    siVoucher: document.getElementById("siVoucherMeta"),
    siAssortment: document.getElementById("siAssortmentMeta"),
  };

  const cache = {};

  function fetchApi(path) {
    const fn = window.SipApi?.fetch || fetch;
    return fn(path, { credentials: "same-origin" });
  }

  function escapeHtml(text) {
    const d = document.createElement("div");
    d.textContent = String(text ?? "");
    return d.innerHTML;
  }

  function fmtNum(n, digits = 2) {
    if (n == null || Number.isNaN(n)) return "—";
    return Number(n).toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits,
    });
  }

  function fmtPct(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return `${fmtNum(n, 2)}%`;
  }

  function periodLabel(periods) {
    if (!periods?.mtd || !periods?.m1) return "";
    return `MTD ${periods.mtd.start} → ${periods.mtd.end} · M-1 ${periods.m1.start} → ${periods.m1.end}`;
  }

  async function load(path) {
    const res = await fetchApi(path);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${res.status})`);
    }
    return res.json();
  }

  function renderDashboard(data) {
    const el = containers.siDashboard;
    if (!el) return;
    const p = data.periods;
    if (metas.siDashboard) {
      metas.siDashboard.textContent = `${periodLabel(p)} · USD/PHP ${data.usd_php_rate}`;
    }
    const mods = data.modules || {};
    el.innerHTML = `
      <div class="si-v1-cards">
        <article class="si-v1-card">
          <div class="si-v1-card-label">Sellers (mock)</div>
          <div class="si-v1-card-value">${escapeHtml(String(data.seller_count ?? 0))}</div>
          <div class="si-v1-card-sub">Business Intelligence</div>
        </article>
        <article class="si-v1-card">
          <div class="si-v1-card-label">Business</div>
          <div class="si-v1-card-value"><span class="si-v1-badge">${escapeHtml(mods.business_intelligence?.status || "—")}</span></div>
        </article>
        <article class="si-v1-card">
          <div class="si-v1-card-label">Assortment</div>
          <div class="si-v1-card-value"><span class="si-v1-badge si-v1-badge--muted">${escapeHtml(mods.assortment_intelligence?.status || "—")}</span></div>
          <div class="si-v1-card-sub">Tracker: off · FastMoss: off</div>
        </article>
        <article class="si-v1-card">
          <div class="si-v1-card-label">Voucher</div>
          <div class="si-v1-card-value">${escapeHtml(mods.voucher_intelligence?.value || "N/A")}</div>
          <div class="si-v1-card-sub">${escapeHtml(mods.voucher_intelligence?.status || "placeholder")}</div>
        </article>
      </div>
      <p class="si-v1-meta">Version ${escapeHtml(data.version || "v1")} · Reference ${escapeHtml(data.reference_today || "—")}</p>`;
  }

  function renderBusiness(data) {
    const el = containers.siBusiness;
    if (!el) return;
    if (metas.siBusiness) {
      metas.siBusiness.textContent = `${periodLabel(data.periods)} · Mock data · USD/PHP ${data.usd_php_rate}`;
    }
    const rows = (data.sellers || [])
      .map(
        (s) => `
      <tr>
        <td>${escapeHtml(s.shop_name)}</td>
        <td>${escapeHtml(s.shop_id)}</td>
        <td>${fmtNum(s.shopee_mtd_adgmv_usd, 0)}</td>
        <td>${fmtNum(s.tiktok_mtd_adgmv_usd, 0)}</td>
        <td>${fmtPct(s.shopee_mom_percent)}</td>
        <td>${fmtPct(s.tiktok_mom_percent)}</td>
        <td>${fmtPct(s.mtd_shopee_sob_percent)}</td>
        <td>${fmtPct(s.mtd_tiktok_sob_percent)}</td>
        <td>${fmtPct(s.m1_shopee_sob_percent)}</td>
        <td>${fmtPct(s.m1_tiktok_sob_percent)}</td>
      </tr>`
      )
      .join("");
    el.innerHTML = `
      <div class="si-v1-table-wrap">
        <table class="si-v1-table">
          <thead>
            <tr>
              <th>Seller</th>
              <th>Shop ID</th>
              <th>Shopee MTD USD</th>
              <th>TikTok MTD USD</th>
              <th>Shopee MoM</th>
              <th>TikTok MoM</th>
              <th>MTD SOB Shopee</th>
              <th>MTD SOB TikTok</th>
              <th>M-1 SOB Shopee</th>
              <th>M-1 SOB TikTok</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function renderAssortment(data) {
    const el = containers.siAssortment;
    if (!el) return;
    if (metas.siAssortment) {
      metas.siAssortment.textContent = `Status: ${data.status || "structure_only"} · No live data`;
    }
    const rows = (data.sellers || [])
      .map(
        (s) => `
      <tr>
        <td>${escapeHtml(s.shop_name)}</td>
        <td>${escapeHtml(s.shop_id)}</td>
        <td>${escapeHtml(s.data_status)}</td>
        <td>${s.tracker_connected ? "Yes" : "No"}</td>
        <td>${s.fastmoss_connected ? "Yes" : "No"}</td>
        <td>—</td>
        <td>—</td>
        <td>—</td>
        <td>—</td>
      </tr>`
      )
      .join("");
    el.innerHTML = `
      <div class="si-v1-table-wrap">
        <table class="si-v1-table">
          <thead>
            <tr>
              <th>Seller</th>
              <th>Shop ID</th>
              <th>Data</th>
              <th>Tracker</th>
              <th>FastMoss</th>
              <th>Missing</th>
              <th>Review</th>
              <th>Price gap</th>
              <th>New listings</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function renderVoucher(data) {
    const el = containers.siVoucher;
    if (!el) return;
    if (metas.siVoucher) {
      metas.siVoucher.textContent = `Status: ${data.status || "placeholder"} · All fields N/A`;
    }
    const rows = (data.sellers || [])
      .map(
        (s) => `
      <tr>
        <td>${escapeHtml(s.shop_name)}</td>
        <td>${escapeHtml(s.shop_id)}</td>
        <td>${escapeHtml(s.active_voucher_count)}</td>
        <td>${escapeHtml(s.competitor_voucher_status)}</td>
        <td>${escapeHtml(s.last_checked_at)}</td>
        <td>${escapeHtml(s.data_source)}</td>
      </tr>`
      )
      .join("");
    el.innerHTML = `
      <div class="si-v1-table-wrap">
        <table class="si-v1-table">
          <thead>
            <tr>
              <th>Seller</th>
              <th>Shop ID</th>
              <th>Active vouchers</th>
              <th>Competitor status</th>
              <th>Last checked</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function showLoading(view) {
    const el = containers[view];
    if (el) el.innerHTML = '<p class="si-v1-loading">Loading…</p>';
  }

  function showError(view, message) {
    const el = containers[view];
    if (el) el.innerHTML = `<p class="si-v1-error">${escapeHtml(message)}</p>`;
  }

  async function onShow(view) {
    const paths = {
      siDashboard: API.dashboard,
      siBusiness: API.business,
      siAssortment: API.assortment,
      siVoucher: API.voucher,
    };
    const path = paths[view];
    if (!path) return;

    if (cache[view]) {
      if (view === "siDashboard") renderDashboard(cache[view]);
      else if (view === "siBusiness") renderBusiness(cache[view]);
      else if (view === "siAssortment") renderAssortment(cache[view]);
      else if (view === "siVoucher") renderVoucher(cache[view]);
      return;
    }

    showLoading(view);
    try {
      const data = await load(path);
      cache[view] = data;
      if (view === "siDashboard") renderDashboard(data);
      else if (view === "siBusiness") renderBusiness(data);
      else if (view === "siAssortment") renderAssortment(data);
      else if (view === "siVoucher") renderVoucher(data);
    } catch (err) {
      showError(view, err.message || "Failed to load");
    }
  }

  window.ShpIntelligenceV1 = { onShow, clearCache: () => Object.keys(cache).forEach((k) => delete cache[k]) };
})();
