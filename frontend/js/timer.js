import { state, API_BASE, BASE_PATH } from './state.js';
import { renderRatioBar } from './viz.js';

let timerPartialReady = false;

/** Lazily inject the timer section markup from a static HTML partial. */
export async function ensureTimerPartial() {
  if (timerPartialReady) return;
  const host = document.getElementById('section-timer');
  if (!host) return;
  if (!host.dataset.partial) {
    timerPartialReady = true;
    return;
  }
  const res = await fetch(`${BASE_PATH}/static/partials/timer.html`);
  if (!res.ok) throw new Error('timer partial ' + res.status);
  host.innerHTML = await res.text();
  delete host.dataset.partial;
  timerPartialReady = true;
}

export function formatTimerDuration(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const mins = Math.floor((s % 3600) / 60);
  if (days > 0) return days + 'd ' + hours + 'h ' + mins + 'min';
  if (hours > 0) return hours + 'h ' + mins + 'min';
  return mins + 'min ' + (s % 60) + 's';
}

export function formatPlusHms(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return '+' + h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
}

// MeiaUm tip rule observed live: R$1 -> 60s of timer. Used only to estimate
// BRL from poller deltas until Pixie webhooks give real per-txn amounts.
const TIP_SECONDS_PER_REAL = 60;

export function estimateBrlFromGrantedSeconds(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  if (!s || TIP_SECONDS_PER_REAL <= 0) return null;
  const reais = s / TIP_SECONDS_PER_REAL;
  return 'R$ ' + reais.toFixed(2).replace('.', ',');
}

export function formatPollWindowLabel(at, precisionSeconds) {
  if (!at) return '—';
  const end = new Date(at);
  const prec = Math.max(0, Math.floor(Number(precisionSeconds) || 0));
  const pad = (n) => String(n).padStart(2, '0');
  const endLabel =
    pad(end.getDate()) + '/' + pad(end.getMonth() + 1) + ' ' +
    pad(end.getHours()) + ':' + pad(end.getMinutes());
  if (prec <= 0) return endLabel + ' · janela ~1 min';
  const start = new Date(end.getTime() - prec * 1000);
  const sameDay =
    start.getDate() === end.getDate() &&
    start.getMonth() === end.getMonth() &&
    start.getFullYear() === end.getFullYear();
  const startClock = pad(start.getHours()) + ':' + pad(start.getMinutes());
  const endClock = pad(end.getHours()) + ':' + pad(end.getMinutes());
  if (sameDay && startClock === endClock) {
    return endLabel + ' · ~' + formatTimerDuration(prec);
  }
  if (sameDay) {
    return (
      pad(end.getDate()) + '/' + pad(end.getMonth() + 1) + ' ' +
      startClock + '–' + endClock
    );
  }
  return (
    pad(start.getDate()) + '/' + pad(start.getMonth() + 1) + ' ' + startClock +
    ' – ' + endLabel
  );
}

export function renderTimerBarChart(container, labelsEl, values, labelFn) {
  if (!container) return;
  container.textContent = '';
  if (labelsEl) labelsEl.textContent = '';
  const max = Math.max(1, ...values.map((v) => Math.max(0, v)));
  values.forEach((v, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'bar-wrapper';
    wrap.dataset.tooltip = labelFn(i, v);
    const bar = document.createElement('div');
    bar.className = 'bar';
    const ratio = Math.max(0, v) / max;
    bar.style.height = Math.max(2, Math.sqrt(ratio) * 100) + '%';
    wrap.appendChild(bar);
    container.appendChild(wrap);
    if (labelsEl) {
      const lab = document.createElement('div');
      lab.className = 'chart-label';
      lab.textContent = labelFn(i, v, true);
      labelsEl.appendChild(lab);
    }
  });
}

export function renderTimerRankedList(el, rows, valueFn) {
  if (!el) return;
  el.textContent = '';
  if (!rows.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = '—';
    el.appendChild(empty);
    return;
  }
  rows.forEach((row, idx) => {
    const div = document.createElement('div');
    div.className = 'active-chatter';
    div.setAttribute(
      'data-tip',
      'Dia ' + (row.date || '—') + ': ' + valueFn(row) + ' adicionados ao timer.'
    );
    const rank = document.createElement('span');
    rank.className = 'active-chatter-rank';
    rank.textContent = String(idx + 1);
    const name = document.createElement('span');
    name.className = 'active-chatter-name';
    name.textContent = row.date || '—';
    const val = document.createElement('span');
    val.className = 'active-chatter-count';
    val.textContent = valueFn(row);
    div.appendChild(rank);
    div.appendChild(name);
    div.appendChild(val);
    el.appendChild(div);
  });
}

