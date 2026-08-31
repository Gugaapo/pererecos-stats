/**
 * Shared visual helpers for overview / podium / distribution bars.
 * Pure DOM builders — no chart library.
 */

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function fmtNum(n, digits = 0) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/**
 * @param {Array<{label: string, value: string|number, hint?: string}>} items
 * @returns {HTMLElement}
 */
export function renderKpiStrip(items) {
  const wrap = document.createElement('div');
  wrap.className = 'kpi-strip';
  (items || []).forEach((item) => {
    const el = document.createElement('div');
    el.className = 'kpi-callout';
    if (item.hint) el.title = item.hint;
    el.innerHTML =
      `<div class="kpi-value">${esc(item.value)}</div>` +
      `<div class="kpi-label">${esc(item.label)}</div>`;
    wrap.appendChild(el);
  });
  return wrap;
}

/**
 * @param {Array<{label: string, count: number}>} buckets
 * @param {{maxHeight?: number}} [opts]
 * @returns {HTMLElement}
 */
export function renderDistBars(buckets, opts = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'dist-bars';
  const list = buckets || [];
  const max = Math.max(1, ...list.map((b) => Number(b.count) || 0));
  list.forEach((b) => {
    const col = document.createElement('div');
    col.className = 'dist-bar-col';
    const count = Number(b.count) || 0;
    const pct = Math.round((count / max) * 100);
    col.innerHTML =
      `<div class="dist-bar-track"><div class="dist-bar-fill" style="height:${pct}%"></div></div>` +
      `<div class="dist-bar-count">${fmtNum(count)}</div>` +
      `<div class="dist-bar-label">${esc(b.label || b.bucket || '')}</div>`;
    col.title = `${b.label || b.bucket}: ${fmtNum(count)}`;
    wrap.appendChild(col);
  });
  if (!list.length) {
    wrap.innerHTML = '<div class="empty-state">Sem dados</div>';
  }
  return wrap;
}

/**
 * Horizontal proportional bars.
 * @param {Array<{label: string, value: number, sub?: string, onClick?: function}>} rows
 * @param {{maxRows?: number}} [opts]
 * @returns {HTMLElement}
 */
export function renderMiniBars(rows, opts = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'mini-bars';
  const list = (rows || []).slice(0, opts.maxRows != null ? opts.maxRows : 8);
  const max = Math.max(1, ...list.map((r) => Number(r.value) || 0));
  if (!list.length) {
    wrap.innerHTML = '<div class="empty-state">Sem dados</div>';
    return wrap;
  }
  list.forEach((r, i) => {
    const row = document.createElement(r.onClick ? 'button' : 'div');
    if (r.onClick) {
      row.type = 'button';
      row.addEventListener('click', r.onClick);
    }
    row.className = 'mini-bar-row';
    const val = Number(r.value) || 0;
    const pct = Math.max(2, Math.round((val / max) * 100));
    row.innerHTML =
      `<span class="mini-bar-rank">#${i + 1}</span>` +
      `<span class="mini-bar-label">${esc(r.label)}</span>` +
      `<span class="mini-bar-track"><span class="mini-bar-fill" style="width:${pct}%"></span></span>` +
      `<span class="mini-bar-value">${esc(r.sub || fmtNum(val))}</span>`;
    wrap.appendChild(row);
  });
  return wrap;
}

/**
 * Top-3 podium with relative bar widths.
 * @param {Array<object>} entries
 * @param {{
 *   valueKey?: string,
 *   formatValue?: (entry, value) => string,
 *   onSelect?: (entry) => void,
 *   nameKey?: string,
 * }} [opts]
 * @returns {HTMLElement}
 */
export function renderPodium(entries, opts = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'podium';
  const list = (entries || []).slice(0, 3);
  if (!list.length) {
    wrap.innerHTML = '<div class="empty-state">Sem dados</div>';
    return wrap;
  }
  const valueKey = opts.valueKey || 'count';
  const values = list.map((e) => {
    const v = e[valueKey] != null ? e[valueKey] : e.value;
    return Number(v) || 0;
  });
  const max = Math.max(1, ...values);

  list.forEach((entry, i) => {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'podium-row podium-place-' + (i + 1);
    const name = entry.display_name || entry.username || entry.emote_name || entry.command || '—';
    const val = values[i];
    const pct = Math.max(8, Math.round((val / max) * 100));
    const formatted = opts.formatValue
      ? opts.formatValue(entry, val)
      : fmtNum(val);
    row.innerHTML =
      `<span class="podium-rank">#${entry.rank != null ? entry.rank : i + 1}</span>` +
      `<span class="podium-body">` +
      `<span class="podium-name"></span>` +
      `<span class="podium-track"><span class="podium-fill" style="width:${pct}%"></span></span>` +
      `</span>` +
      `<span class="podium-value">${esc(formatted)}</span>`;
    const nameEl = row.querySelector('.podium-name');
    nameEl.textContent = name;
    if (typeof opts.onSelect === 'function') {
      row.addEventListener('click', () => opts.onSelect(entry));
    }
    wrap.appendChild(row);
  });
  return wrap;
}

/**
 * @param {{text: string, value?: string|number, hint?: string}} insight
 * @returns {HTMLElement}
 */
export function renderInsightCard(insight) {
  const el = document.createElement('div');
  el.className = 'insight-card';
  if (insight?.hint) el.title = insight.hint;
  const valueHtml =
    insight?.value != null && insight.value !== ''
      ? `<div class="insight-value">${esc(insight.value)}</div>`
      : '';
  el.innerHTML =
    valueHtml + `<div class="insight-text">${esc(insight?.text || '')}</div>`;
  return el;
}

