/* Persisted-settings wiring: theme (amber/green Pip-Boy palette,
   server-side via /api/settings) and the log console drawer (client-only
   UI state, localStorage - no server round-trip needed for something
   this ephemeral). */

async function patchSettings(body) {
  const res = await fetch("/api/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const input = document.getElementById("theme-switch");
  if (input) input.checked = theme === "green";
  const label = input?.closest(".switch")?.querySelector(".switch-label");
  if (label) label.textContent = theme === "green" ? "Green" : "Amber";
}

export function openConsole() {
  const drawer = document.getElementById("col-log");
  drawer.classList.add("open");
  localStorage.setItem("consoleOpen", "1");
}

export async function initSettings() {
  let settings = { theme: "amber" };
  try {
    const res = await fetch("/api/settings");
    settings = await res.json();
  } catch (_) { /* fall back to default theme */ }
  applyTheme(settings.theme);

  document.getElementById("theme-switch").addEventListener("change", async (e) => {
    const theme = e.target.checked ? "green" : "amber";
    applyTheme(theme);
    await patchSettings({ theme });
  });

  const drawer = document.getElementById("col-log");
  const toggleBtn = document.getElementById("console-toggle");
  const closeBtn = document.getElementById("log-close");
  const setOpen = (open) => {
    drawer.classList.toggle("open", open);
    localStorage.setItem("consoleOpen", open ? "1" : "0");
  };
  toggleBtn.addEventListener("click", () => setOpen(!drawer.classList.contains("open")));
  closeBtn.addEventListener("click", () => setOpen(false));
  setOpen(localStorage.getItem("consoleOpen") === "1");
}
