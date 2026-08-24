/* Plex update check, topbar/status dots (topbar conn + arr dots +
   quicklink dots), and the clock + session uptime ticker. */
import { logLine } from "./activity-log.js";

export function buildPlexUpdateCheck() {
  const btn = document.getElementById("plex-check-updates");
  const val = document.getElementById("stat-plex-value");
  const sub = document.getElementById("stat-plex-sub");
  const check = async () => {
    btn.disabled = true;
    try {
      const res = await fetch("/api/plex/updates");
      const d = await res.json();
      if (!res.ok) throw new Error(d?.detail?.message || "Could not check Plex updates.");
      val.textContent = d.running_version || "—";
      sub.textContent = d.update_available ? `Update available: ${d.releases[0]?.version}` : "Up to date on its current channel.";
      sub.classList.toggle("stat-sub-warn", d.update_available);
      logLine(d.update_available ? "pending" : "ok", `Plex updates — ${sub.textContent}`);
    } catch (e) {
      sub.textContent = e.message;
      logLine("err", `Plex updates — ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  };
  btn.addEventListener("click", check);
  check();
}

export function setHudConn(up) {
  const dot = document.getElementById("hud-conn-dot");
  const label = document.getElementById("hud-conn-label");
  if (!dot || !label) return;
  dot.classList.remove("up", "down");
  dot.classList.add(up ? "up" : "down");
  label.textContent = up ? "connected" : "disconnected";
}

export function renderStatusDots(data) {
  for (const c of data) {
    const isUp = c.state === "running" && (c.health === "healthy" || !c.health);
    const isStarting = c.state === "running" && c.health === "starting";
    const stateClass = isUp ? "up" : isStarting ? "unknown" : "down";
    const dot = document.getElementById(`arr-dot-${c.name}`);
    if (dot) { dot.classList.remove("up", "down", "unknown"); dot.classList.add(stateClass); }
    const qdot = document.getElementById(`qdot-${c.name}`);
    if (qdot) { qdot.classList.remove("up", "down", "unknown"); qdot.classList.add(stateClass); }
  }
}

export async function refreshStatus() {
  try {
    await fetch("/api/status");
    setHudConn(true);
  } catch (_) {
    setHudConn(false);
  }
}

const sessionStart = Date.now();
export function tickClock() {
  const el = document.getElementById("clock");
  el.textContent = new Date().toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  const elapsed = Math.floor((Date.now() - sessionStart) / 1000);
  const h = String(Math.floor(elapsed / 3600)).padStart(2, "0");
  const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
  const s = String(elapsed % 60).padStart(2, "0");
  const up = document.getElementById("uptime");
  if (up) up.textContent = `up ${h}:${m}:${s}`;
}
