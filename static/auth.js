/**
 * Login page — credentials sent only to /api/auth/login (server-side validation).
 */
(function () {
  const form = document.getElementById("loginForm");
  const errorEl = document.getElementById("loginError");
  const submitBtn = document.getElementById("loginSubmit");

  function showError(msg) {
    if (!errorEl) return;
    errorEl.textContent = msg || "Invalid username or password";
    errorEl.classList.remove("hidden");
  }

  function hideError() {
    errorEl?.classList.add("hidden");
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
        return;
      }
      window.location.replace("/");
    } catch {
      showError("Unable to sign in. Try again.");
    } finally {
      submitBtn.disabled = false;
    }
  });

  checkExistingSession();
})();
