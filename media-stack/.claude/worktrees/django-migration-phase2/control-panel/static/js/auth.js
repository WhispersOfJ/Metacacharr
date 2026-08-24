/* Minimal login gate for the evolved backend (main.py, Phase 5 of
   .claude/plans/evolved-control-panel-backend.plan.md). app.py (the
   currently-live backend) has no auth at all, so this module is a no-op
   there - /api/auth/me 404s under app.py, which requireSession() treats
   the same as "not logged in" and just proceeds to boot the app anyway
   (see the catch block below), so this file is safe to ship before the
   Phase 5 cutover actually happens.

   Session auth relies on the browser's normal same-origin cookie
   handling - every existing fetch() call site elsewhere in this app
   already sends the httponly session cookie automatically, no changes
   needed there. This file only needs to: show a login form when there's
   no valid session, and catch a 401 on any *subsequent* request (session
   expired mid-use) by patching window.fetch once, globally. */

const overlay = document.getElementById("login-overlay");
const form = document.getElementById("login-form");
const errorEl = document.getElementById("login-error");
const logoutBtn = document.getElementById("logout-btn");

function showOverlay(message) {
  if (errorEl) errorEl.textContent = message || "";
  if (overlay) overlay.hidden = false;
  const userField = document.getElementById("login-username");
  if (userField) userField.focus();
}

function hideOverlay() {
  if (overlay) overlay.hidden = true;
}

async function submitLogin(username, password) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    let message = "Invalid username or password.";
    try {
      const data = await res.json();
      message = data?.detail || data?.message || message;
    } catch (_) { /* no body */ }
    throw new Error(message);
  }
}

/* Patches window.fetch exactly once, globally, so a session that expires
   mid-use (cookie lifetime elapses while the dashboard is open) re-shows
   the login overlay on the very next API call instead of every module
   independently having to check for a 401. Login/logout calls themselves
   are excluded so a failed login attempt doesn't recursively re-trigger
   this handler. */
function installSessionExpiryGuard() {
  const realFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const res = await realFetch(...args);
    const url = typeof args[0] === "string" ? args[0] : args[0]?.url || "";
    if (res.status === 401 && !url.startsWith("/api/auth/")) {
      showOverlay("Session expired - please log in again.");
    }
    return res;
  };
}

/* Runs before the rest of the app boots. `boot` only fires once a valid
   session is confirmed (or once the evolved backend isn't even in front
   of us yet - app.py has no /api/auth/me at all, and a 404 there means
   "nothing to gate on", not "not logged in"). */
export function requireSession(boot) {
  installSessionExpiryGuard();

  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("login-username").value;
    const password = document.getElementById("login-password").value;
    try {
      await submitLogin(username, password);
      hideOverlay();
      boot();
    } catch (err) {
      if (errorEl) errorEl.textContent = err.message;
    }
  });

  fetch("/api/auth/me")
    .then((res) => {
      if (res.status === 401) {
        showOverlay();
        return;
      }
      // 404 (app.py, no auth system at all yet) or 200 (already logged
      // in) both mean: proceed straight to booting the app.
      boot();
    })
    .catch(() => boot()); // network hiccup on this one check - don't block the whole app over it
}

export function wireLogout() {
  logoutBtn?.addEventListener("click", async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch (_) { /* best effort */ }
    window.location.reload();
  });
}
