/**
 * Login page — credentials sent only to /api/auth/login (server-side validation).
 */
(function () {
  const form = document.getElementById("loginForm");
  const errorEl = document.getElementById("loginError");
  const submitBtn = document.getElementById("loginSubmit");
  const loginCard = document.querySelector(".login-card");
  const warpEl = document.getElementById("loginWarp");
  const warpStatus = document.getElementById("warpStatus");

  const WARP_DURATION_MS = 1800;
  const WARP_LINES = [
    { at: 0, text: "Access Granted" },
    { at: 550, text: "Initializing Seller Intelligence" },
    { at: 1100, text: "Entering Dashboard" },
  ];

  function showError(msg) {
    if (!errorEl) return;
    errorEl.textContent = msg || "Invalid username or password";
    errorEl.classList.remove("hidden");
  }

  function hideError() {
    errorEl?.classList.add("hidden");
  }

  function playWarpTransition() {
    return new Promise((resolve) => {
      if (!warpEl || !warpStatus) {
        resolve();
        return;
      }

      loginCard?.classList.add("login-card--exit");
      warpEl.classList.remove("hidden");
      warpEl.setAttribute("aria-hidden", "false");
      document.body.classList.add("login-warp-active");

      WARP_LINES.forEach(({ at, text }) => {
        setTimeout(() => {
          warpStatus.textContent = text;
          warpStatus.classList.remove("warp-status--flash");
          void warpStatus.offsetWidth;
          warpStatus.classList.add("warp-status--flash");
        }, at);
      });

      setTimeout(resolve, WARP_DURATION_MS);
    });
  }

  async function checkExistingSession() {
    try {
      const res = await fetch("/api/auth/me", { credentials: "same-origin" });
      if (!res.ok) return;
      const data = await res.json();
      if (data.authenticated) {
        window.location.replace("/");
      }
    } catch {
      /* ignore */
    }
  }

  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideError();
    submitBtn.disabled = true;
    const username = document.getElementById("username")?.value?.trim() || "";
    const password = document.getElementById("password")?.value || "";
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showError(data.detail || "Invalid username or password");
        submitBtn.disabled = false;
        return;
      }
      await playWarpTransition();
      window.location.replace("/");
    } catch {
      showError("Unable to sign in. Try again.");
      submitBtn.disabled = false;
    }
  });

  checkExistingSession();
})();