/**
 * Two opposing horizontal totals (e.g. ganhos vs perdas).
 * @param {{leftLabel: string, leftValue: number, rightLabel: string, rightValue: number}} data
 * @returns {HTMLElement}
 */
export function renderOpposingBars(data) {
  const wrap = document.createElement('div');
  wrap.className = 'opposing-bars';
  const left = Number(data.leftValue) || 0;
  const right = Number(data.rightValue) || 0;
  const total = left + right;
  const leftPctExact = total > 0 ? (left / total) * 100 : 0;
  const rightPctExact = total > 0 ? (right / total) * 100 : 0;
  const leftPctBar = Math.round(leftPctExact);
  const rightPctBar = total > 0 ? 100 - leftPctBar : 0;
  const fmtPct = (p) => (Math.round(p * 10) / 10).toLocaleString('pt-BR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  });
  wrap.innerHTML =
    `<div class="opposing-labels">` +
    `<span>${esc(data.leftLabel)} <strong>${fmtNum(left)}</strong> (${fmtPct(leftPctExact)}%)</span>` +
    `<span>${esc(data.rightLabel)} <strong>${fmtNum(right)}</strong> (${fmtPct(rightPctExact)}%)</span>` +
    `</div>` +
    `<div class="opposing-track">` +
    `<span class="opposing-fill opposing-left" style="width:${leftPctBar}%"></span>` +
    `<span class="opposing-fill opposing-right" style="width:${rightPctBar}%"></span>` +
    `</div>`;
  return wrap;
}

/**
 * Stacked ratio bar (donut-style substitute).
 * @param {Array<{label: string, value: number, className?: string}>} parts
 * @returns {HTMLElement}
 */
export function renderRatioBar(parts) {
  const wrap = document.createElement('div');
  wrap.className = 'ratio-bar-wrap';
  const list = parts || [];
  const total = Math.max(1, list.reduce((s, p) => s + (Number(p.value) || 0), 0));
  const track = document.createElement('div');
  track.className = 'ratio-bar-track';
  const legend = document.createElement('div');
  legend.className = 'ratio-bar-legend';
  list.forEach((p, i) => {
    const v = Number(p.value) || 0;
    const pct = Math.round((v / total) * 100);
    const seg = document.createElement('span');
    seg.className = 'ratio-bar-seg ' + (p.className || 'ratio-seg-' + (i + 1));
    seg.style.width = pct + '%';
    seg.title = `${p.label}: ${fmtNum(v)} (${pct}%)`;
    track.appendChild(seg);
    const leg = document.createElement('span');
    leg.className = 'ratio-leg';
    leg.innerHTML =
      `<i class="ratio-dot ${p.className || 'ratio-seg-' + (i + 1)}"></i>` +
      `${esc(p.label)} ${fmtNum(v)} (${pct}%)`;
    legend.appendChild(leg);
  });
  wrap.appendChild(track);
  wrap.appendChild(legend);
  return wrap;
}

/**
 * Paired duel bars for Comparar (two columns, shared max).
 * @param {Array<{label: string, a: number|null, b: number|null, lowerIsBetter?: boolean}>} metrics
 * @param {{nameA: string, nameB: string}} names
 * @returns {HTMLElement}
 */
export function renderCompareDuel(metrics, names) {
  const wrap = document.createElement('div');
  wrap.className = 'compare-duel';
  const head = document.createElement('div');
  head.className = 'compare-duel-head';
  head.innerHTML =
    `<span></span><span>${esc(names.nameA)}</span><span>${esc(names.nameB)}</span>`;
  wrap.appendChild(head);

  (metrics || []).forEach((m) => {
    const a = m.a != null ? Number(m.a) : null;
    const b = m.b != null ? Number(m.b) : null;
    if (a == null && b == null) return;
    const max = Math.max(1, a || 0, b || 0);
    let better = null;
    if (a != null && b != null && a !== b) {
      if (m.lowerIsBetter) better = a < b ? 'a' : 'b';
      else better = a > b ? 'a' : 'b';
    }
    const row = document.createElement('div');
    row.className = 'compare-duel-row';
    const aPct = a != null ? Math.max(4, Math.round((a / max) * 100)) : 0;
    const bPct = b != null ? Math.max(4, Math.round((b / max) * 100)) : 0;
    row.innerHTML =
      `<div class="compare-duel-label">${esc(m.label)}</div>` +
      `<div class="compare-duel-side${better === 'a' ? ' is-better' : ''}">` +
      `<span class="compare-duel-track"><span style="width:${aPct}%"></span></span>` +
      `<span class="compare-duel-num">${a != null ? fmtNum(a, m.digits || 0) : '—'}</span>` +
      `</div>` +
      `<div class="compare-duel-side${better === 'b' ? ' is-better' : ''}">` +
      `<span class="compare-duel-track"><span style="width:${bPct}%"></span></span>` +
      `<span class="compare-duel-num">${b != null ? fmtNum(b, m.digits || 0) : '—'}</span>` +
      `</div>`;
    wrap.appendChild(row);
  });
  return wrap;
}

if (typeof window !== 'undefined') {
  window.PererecosViz = {
    renderKpiStrip,
    renderDistBars,
    renderMiniBars,
    renderPodium,
    renderInsightCard,
    renderOpposingBars,
    renderRatioBar,
    renderCompareDuel,
    fmtNum,
  };
}
