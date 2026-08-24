/* Control Panel front end — no build step, no dependencies.
   A scrollable column of rack-module panels (Overview, Fleet, Host,
   Reference) plus a slide-out log console drawer (closed by default,
   toggled from the topbar or opened automatically when something starts
   streaming to it). The only other overlay is the command palette
   (Ctrl/Cmd+K), which is transient by design.

   This file is just the boot sequence; each rail/subsystem lives in its
   own ES module under js/, loaded natively (no bundler) since this is a
   root-mounted static site. */
import { logLine, wireLogConsole } from "./js/activity-log.js";
import { initSettings } from "./js/settings.js";
import { buildPrimaryActions } from "./js/overview.js";
import { refreshFleet } from "./js/fleet.js";
import { buildArrFleet } from "./js/arr-fleet.js";
import { buildLoopRemediation } from "./js/loop-remediation.js";
import { buildLetterboxdPanel } from "./js/letterboxd.js";
import { buildHostVitals, buildHostActions, buildHostResources, refreshHostResources } from "./js/host.js";
import { buildPosterSync } from "./js/poster-sync.js";
import { buildQuickLinks, buildDocLinks, buildSkillsList } from "./js/reference.js";
import { buildPlexUpdateCheck, refreshStatus, tickClock } from "./js/status.js";
import { wirePalette, loadCommandRegistry } from "./js/palette.js";
import { buildPlexHealth, refreshPlexHealth } from "./js/plex-health.js";
import { requireSession, wireLogout } from "./js/auth.js";

function bootApp() {
  initSettings();
  wireLogConsole();
  buildQuickLinks();
  buildPrimaryActions();
  buildArrFleet();
  buildLoopRemediation();
  buildLetterboxdPanel();
  buildHostVitals();
  buildHostActions();
  buildHostResources();
  refreshHostResources();
  setInterval(refreshHostResources, 5000);
  buildPosterSync();
  buildDocLinks();
  buildSkillsList();
  buildPlexUpdateCheck();
  wirePalette();
  loadCommandRegistry();
  tickClock();
  setInterval(tickClock, 1000);
  refreshStatus();
  setInterval(refreshStatus, 20000);
  refreshFleet();
  setInterval(refreshFleet, 15000);
  buildPlexHealth();
  refreshPlexHealth();
  setInterval(refreshPlexHealth, 15000);
  logLine("ok", "Control panel ready.");
}

wireLogout();
requireSession(bootApp);
