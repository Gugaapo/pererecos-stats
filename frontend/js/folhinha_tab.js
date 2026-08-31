/**
 * Folhinha tab section loader — boards first (fast), overview after.
 */
import { FOLHINHA_BOARDS } from './boards/folhinha.js';
import {
  renderKpiStrip,
  renderDistBars,
  renderMiniBars,
  renderInsightCard,
  renderOpposingBars,
  renderRatioBar,
  fmtNum,
} from './viz.js';

/**
 * @param {object} ctx
 * @param {function} ctx.apiUrl
 * @param {function} ctx.setLeaderboardError
 * @param {function} ctx.renderEntry — (el, entries, board) => void
 * @param {function} [ctx.selectUser]
 * @param {function} [ctx.navigateToBoard]
 * @param {function} [ctx.onLoaded]
 */
export async function loadFolhinhaBoards(ctx) {
  let boardsPayload = null;
  let overviewData = null;

  const paintOverview = () => {
    if (!overviewData) return;
    renderFolhinhaOverview(overviewData, boardsPayload || {}, ctx);
  };

  // Overview is above the fold — fetch in parallel with boards
  const overviewPromise = (async () => {
    const root = document.getElementById('folhinha-overview');
    try {
      const res = await fetch(ctx.apiUrl('/stats/folhinha/overview'));
      if (!res.ok) throw new Error('overview ' + res.status);
      overviewData = await res.json();
      paintOverview();
    } catch (err) {
      console.error('Folhinha overview failed', err);
      if (root) root.innerHTML = '';
    }
  })();

  try {
    const res = await fetch(ctx.apiUrl('/stats/folhinha/tab', { limit: 10 }));
    if (!res.ok) throw new Error('API /stats/folhinha/tab ' + res.status);
    const data = await res.json();
    boardsPayload = data.boards || {};
  } catch (err) {
    console.error('Folhinha tab batch failed', err);
    boardsPayload = {};
    await Promise.all(
      FOLHINHA_BOARDS.map(async (board) => {
        const el = document.getElementById(board.listId);
        if (!el) return;
        try {
          const res = await fetch(ctx.apiUrl(board.endpoint, board.params || {}));
          if (!res.ok) throw new Error('API ' + board.endpoint);
          const data = await res.json();
          const entries = data[board.responseKey || 'leaderboard'] || [];
          boardsPayload[board.id] = entries;
          ctx.renderEntry(el, entries, board);
        } catch (e) {
          console.error('Folhinha board', board.id, e);
          ctx.setLeaderboardError(el);
        }
      })
    );
    paintOverview();
    await overviewPromise;
    return;
  }

  FOLHINHA_BOARDS.forEach((board) => {
    const el = document.getElementById(board.listId);
    if (!el) return;
    ctx.renderEntry(el, boardsPayload[board.id] || [], board);
  });

  if (typeof ctx.onLoaded === 'function') {
    ctx.onLoaded(boardsPayload, null);
  }

  // Refresh overview insights that depend on board tops (mais-fortes / mais-fracos)
  paintOverview();
  await overviewPromise;
}