export async function fetchTimerSection() {
  // Plain fetch — do NOT use apiUrl() (that helper appends platform/period).
  const paths = [
    '/subathon/overview',
    '/subathon/daily?days=30',
    '/subathon/hourly',
    '/subathon/increases?limit=25',
    '/subathon/timer',
    '/subathon/insights',
  ];
  const results = await Promise.all(
    paths.map((p) => fetch(API_BASE + p).then((r) => {
      if (!r.ok) throw new Error(p + ' ' + r.status);
      return r.json();
    }))
  );
  return {
    overview: results[0],
    daily: results[1],
    hourly: results[2],
    increases: results[3],
    timer: results[4],
    insights: results[5],
  };
}

export function renderTimerSection(data) {
  const emptyEl = document.getElementById('timer-empty');
  const daysTracked = Number(data.overview?.days_tracked || 0);
  if (emptyEl) emptyEl.style.display = daysTracked === 0 ? '' : 'none';

  const staleNote = document.getElementById('timer-stale');
  if (staleNote) {
    staleNote.style.display = data.timer?.stale ? '' : 'none';
    if (data.timer?.stale && data.timer?.fetched_at) {
      const t = new Date(data.timer.fetched_at);
      staleNote.textContent = 'dados de ' +
        String(t.getHours()).padStart(2, '0') + ':' +
        String(t.getMinutes()).padStart(2, '0');
    }
  }

  const setText = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };
  setText('timer-now-remaining', formatTimerDuration(data.timer?.remaining_seconds));
  setText('timer-now-state', data.timer?.mode || data.timer?.state || '—');
  setText(
    'timer-now-ends-at',
    data.timer?.ends_at ? new Date(data.timer.ends_at).toLocaleString('pt-BR') : '—'
  );

  const ov = data.overview || {};
  setText('timer-hl-total', formatTimerDuration(ov.total_added_seconds));
  setText(
    'timer-hl-biggest-day',
    ov.biggest_day
      ? (ov.biggest_day.date || '') + ' · ' + formatTimerDuration(ov.biggest_day.added_seconds)
      : '—'
  );
  setText(
    'timer-hl-static-day',
    ov.most_static_day
      ? (ov.most_static_day.date || '') + ' · ' + formatTimerDuration(ov.most_static_day.added_seconds)
      : '—'
  );
  setText('timer-hl-streak', String(ov.current_active_streak || 0) + ' / max ' + (ov.longest_active_streak || 0));
  setText('timer-hl-paused', formatTimerDuration(ov.paused_total_seconds));

  const daily = Array.isArray(data.daily) ? data.daily : [];
  renderTimerBarChart(
    document.getElementById('timer-daily-chart'),
    document.getElementById('timer-daily-labels'),
    daily.map((d) => d.added_seconds || 0),
    (i, v, short) => {
      const d = daily[i];
      if (!d) return '';
      const dd = (d.date || '').slice(8, 10) + '/' + (d.date || '').slice(5, 7);
      if (short) return dd;
      return dd + ' — ' + formatPlusHms(v) + ' (' + (d.increase_count || 0) + ' aumentos)';
    }
  );

  const byAdded = daily.slice().sort((a, b) => (b.added_seconds || 0) - (a.added_seconds || 0)).slice(0, 10);
  const byStatic = daily.slice().sort((a, b) => (a.added_seconds || 0) - (b.added_seconds || 0)).slice(0, 10);
  renderTimerRankedList(document.getElementById('timer-top-days'), byAdded, (r) => formatPlusHms(r.added_seconds));
  renderTimerRankedList(document.getElementById('timer-static-days'), byStatic, (r) => formatPlusHms(r.added_seconds));

  const hourly = Array.isArray(data.hourly) ? data.hourly : [];
  renderTimerBarChart(
    document.getElementById('timer-hourly-chart'),
    document.getElementById('timer-hourly-labels'),
    hourly.map((h) => h.added_seconds || 0),
    (i, v, short) => (short ? String(i) : (i + 'h — ' + formatPlusHms(v)))
  );

  const recentEl = document.getElementById('timer-recent-list');
  if (recentEl) {
    recentEl.textContent = '';
    const items = (data.increases?.items || []).filter(
      (it) => it.kind === 'grant' && (it.granted_seconds || 0) > 0
    );
    if (!items.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 3;
      td.className = 'empty-state';
      td.textContent = '—';
      tr.appendChild(td);
      recentEl.appendChild(tr);
    } else {
      items.forEach((it) => {
        const tr = document.createElement('tr');
        const windowLabel = formatPollWindowLabel(it.at, it.precision_seconds);
        const brl = estimateBrlFromGrantedSeconds(it.granted_seconds) || '—';
        const impact = formatPlusHms(it.granted_seconds);
        tr.setAttribute(
          'data-tip',
          'Total detectado na janela ' + windowLabel +
            ' — pode somar várias doações. Estimativa R$1 → 1 min de timer.'
        );
        const tdWhen = document.createElement('td');
        tdWhen.textContent = windowLabel;
        const tdBrl = document.createElement('td');
        tdBrl.textContent = brl;
        const tdImpact = document.createElement('td');
        tdImpact.textContent = impact;
        tr.appendChild(tdWhen);
        tr.appendChild(tdBrl);
        tr.appendChild(tdImpact);
        recentEl.appendChild(tr);
      });
    }
  }
  renderInsights(data.insights);
}

