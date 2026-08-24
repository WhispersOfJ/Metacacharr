/* Poster sync dock — auto mode (server picks + applies) and review mode
   (server streams per-item candidates, human picks or bulk-applies the
   top match for whatever's left undecided). */
import { escapeHtml, postAction } from "./core.js";
import { logLine } from "./activity-log.js";

let activePosterSource = null;

async function loadPosterLibraries() {
  const select = document.getElementById("poster-sync-library");
  if (!select) return;
  try {
    const res = await fetch("/api/posters/libraries");
    const libs = await res.json();
    if (!Array.isArray(libs) || libs.length === 0) {
      select.innerHTML = '<option value="">No movie/show libraries found</option>';
      return;
    }
    select.innerHTML = libs.map((lib) => `<option value="${escapeHtml(lib.title)}">${escapeHtml(lib.title)} (${lib.type})</option>`).join("");
  } catch (e) {
    select.innerHTML = '<option value="">Couldn\'t load libraries</option>';
  }
}

function posterLogLine(text) {
  const pane = document.getElementById("poster-log");
  const cls = text.startsWith("OK ") ? "poster-line-ok"
    : text.startsWith("FAIL ") || text.startsWith("ERROR ") ? "poster-line-fail"
    : text.startsWith("SKIP ") ? "poster-line-skip"
    : "poster-line-info";
  const line = document.createElement("div");
  line.className = cls;
  line.textContent = text;
  pane.appendChild(line);
  pane.scrollTop = pane.scrollHeight;
}

function closePosterStream() {
  if (activePosterSource) {
    activePosterSource.close();
    activePosterSource = null;
  }
}

// Items a human has clicked a candidate for during the current review
// pass - "apply auto for the rest" skips these and uses candidate #1
// for everything else, so a manual pick is never silently overwritten.
const posterReviewDecided = new Set();

