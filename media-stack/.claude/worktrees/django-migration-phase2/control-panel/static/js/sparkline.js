/* Shared inline-SVG sparkline renderer. Single implementation used by
   Host, Plex Health, and Fleet — do not fork a per-rail copy; add
   options here instead (see the `min`/`max` clamp, added for Plex
   Health's non-0-100 busy-DB-error counts). */

export function pushHistory(buffer, value, maxLen) {
  buffer.push(value);
  if (buffer.length > maxLen) buffer.shift();
  return buffer;
}

export function renderSparkline(svgEl, samples, { min = 0, max = 100, stroke = "var(--accent)", fill = false } = {}) {
  if (!svgEl) return;
  if (!samples.length) {
    svgEl.innerHTML = "";
    return;
  }
  const w = 200, h = 40;
  const range = Math.max(max - min, 1);
  const points = samples.map((v, i) => {
    const x = samples.length === 1 ? w : (i / (samples.length - 1)) * w;
    const y = h - ((Math.min(Math.max(v, min), max) - min) / range) * h;
    return [x, y];
  });
  const pointsAttr = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const fillEl = fill
    ? `<polygon points="0,${h} ${pointsAttr} ${w},${h}" fill="${stroke}" opacity="0.14" />`
    : "";
  svgEl.innerHTML = `${fillEl}<polyline points="${pointsAttr}" fill="none" stroke="${stroke}" stroke-width="1.5" />`;
}