const PACE_ARROW = { up: '↑', down: '↓', flat: '→', unknown: '—' };

export function formatSigned(seconds) {
  const s = Math.floor(Number(seconds) || 0);
  const sign = s > 0 ? '+' : (s < 0 ? '-' : '');
  return sign + formatTimerDuration(Math.abs(s));
}

export function formatHourBRT(hour) {
  if (hour === null || hour === undefined) return '—';
  return String(hour).padStart(2, '0') + 'h';
}

export function renderInsights(data) {
  const setText = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };
  const ins = data || {};
  const pace = ins.pace || {};
  setText(
    'timer-pace',
    pace.minutes_per_hour == null
      ? '—'
      : pace.minutes_per_hour + ' min/h ' + (PACE_ARROW[pace.arrow] || '')
  );
  const bal = ins.balance || {};
  setText(
    'timer-balance',
    bal.net_seconds == null ? '—' : formatSigned(bal.net_seconds)
  );
  const proj = ins.projection || {};
  if (!proj.available) {
    setText('timer-projection', '—');
    setText('timer-projection-note', '—');
  } else if (proj.finite === false) {
    setText('timer-projection', 'não acaba');
    setText('timer-projection-note', 'A este ritmo o timer está ganhando tempo.');
  } else {
    setText(
      'timer-projection',
      proj.eta ? new Date(proj.eta).toLocaleString('pt-BR') : '—'
    );
    setText(
      'timer-projection-note',
      'Sem doações: ' +
        (proj.naive_eta ? new Date(proj.naive_eta).toLocaleString('pt-BR') : '—') +
        (proj.confidence === 'low' ? ' · confiança baixa (pouco histórico)' : '')
    );
  }

  const ramp = Array.isArray(ins.ramp_24h) ? ins.ramp_24h : [];
  renderTimerBarChart(
    document.getElementById('timer-ramp-chart'),
    document.getElementById('timer-ramp-labels'),
    ramp.map((r) => r.granted_seconds || 0),
    (i, v, short) => (short ? (ramp[i] ? '-'.concat(ramp[i].hours_ago, 'h') : '') : (ramp[i] ? ramp[i].hours_ago + 'h atrás — ' + formatPlusHms(v) : ''))
  );

  const msEl = document.getElementById('timer-milestones');
  if (msEl) {
    msEl.textContent = '';
    const rows = Array.isArray(ins.milestones) ? ins.milestones : [];
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = '—';
      msEl.appendChild(empty);
    } else {
      rows.forEach((m) => {
        const row = document.createElement('div');
        row.className = 'active-chatter';
        row.setAttribute(
          'data-tip',
          m.above
            ? ('Marco de ' + m.label + ': o timer está acima disso agora' +
              (m.crossed_at
                ? (m.estimated
                  ? ' (já estava acima desde o início da coleta).'
                  : ' (cruzado em ' + new Date(m.crossed_at).toLocaleString('pt-BR') + ').')
                : '.'))
            : ('Marco de ' + m.label + ': ainda não foi batido — o timer está abaixo disso.')
        );
        const mark = document.createElement('span');
        mark.className = 'active-chatter-rank';
        mark.textContent = m.above ? '✓' : '✗';
        const name = document.createElement('span');
        name.className = 'active-chatter-name';
        name.textContent = m.label;
        const val = document.createElement('span');
        val.className = 'active-chatter-count';
        val.textContent = m.crossed_at
          ? new Date(m.crossed_at).toLocaleDateString('pt-BR') +
            (m.estimated ? ' (desde o início)' : '')
          : (m.above ? 'acima agora' : 'não batido');
        row.appendChild(mark);
        row.appendChild(name);
        row.appendChild(val);
        msEl.appendChild(row);
      });
    }
  }

  const rec = ins.records || {};
  setText(
    'timer-rec-max',
    rec.max_remaining_seconds == null
      ? '—'
      : formatTimerDuration(rec.max_remaining_seconds) +
        (rec.max_remaining_at ? ' · ' + new Date(rec.max_remaining_at).toLocaleString('pt-BR') : '')
  );
  setText(
    'timer-rec-min',
    rec.min_remaining_seconds == null
      ? '—'
      : formatTimerDuration(rec.min_remaining_seconds) +
        (rec.min_remaining_at ? ' · ' + new Date(rec.min_remaining_at).toLocaleString('pt-BR') : '')
  );
  const streak = ins.growth_streak || {};
  setText(
    'timer-streak',
    (streak.current_minutes || 0) + ' / max ' + (streak.longest_minutes || 0) + ' min'
  );

  const dist = ins.distribution || {};
  const buckets = Array.isArray(dist.buckets) ? dist.buckets : [];
  renderTimerBarChart(
    document.getElementById('timer-histogram-chart'),
    document.getElementById('timer-histogram-labels'),
    buckets.map((b) => b.count || 0),
    (i, v, short) => (short ? String(v) : (buckets[i] ? buckets[i].label + ' — ' + v + ' eventos' : ''))
  );
  setText('timer-inc-biggest', dist.biggest_seconds == null ? '—' : formatPlusHms(dist.biggest_seconds));
  setText('timer-inc-mean', dist.mean_seconds == null ? '—' : formatPlusHms(dist.mean_seconds));
  setText('timer-inc-median', dist.median_seconds == null ? '—' : formatPlusHms(dist.median_seconds));
  const dry = ins.dry_spell || {};
  setText('timer-dry-now', dry.since_seconds == null ? '—' : formatTimerDuration(dry.since_seconds));
  setText('timer-dry-record', dry.record_seconds ? formatTimerDuration(dry.record_seconds) : '—');
  setText(
    'timer-dry-note',
    dry.record_may_include_downtime
      ? 'Atenção: o maior tempo sem doações pode incluir período sem coleta.'
      : 'Tempo sem doações = intervalo desde o último aumento no timer.'
  );

  const hours = ins.hours || {};
  setText('timer-hour-best', hours.best ? formatHourBRT(hours.best.hour) + ' (' + formatSigned(hours.best.net_seconds) + ')' : '—');
  setText('timer-hour-worst', hours.worst ? formatHourBRT(hours.worst.hour) + ' (' + formatSigned(hours.worst.net_seconds) + ')' : '—');

  const live = ins.live || {};
  setText('timer-live-online', formatTimerDuration(live.online_granted_seconds));
  setText('timer-live-offline', formatTimerDuration(live.offline_granted_seconds));
  const liveRatioEl = document.getElementById('timer-live-ratio');
  if (liveRatioEl) {
    liveRatioEl.textContent = '';
    const onlineSec = Number(live.online_granted_seconds) || 0;
    const offlineSec = Number(live.offline_granted_seconds) || 0;
    const viz = window.PererecosViz;
    if (viz && typeof viz.renderRatioBar === 'function' && (onlineSec > 0 || offlineSec > 0)) {
      liveRatioEl.appendChild(
        viz.renderRatioBar([
          {
            label: 'Live',
            value: onlineSec,
            display: formatTimerDuration(onlineSec),
            className: 'ratio-seg-1',
          },
          {
            label: 'Offline',
            value: offlineSec,
            display: formatTimerDuration(offlineSec),
            className: 'ratio-seg-2',
          },
        ])
      );
    }
  }
  setText(
    'timer-live-note',
    live.online_pct == null
      ? 'Status da live ainda não registrado nos aumentos coletados.'
      : live.online_pct + '% do tempo adicionado veio com a live online.' +
        (live.unknown_status_granted_seconds
          ? ' (' + formatTimerDuration(live.unknown_status_granted_seconds) + ' sem status registrado)'
          : '')
  );
}