function posterCandidateCard(itemMsg, requestedSource) {
  const card = document.createElement("div");
  card.className = "poster-review-card";
  card.dataset.ratingKey = itemMsg.ratingKey;
  const label = itemMsg.year ? `${itemMsg.title} (${itemMsg.year})` : itemMsg.title;

  if (!itemMsg.candidates || itemMsg.candidates.length === 0) {
    card.innerHTML = `<div class="poster-review-title">${escapeHtml(label)}</div>
      <div class="poster-review-skip">no match in ${escapeHtml(requestedSource)} or its fallback — skipped</div>`;
    return card;
  }

  const fallbackNote = itemMsg.source && itemMsg.source !== requestedSource
    ? ` <span class="poster-review-fallback">(via ${escapeHtml(itemMsg.source)} fallback)</span>` : "";

  // Before/after: "after" (the candidate) sits on top and fades on hover
  // to reveal "before" (the item's current Plex poster) underneath - one
  // fetch of the current poster per card, shared by every candidate thumb.
  const beforeUrl = `/api/posters/thumb/${encodeURIComponent(itemMsg.ratingKey)}`;
  const thumbs = itemMsg.candidates.map((c, idx) => `
    <button type="button" class="poster-review-thumb" data-url="${escapeHtml(c.url)}" title="${escapeHtml(c.label || "")}">
      <span class="poster-compare">
        <img class="poster-compare-before" src="${beforeUrl}" loading="lazy" alt="current poster">
        <img class="poster-compare-after" src="${escapeHtml(c.url)}" loading="lazy" alt="candidate ${idx + 1}">
        <span class="poster-compare-label">hover: current</span>
      </span>
      <span class="poster-review-thumb-label">${escapeHtml(c.label || `#${idx + 1}`)}</span>
    </button>`).join("");

  card.innerHTML = `<div class="poster-review-title">${escapeHtml(label)}${fallbackNote}</div>
    <div class="poster-review-thumbs">${thumbs}</div>
    <div class="poster-review-status"></div>`;

  card.querySelectorAll(".poster-review-thumb").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const status = card.querySelector(".poster-review-status");
      card.querySelectorAll(".poster-review-thumb").forEach((b) => b.classList.remove("poster-review-picked"));
      btn.classList.add("poster-review-picked");
      status.textContent = "applying…";
      try {
        await postAction("/api/posters/apply", { rating_key: itemMsg.ratingKey, url: btn.dataset.url });
        posterReviewDecided.add(itemMsg.ratingKey);
        status.textContent = "applied";
      } catch (e) {
        status.textContent = `failed: ${e.message}`;
      }
    });
  });

  return card;
}

// ---------------------------------------------------------------------
// Gallery mode - a real image grid of a library's *current* posters (not
// a trigger dock), with pagination, a manual paste-URL override per
// card, and quality-scan flag badges once a scan has run.
// ---------------------------------------------------------------------
const POSTER_GALLERY_PAGE_SIZE = 60;
const posterGallery = { library: null, offset: 0, total: 0 };
const FLAG_LABELS = { low_res: "low-res", placeholder: "placeholder", no_poster: "no poster", language_mismatch: "language?" };

function posterGalleryCard(item) {
  const card = document.createElement("div");
  card.className = "poster-gallery-card glass-card";
  card.dataset.ratingKey = item.ratingKey;
  const label = item.year ? `${item.title} (${item.year})` : item.title;
  const thumbSrc = item.thumbUrl ? `${item.thumbUrl}?v=${Date.now()}` : "";

  card.innerHTML = `
    <div class="poster-gallery-title" title="${escapeHtml(label)}">${escapeHtml(label)}</div>
    <span class="poster-compare">
      ${thumbSrc ? `<img class="poster-compare-before" src="${escapeHtml(thumbSrc)}" loading="lazy" alt="current poster">` : ""}
      <img class="poster-compare-after" hidden alt="preview">
      <span class="poster-compare-label">hover: current</span>
    </span>
    <div class="poster-gallery-flags"></div>
    <div class="poster-gallery-override">
      <input type="url" placeholder="Paste poster URL…" class="poster-gallery-url">
      <button type="button" class="btn-ghost poster-gallery-preview">Preview</button>
      <button type="button" class="btn-primary poster-gallery-apply">Apply</button>
    </div>
    <div class="poster-gallery-status"></div>
  `;

  const urlInput = card.querySelector(".poster-gallery-url");
  const afterImg = card.querySelector(".poster-compare-after");
  const status = card.querySelector(".poster-gallery-status");

  card.querySelector(".poster-gallery-preview").addEventListener("click", () => {
    const url = urlInput.value.trim();
    if (!url) return;
    afterImg.src = url;
    afterImg.hidden = false;
  });

  card.querySelector(".poster-gallery-apply").addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) return;
    status.textContent = "applying…";
    try {
      await postAction("/api/posters/apply", { rating_key: item.ratingKey, url });
      status.textContent = "applied";
      const before = card.querySelector(".poster-compare-before");
      const refreshed = `/api/posters/thumb/${encodeURIComponent(item.ratingKey)}?v=${Date.now()}`;
      if (before) {
        before.src = refreshed;
      } else {
        const img = document.createElement("img");
        img.className = "poster-compare-before";
        img.loading = "lazy";
        img.alt = "current poster";
        img.src = refreshed;
        card.querySelector(".poster-compare").prepend(img);
      }
      afterImg.hidden = true;
      urlInput.value = "";
      logLine("ok", `Poster override — ${label}`);
    } catch (e) {
      status.textContent = `failed: ${e.message}`;
      logLine("err", `Poster override — ${label}: ${e.message}`);
    }
  });

  return card;
}

function renderPosterGalleryFlags(card, flags) {
  const wrap = card.querySelector(".poster-gallery-flags");
  if (!wrap) return;
  wrap.innerHTML = (flags || []).map((f) =>
    `<span class="lb-pill poster-flag-pill poster-flag-pill-${escapeHtml(f)}">${escapeHtml(FLAG_LABELS[f] || f)}</span>`).join("");
}

async function loadPosterGalleryPage(library, offset) {
  const grid = document.getElementById("poster-gallery-grid");
  const pageInfo = document.getElementById("poster-gallery-page-info");
  const prevBtn = document.getElementById("poster-gallery-prev");
  const nextBtn = document.getElementById("poster-gallery-next");
  grid.innerHTML = '<span class="hint">loading…</span>';
  try {
    const res = await fetch(`/api/posters/gallery?library=${encodeURIComponent(library)}&offset=${offset}&limit=${POSTER_GALLERY_PAGE_SIZE}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail?.message || data?.message || "Could not load gallery");

    posterGallery.library = library;
    posterGallery.offset = offset;
    posterGallery.total = data.total;

    grid.innerHTML = "";
    if (data.items.length === 0) {
      grid.innerHTML = '<span class="hint">No items in this library.</span>';
    } else {
      data.items.forEach((item) => grid.appendChild(posterGalleryCard(item)));
    }
    const last = Math.max(0, data.total - 1);
    const end = Math.min(offset + data.items.length, data.total);
    pageInfo.textContent = data.total ? `${offset + 1}–${end} of ${data.total}` : "0 of 0";
    prevBtn.disabled = offset <= 0;
    nextBtn.disabled = offset + POSTER_GALLERY_PAGE_SIZE > last;
  } catch (e) {
    grid.innerHTML = "";
    pageInfo.textContent = e.message;
  }
}