function renderFolhinhaOverview(overview, boards, ctx) {
  const root = document.getElementById('folhinha-overview');
  if (!root) return;
  root.textContent = '';
  if (!overview) {
    root.innerHTML = '<div class="empty-state">Sem overview</div>';
    return;
  }

  const t = overview.totals || {};
  const wrap = document.createElement('div');
  wrap.className = 'viz-overview';

  wrap.appendChild(
    renderKpiStrip([
      { label: 'Bonks', value: fmtNum(t.bonks), hint: 'Total de ?bonk no período' },
      { label: 'Abraços', value: fmtNum(t.abracos), hint: 'Total de ?abraco' },
      { label: 'Apostas', value: fmtNum(t.slots), hint: '?cookie slot' },
      { label: 'Roleta', value: fmtNum(t.roulette), hint: 'Sobreviveram + se foram' },
    ])
  );

  const hero = document.createElement('div');
  hero.className = 'viz-overview-hero';

  const histCard = document.createElement('div');
  histCard.innerHTML = '<div class="section-label">Distribuição de impacto (?bonk %)</div>';
  histCard.appendChild(renderDistBars(overview.bonk_pct_histogram || []));
  hero.appendChild(histCard);

  const side = document.createElement('div');
  side.style.display = 'flex';
  side.style.flexDirection = 'column';
  side.style.gap = '0.75rem';

  const fortes = (boards['mais-fortes'] || [])[0];
  const fracos = (boards['mais-fracos'] || [])[0];
  if (fortes) {
    side.appendChild(
      renderInsightCard({
        value: (Number(fortes.avg_percentage) || 0).toFixed(1) + '%',
        text: `${fortes.display_name || fortes.username} lidera a média de impacto`,
        hint: 'Mais Fortes (mín. 3 bonks)',
      })
    );
  }
  if (fracos) {
    side.appendChild(
      renderInsightCard({
        value: (Number(fracos.avg_percentage) || 0).toFixed(1) + '%',
        text: `${fracos.display_name || fracos.username} com a média mais baixa`,
        hint: 'Mais Fracos',
      })
    );
  }
  const pair = overview.top_bonk_pair;
  if (pair) {
    side.appendChild(
      renderInsightCard({
        value: fmtNum(pair.count) + '×',
        text: `${pair.actor_display_name} ↔ ${pair.target_display_name}`,
        hint: 'Dupla mais caótica (bonks mútuos A→B + B→A)',
      })
    );
  }
  hero.appendChild(side);
  wrap.appendChild(hero);
  root.appendChild(wrap);

  const stories = document.getElementById('folhinha-stories');
  if (!stories) return;
  stories.textContent = '';

  const duel = document.createElement('div');
  duel.className = 'card story-card';
  duel.innerHTML =
    '<div class="section-label">Duelo mais caótico</div>' +
    '<div class="section-note">Quem mais se bonkou mutuamente</div>';
  if (pair) {
    const actorName = pair.actor_display_name || pair.actor_username;
    const targetName = pair.target_display_name || pair.target_username;
    const actorCount = Number(pair.actor_count) || 0;
    const targetCount = Number(pair.target_count) || 0;
    const total = Number(pair.count) || actorCount + targetCount;

    const body = document.createElement('div');
    body.className = 'duel-highlight';
    body.style.marginTop = '0.75rem';

    const names = document.createElement('div');
    names.className = 'duel-highlight-names';

    const actorBtn = document.createElement('button');
    actorBtn.type = 'button';
    actorBtn.className = 'duel-highlight-name';
    actorBtn.textContent = actorName;
    if (ctx.selectUser) {
      actorBtn.addEventListener('click', () => ctx.selectUser(pair.actor_username, pair.platform));
    }

    const arrow = document.createElement('span');
    arrow.className = 'duel-highlight-arrow';
    arrow.textContent = '↔';
    arrow.setAttribute('aria-hidden', 'true');

    const targetBtn = document.createElement('button');
    targetBtn.type = 'button';
    targetBtn.className = 'duel-highlight-name';
    targetBtn.textContent = targetName;
    if (ctx.selectUser) {
      targetBtn.addEventListener('click', () => ctx.selectUser(pair.target_username, pair.platform));
    }

    names.appendChild(actorBtn);
    names.appendChild(arrow);
    names.appendChild(targetBtn);

    const count = document.createElement('div');
    count.className = 'duel-highlight-count';
    count.textContent = fmtNum(total) + ' bonks';

    const barWrap = document.createElement('div');
    barWrap.style.marginTop = '0.75rem';
    barWrap.appendChild(
      renderRatioBar([
        { label: actorName, value: actorCount, className: 'ratio-seg-1' },
        { label: targetName, value: targetCount, className: 'ratio-seg-2' },
      ])
    );

    body.appendChild(names);
    body.appendChild(count);
    body.appendChild(barWrap);
    duel.appendChild(body);
  } else {
    duel.innerHTML += '<div class="empty-state">Sem pares ainda</div>';
  }
  stories.appendChild(duel);

  const cookies = document.createElement('div');
  cookies.className = 'card story-card';
  cookies.innerHTML = '<div class="section-label">Economia de cookies</div><div class="section-note">Maiores saldos anunciados</div>';
  const cookieRows = (overview.cookie_top || []).map((c) => ({
    label: c.display_name || c.username,
    value: c.count,
    onClick: ctx.selectUser ? () => ctx.selectUser(c.username, c.platform) : undefined,
  }));
  const cookieBody = document.createElement('div');
  cookieBody.style.marginTop = '0.75rem';
  cookieBody.appendChild(renderMiniBars(cookieRows, { maxRows: 5 }));
  cookies.appendChild(cookieBody);
  stories.appendChild(cookies);

  const slot = document.createElement('div');
  slot.className = 'card story-card';
  slot.innerHTML = '<div class="section-label">Apostas: ganhos vs perdas</div><div class="section-note">Cookies ganhos vs perdidos</div>';
  const st = overview.slot_totals || {};
  const slotBody = document.createElement('div');
  slotBody.style.marginTop = '0.75rem';
  slotBody.appendChild(
    renderOpposingBars({
      leftLabel: 'Ganhos',
      leftValue: st.won || 0,
      rightLabel: 'Perdas',
      rightValue: st.lost || 0,
    })
  );
  slot.appendChild(slotBody);
  stories.appendChild(slot);

  const roleta = document.createElement('div');
  roleta.className = 'card story-card';
  roleta.innerHTML = '<div class="section-label">Roleta</div><div class="section-note">Sobreviveram vs Se foram</div>';
  const roletaBody = document.createElement('div');
  roletaBody.style.marginTop = '0.75rem';
  roletaBody.appendChild(
    renderRatioBar([
      { label: 'Sobreviveram', value: t.roulette_survive || 0, className: 'ratio-seg-1' },
      { label: 'Se foram', value: t.roulette_death || 0, className: 'ratio-seg-2' },
    ])
  );
  roleta.appendChild(roletaBody);
  stories.appendChild(roleta);
}
