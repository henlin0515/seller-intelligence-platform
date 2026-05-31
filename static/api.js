/**
 * Authenticated fetch wrapper — always sends session cookie; redirects on 401.
 */
(function () {
  async function apiFetch(url, options = {}) {
    const opts = {
      credentials: "same-origin",
      ...options,
      headers: {
        ...(options.headers || {}),
      },
    };
    const res = await fetch(url, opts);
    if (res.status === 401) {
      window.location.replace("/login");
      throw new Error("Authentication required");
    }
    return res;
  }

  window.SipApi = { fetch: apiFetch };
})();