function buildPosterGalleryControls() {
  document.getElementById("poster-gallery-prev").addEventListener("click", () => {
    if (!posterGallery.library) return;
    loadPosterGalleryPage(posterGallery.library, Math.max(0, posterGallery.offset - POSTER_GALLERY_PAGE_SIZE));
  });
  document.getElementById("poster-gallery-next").addEventListener("click", () => {
    if (!posterGallery.library) return;
    loadPosterGalleryPage(posterGallery.library, posterGallery.offset + POSTER_GALLERY_PAGE_SIZE);
  });

  document.getElementById("poster-gallery-scan").addEventListener("click", async (ev) => {
    if (!posterGallery.library) return;
    const btn = ev.currentTarget;
    const summary = document.getElementById("poster-gallery-scan-summary");
    btn.disabled = true;
    summary.textContent = "scanning…";
    closePosterStream();
    try {
      await postAction("/api/posters/scan", { library: posterGallery.library });
      activePosterSource = new EventSource("/api/posters/scan/stream");
      activePosterSource.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.type === "start") {
          summary.textContent = `scanning ${msg.total} item(s)…`;
        } else if (msg.type === "item") {
          summary.textContent = `scanning… ${msg.i}/${msg.total}`;
          const card = document.querySelector(`.poster-gallery-card[data-rating-key="${msg.ratingKey}"]`);
          if (card && msg.flags) renderPosterGalleryFlags(card, msg.flags);
        } else if (msg.type === "error") {
          summary.textContent = msg.message;
          logLine("err", `Poster quality scan — ${msg.message}`);
          closePosterStream();
          btn.disabled = false;
        } else if (msg.type === "done") {
          summary.textContent = `${msg.flagged} of ${msg.total} flagged`;
          logLine("ok", `Poster quality scan — ${msg.flagged} of ${msg.total} flagged`);
          closePosterStream();
          btn.disabled = false;
        }
      };
      activePosterSource.onerror = () => {
        closePosterStream();
        btn.disabled = false;
      };
    } catch (e) {
      summary.textContent = e.message;
      logLine("err", `Poster quality scan — ${e.message}`);
      btn.disabled = false;
    }
  });
}