export function renderChatSync(data) {
  const setText = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };
  const panic = (data || {}).panic || {};
  setText('timer-panic-time', panic.panic_seconds == null ? '—' : formatTimerDuration(panic.panic_seconds));
  setText('timer-panic-rate', panic.avg_msgs_per_min == null ? '—' : String(panic.avg_msgs_per_min));
  setText(
    'timer-panic-delta',
    panic.delta_pct == null ? '—' : (panic.delta_pct > 0 ? '+' : '') + panic.delta_pct + '%'
  );
  const topEl = document.getElementById('timer-panic-top');
  if (topEl) {
    topEl.textContent = '';
    const rows = Array.isArray(panic.top_moments) ? panic.top_moments : [];
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'Nenhum momento de pânico ainda.';
      topEl.appendChild(empty);
    } else {
      rows.forEach((m) => {
        const row = document.createElement('div');
        row.className = 'active-chatter';
        row.textContent =
          new Date(m.at).toLocaleString('pt-BR') + ' — ' +
          formatTimerDuration(m.remaining_seconds) + ' restantes · ' + m.msgs + ' msgs';
        row.setAttribute(
          'data-tip',
          'Momento de pânico: timer abaixo de 30 min, com ' +
            m.msgs + ' mensagens nesse intervalo. Um dos picos mais agitados do chat.'
        );
        topEl.appendChild(row);
      });
    }
  }
  const emoteEl = document.getElementById('timer-reactive-emotes');
  if (emoteEl) {
    emoteEl.textContent = '';
    const rows = Array.isArray(data && data.reactive_emotes) ? data.reactive_emotes : [];
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'Sem aumentos suficientes ainda.';
      emoteEl.appendChild(empty);
    } else {
      rows.forEach((e, idx) => {
        const row = document.createElement('div');
        row.className = 'leaderboard-entry timer-reactive-row';
        row.setAttribute(
          'data-tip',
          e.lift == null
            ? (e.emote_name + ': ' + e.after_per_min + '/min nos 5 min após aumentos (sem baseline suficiente pra comparar).')
            : (e.emote_name + ': ' + e.after_per_min + '/min após aumentos — ' +
              e.lift + '× o ritmo normal do período.')
        );

        const rank = document.createElement('span');
        rank.className = 'rank';
        rank.textContent = '#' + (idx + 1);

        const name = document.createElement('span');
        name.className = 'entry-name';

        const emoteId = e.emote_id || null;
        let cachedUrl = e.emote_name ? state.sevenTVEmotes.get(e.emote_name) : null;
        if (!cachedUrl && e.emote_name) {
          // Case-insensitive fallback (7TV map keys are exact names).
          const needle = String(e.emote_name).toLowerCase();
          for (const [k, url] of state.sevenTVEmotes.entries()) {
            if (String(k).toLowerCase() === needle) {
              cachedUrl = url;
              break;
            }
          }
        }
        const imgUrl = emoteId
          ? ('https://cdn.7tv.app/emote/' + emoteId + '/1x.webp')
          : cachedUrl;
        if (imgUrl) {
          const img = document.createElement('img');
          img.src = imgUrl;
          img.alt = e.emote_name || '';
          img.width = 20;
          img.height = 20;
          img.loading = 'lazy';
          img.decoding = 'async';
          img.referrerPolicy = 'no-referrer';
          img.style.flexShrink = '0';
          img.onerror = function () { this.remove(); };
          name.appendChild(img);
        }

        const nameText = document.createElement('span');
        nameText.className = 'name-text';
        nameText.textContent = e.emote_name || '—';
        name.appendChild(nameText);

        const val = document.createElement('span');
        val.className = 'entry-count';
        val.textContent = e.after_per_min + '/min (' + (e.lift == null ? '—' : 'x' + e.lift) + ')';

        row.appendChild(rank);
        row.appendChild(name);
        row.appendChild(val);
        emoteEl.appendChild(row);
      });
    }
  }
}

export async function loadChatSync() {
  if (state.chatSyncLoaded) return;
  state.chatSyncLoaded = true;
  try {
    const res = await fetch(API_BASE + '/subathon/chat-sync');
    if (!res.ok) throw new Error('chat-sync ' + res.status);
    renderChatSync(await res.json());
  } catch (err) {
    console.error('chat-sync load failed', err);
    state.chatSyncLoaded = false;
  }
}

export async function loadTimerSection(force = false) {
  if (state.timerSectionLoaded && !force) return;
  state.timerSectionLoaded = true;
  try {
    await ensureTimerPartial();
    const data = await fetchTimerSection();
    renderTimerSection(data);
    if (force) state.chatSyncLoaded = false;
    await loadChatSync();
  } catch (err) {
    console.error('Timer section load failed', err);
    state.timerSectionLoaded = false;
  }
  if (state.timerSectionRefreshTimer) clearInterval(state.timerSectionRefreshTimer);
  state.timerSectionRefreshTimer = setInterval(() => {
    if (state.currentSection === 'timer') loadTimerSection(true);
  }, 5 * 60 * 1000);
}