export function buildPosterSync() {
  const form = document.getElementById("poster-sync-form");
  if (!form) return;
  const summary = document.getElementById("poster-sync-summary");
  const submitBtn = form.querySelector("button[type=submit]");
  const modeSelect = document.getElementById("poster-sync-mode");
  const dryRunWrap = document.getElementById("poster-sync-dry-run-wrap");
  const logPane = document.getElementById("poster-log");
  const grid = document.getElementById("poster-review-grid");
  const gallery = document.getElementById("poster-gallery");

  buildPosterGalleryControls();

  modeSelect.addEventListener("change", () => {
    dryRunWrap.hidden = modeSelect.value !== "auto";
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const library = document.getElementById("poster-sync-library").value;
    if (!library) return;
    const source = document.getElementById("poster-sync-source").value;
    const mode = modeSelect.value;

    logPane.textContent = "";
    logPane.hidden = mode !== "auto";
    grid.innerHTML = "";
    grid.hidden = mode !== "review";
    gallery.hidden = mode !== "gallery";
    summary.textContent = "";
    submitBtn.disabled = true;
    closePosterStream();
    posterReviewDecided.clear();

    if (mode === "gallery") {
      submitBtn.disabled = false;
      document.getElementById("poster-gallery-scan-summary").textContent = "";
      await loadPosterGalleryPage(library, 0);
      return;
    }

    if (mode === "auto") {
      const dryRun = document.getElementById("poster-sync-dry-run").checked;
      try {
        const data = await postAction("/api/posters/sync", { library, dry_run: dryRun, source });
        logLine("pending", data.message);
        summary.textContent = "running…";

        activePosterSource = new EventSource("/api/posters/sync/stream");
        activePosterSource.onmessage = (evt) => {
          posterLogLine(evt.data);
          if (evt.data.startsWith("DONE ")) {
            summary.textContent = evt.data.slice(5);
            logLine("ok", `Poster sync — ${evt.data.slice(5)}`);
            closePosterStream();
            submitBtn.disabled = false;
          } else if (evt.data.startsWith("ERROR ")) {
            summary.textContent = evt.data.slice(6);
            logLine("err", `Poster sync — ${evt.data.slice(6)}`);
            closePosterStream();
            submitBtn.disabled = false;
          }
        };
        activePosterSource.onerror = () => {
          closePosterStream();
          submitBtn.disabled = false;
        };
      } catch (e) {
        summary.textContent = e.message;
        logLine("err", `Poster sync — ${e.message}`);
        submitBtn.disabled = false;
      }
      return;
    }

    // Review mode: stream per-item candidates, render a picker grid.
    // Items nobody clicks stay unapplied until "Apply auto for the rest".
    const pending = [];
    try {
      const data = await postAction("/api/posters/review", { library, source });
      logLine("pending", data.message);
      summary.innerHTML = 'streaming candidates… <button type="button" class="btn-ghost" id="poster-apply-auto-rest">Apply auto for the rest</button>';
      document.getElementById("poster-apply-auto-rest").addEventListener("click", async (e) => {
        e.target.disabled = true;
        e.target.textContent = "applying…";
        for (const item of pending) {
          if (posterReviewDecided.has(item.ratingKey) || !item.candidates.length) continue;
          const card = grid.querySelector(`[data-rating-key="${item.ratingKey}"]`);
          const status = card?.querySelector(".poster-review-status");
          try {
            await postAction("/api/posters/apply", { rating_key: item.ratingKey, url: item.candidates[0].url });
            posterReviewDecided.add(item.ratingKey);
            if (status) status.textContent = "applied (auto)";
            card?.querySelector(".poster-review-thumb")?.classList.add("poster-review-picked");
          } catch (err) {
            if (status) status.textContent = `failed: ${err.message}`;
          }
        }
        e.target.textContent = "Done";
      });

      activePosterSource = new EventSource("/api/posters/review/stream");
      activePosterSource.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.type === "item") {
          pending.push(msg);
          grid.appendChild(posterCandidateCard(msg, source));
        } else if (msg.type === "error") {
          logLine("err", `Poster review — ${msg.message}`);
          closePosterStream();
          submitBtn.disabled = false;
        } else if (msg.type === "done") {
          logLine("ok", `Poster review — ${pending.length} item(s) loaded, pick a poster or apply auto for the rest.`);
          closePosterStream();
          submitBtn.disabled = false;
        }
      };
      activePosterSource.onerror = () => {
        closePosterStream();
        submitBtn.disabled = false;
      };
    } catch (e) {
      summary.textContent = e.message;
      logLine("err", `Poster review — ${e.message}`);
      submitBtn.disabled = false;
    }
  });

  loadPosterLibraries();
}
