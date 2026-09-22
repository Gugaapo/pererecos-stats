import { state, BASE_PATH, EMOTE_RANKING_PAGE } from './state.js';
import { apiUrl } from './api.js';
import { getPeriodLabel, showError, hideError, renderSimpleRankList } from './shared.js';
import { chatGeralBtn, generalView, statsSection, leaderboard, emoteView, emoteSearchInput, emoteAutocomplete, chatTopEmotes, emoteSearchBtn, btnEmotesCondensadas, btnEmotesBackRanking, emotesRankingDetails } from './dom.js';
import { hooks } from './hooks.js';

export function loadEmotesSection(force = false) {
  if (state.emotesSectionLoaded && !force) return;
  state.emotesSectionLoaded = true;
  // Condensadas visuals are the above-the-fold default — keep light.
  if (force) state.emotePositionUsersCache = null;
  state.emotesCondensadasLoaded = true;
  fetchChatTopEmotes().then((emotes) => {
    if (state.sidebarContextMode === 'emotes' && emotes) {
      renderSidebarTopEmotes(emotes.slice(0, 10));
    }
  });
  fetchLeastUsedEmotes();
  // Heavy: only when user opens ranking / after idle
  const rankingDetails = document.getElementById('emotes-ranking-details');
  if (rankingDetails && rankingDetails.open) {
    fetchEmoteRanking(force);
  }
  // Defer position spectrum — was ~2–3s and blocked perceived Emotes load
  setTimeout(() => {
    if (state.currentSection === 'emotes') fetchChatEmotePositions();
  }, 1200);
}

export function loadEmotesCondensadasSection(force = false) {
  // Deep-link compat: show main Emotes tab (condensadas-first)
  hooks.navigateToSection('emotes', false);
  loadEmotesSection(force);
}
export function renderTopEmotes(container, emotes, { showRank = true } = {}) {
  container.textContent = '';

  if (!emotes || emotes.length === 0) {
    container.innerHTML = '<div class="empty-state">Nenhum emote encontrado</div>';
    return;
  }

  emotes.forEach((emote, index) => {
    const item = document.createElement('div');
    item.className = 'emote-item';
    item.title = emote.emote_name;
    item.addEventListener('click', () => navigateToEmote(emote.emote_name));

    if (showRank) {
      const rank = document.createElement('div');
      rank.className = 'emote-rank';
      rank.textContent = '#' + (index + 1);
      item.appendChild(rank);
    }

    const img = document.createElement('img');
    img.src = `https://cdn.7tv.app/emote/${emote.emote_id}/2x.webp`;
    img.alt = emote.emote_name;
    img.loading = 'lazy';

    const count = document.createElement('div');
    count.className = 'emote-count';
    count.textContent = (emote.count || 0).toLocaleString('pt-BR');

    const name = document.createElement('div');
    name.className = 'emote-name';
    name.textContent = emote.emote_name;
    name.title = emote.emote_name;

    item.appendChild(img);
    item.appendChild(count);
    item.appendChild(name);
    container.appendChild(item);
  });
}

export function renderEmoteRankingList(container, emotes, { filter = '', preserveRank = true, limit = null } = {}) {
  if (!container) return;
  container.textContent = '';
  if (!emotes || !emotes.length) {
    container.innerHTML = '<div class="empty-state">Nenhum emote encontrado</div>';
    return;
  }
  const q = (filter || '').trim().toLowerCase();
  const matched = [];
  emotes.forEach((emote, index) => {
    if (q && !(emote.emote_name || '').toLowerCase().includes(q)) return;
    matched.push({ emote, index });
  });
  if (!matched.length) {
    container.innerHTML = '<div class="empty-state">Nenhum emote corresponde ao filtro</div>';
    return;
  }
  const max = limit == null ? matched.length : Math.min(limit, matched.length);
  const frag = document.createDocumentFragment();
  for (let i = 0; i < max; i++) {
    const { emote, index } = matched[i];
    const row = document.createElement('div');
    row.className = 'emote-ranking-row';
    row.title = emote.emote_name;
    row.addEventListener('click', () => navigateToEmote(emote.emote_name));

    const rank = document.createElement('span');
    rank.className = 'emote-ranking-rank';
    rank.textContent = '#' + (preserveRank ? index + 1 : i + 1);

    const img = document.createElement('img');
    img.src = `https://cdn.7tv.app/emote/${emote.emote_id}/2x.webp`;
    img.alt = emote.emote_name;
    img.loading = 'lazy';

    const name = document.createElement('span');
    name.className = 'emote-ranking-name';
    name.textContent = emote.emote_name;

    const count = document.createElement('span');
    count.className = 'emote-ranking-count';
    count.textContent = (emote.count || 0).toLocaleString('pt-BR');

    row.appendChild(rank);
    row.appendChild(img);
    row.appendChild(name);
    row.appendChild(count);
    frag.appendChild(row);
  }
  container.appendChild(frag);

  if (limit != null && matched.length > limit) {
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'emotes-link-btn secondary';
    more.style.marginTop = '0.75rem';
    more.textContent = 'Carregar mais (' + (matched.length - limit).toLocaleString('pt-BR') + ' restantes)';
    more.addEventListener('click', (e) => {
      e.stopPropagation();
      state.emoteRankingVisible += EMOTE_RANKING_PAGE;
      renderFilteredEmoteRanking();
    });
    container.appendChild(more);
  }
}

export function renderFilteredEmoteRanking() {
  const list = state.emoteRankingCache && state.emoteRankingCache.emotes;
  renderEmoteRankingList(
    document.getElementById('emote-ranking-list'),
    list,
    { filter: state.emoteRankingFilter, preserveRank: true, limit: state.emoteRankingVisible }
  );
  const note = document.getElementById('note-emote-ranking');
  if (note && state.emoteRankingCache) {
    const label = getPeriodLabel();
    const base = 'Todos os emotes do catalogo por usos (' + label + ') — clique para detalhes';
    note.textContent = base +
      ' · ' + (state.emoteRankingCache.total_emotes || 0).toLocaleString('pt-BR') +
      ' emotes · ' + (state.emoteRankingCache.total_uses || 0).toLocaleString('pt-BR') + ' usos';
  }
  updateEmotePareto(list || []);
}

export function updateEmotePareto(emotes) {
  const fill = document.getElementById('emote-pareto-fill');
  const note = document.getElementById('emote-pareto-note');
  if (!fill || !note) return;
  const total = emotes.reduce((s, e) => s + (e.count || 0), 0);
  if (!total) {
    fill.style.width = '0%';
    note.textContent = '';
    return;
  }
  let acc = 0;
  let n = 0;
  for (const e of emotes) {
    acc += e.count || 0;
    n += 1;
    if (acc / total >= 0.8) break;
  }
  const pct = Math.round((n / emotes.length) * 100);
  fill.style.width = Math.min(100, pct) + '%';
  note.textContent = n + ' emotes (' + pct + '% do catalogo) concentram ~80% dos usos';
}

export async function fetchEmoteRanking(force = false) {
  if (state.emoteRankingCache && !force) {
    renderFilteredEmoteRanking();
    return state.emoteRankingCache;
  }
  const listEl = document.getElementById('emote-ranking-list');
  if (listEl && state.currentSection === 'emotes') {
    listEl.innerHTML = '<div class="empty-state">Carregando...</div>';
  }
  try {
    const response = await fetch(apiUrl('/stats/emotes/ranking'));
    if (!response.ok) throw new Error('API Error');
    state.emoteRankingCache = await response.json();
    state.emoteRankingVisible = EMOTE_RANKING_PAGE;
    renderFilteredEmoteRanking();
    return state.emoteRankingCache;
  } catch (error) {
    console.error('Error fetching emote ranking:', error);
    if (listEl) listEl.innerHTML = '<div class="empty-state">Erro ao carregar ranking</div>';
    return null;
  }
}

export async function fetchChatTopEmotes() {
  try {
    const response = await fetch(apiUrl('/stats/top-emotes'));
    if (response.ok) {
      const data = await response.json();
      const emotes = data.emotes || [];
      renderTopEmotes(chatTopEmotes, emotes);
      return emotes;
    }
  } catch (error) {
    console.error('Error fetching chat top emotes:', error);
  }
  return null;
}

export async function fetchLeastUsedEmotes() {
  const leastEl = document.getElementById('chat-least-emotes');
  const unusedEl = document.getElementById('chat-unused-emotes');
  const unusedSummary = document.getElementById('unused-emotes-summary');
  const unusedNote = document.getElementById('chat-unused-emotes-summary');
  try {
    const response = await fetch(apiUrl('/stats/emotes/least-used'));
    if (!response.ok) return;
    const data = await response.json();
    const unusedCount = data.unused_count || (data.unused || []).length;
    if (unusedNote) {
      unusedNote.textContent = unusedCount.toLocaleString('pt-BR') +
        ' emote' + (unusedCount === 1 ? '' : 's') + ' com 0 usos no periodo';
    }
    if (unusedSummary) {
      unusedSummary.textContent = 'Ver emotes nunca usados (' + unusedCount.toLocaleString('pt-BR') + ')';
    }
    if (unusedEl) {
      if (!unusedCount) {
        unusedEl.innerHTML = '<div class="empty-state">Todos os emotes foram usados</div>';
      } else {
        renderTopEmotes(unusedEl, data.unused || [], { showRank: false });
      }
    }
    if (leastEl) {
      renderTopEmotes(leastEl, data.least_used || [], { showRank: true });
    }
  } catch (error) {
    console.error('Error fetching least used emotes:', error);
  }
}
export async function fetchEmoteDetail(emoteName) {
  try {
    const response = await fetch(apiUrl(`/stats/emote/${encodeURIComponent(emoteName)}`));
    if (!response.ok) {
      showError('Emote nao encontrado');
      return;
    }
    const data = await response.json();
    document.getElementById('emote-detail-name').textContent = data.emote_name;
    const img = document.getElementById('emote-detail-img');
    img.src = `https://cdn.7tv.app/emote/${data.emote_id}/4x.webp`;
    img.alt = data.emote_name;
    const creatorEl = document.getElementById('emote-detail-creator');
    if (data.creator_display_name || data.creator_username) {
      creatorEl.textContent = 'Criado por ' + (data.creator_display_name || data.creator_username);
      creatorEl.style.cursor = data.creator_username ? 'pointer' : 'default';
      creatorEl.onclick = data.creator_username
        ? () => hooks.selectUser(data.creator_username)
        : null;
    } else {
      creatorEl.textContent = '';
      creatorEl.onclick = null;
    }
    const usage = data.usage || {};
    document.getElementById('emote-usage-day').textContent = (usage.day || 0).toLocaleString('pt-BR');
    document.getElementById('emote-usage-week').textContent = (usage.week || 0).toLocaleString('pt-BR');
    document.getElementById('emote-usage-month').textContent = (usage.month || 0).toLocaleString('pt-BR');
    document.getElementById('emote-usage-all').textContent = (usage.all || 0).toLocaleString('pt-BR');
    renderSimpleRankList(
      document.getElementById('emote-contributors-list'),
      data.top_contributors || [],
      'count'
    );
    document.title = data.emote_name + ' - Pererecos Stats';
  } catch (error) {
    console.error('Error fetching emote detail:', error);
    showError('Erro ao carregar emote');
  }
}

export function navigateToEmote(emoteName, updateUrl = true) {
  if (!emoteName) return;
  state.currentEmoteName = emoteName;
  state.currentUsername = '';
  state.currentUserPlatform = null;
  hooks.hideRanqueadaBoardView();
  hideError();
  generalView.classList.add('hidden');
  statsSection.classList.remove('visible');
  if (emoteView) emoteView.classList.add('visible');
  chatGeralBtn.classList.remove('active');
  hooks.updateNavActive('section', 'emotes');
  if (updateUrl) pushEmoteURL(emoteName);
  fetchEmoteDetail(emoteName);
}

export function pushEmoteURL(emoteName) {
  const url = BASE_PATH + '/emotes/' + encodeURIComponent(emoteName) + hooks.buildFilterQuery(state.currentPlatform, state.currentPeriod);
  history.pushState({
    mode: 'emote',
    emoteName,
    platform: state.currentPlatform,
    period: state.currentPeriod,
  }, '', url);
}

export async function loadRandomNavEmoteIcon() {
  const icon = document.getElementById('nav-emotes-icon');
  if (!icon) return;
  try {
    const response = await fetch(apiUrl('/stats/top-emotes'));
    if (!response.ok) return;
    const data = await response.json();
    const emotes = (data.emotes || []).filter(e => e && e.emote_id);
    if (!emotes.length) return;
    const pick = emotes[Math.floor(Math.random() * Math.min(10, emotes.length))];
    icon.src = `https://cdn.7tv.app/emote/${pick.emote_id}/2x.webp`;
    icon.alt = pick.emote_name || '';
    icon.title = pick.emote_name || '';
  } catch (error) {
    console.error('Error loading nav emote icon:', error);
  }
}


export function renderEmotePositionBar(container, positions, label, clickable = false) {
  container.textContent = '';

  if (!positions || positions.total === 0) {
    container.innerHTML = '<div class="empty-state">Nenhum emote encontrado</div>';
    return;
  }

  const bar = document.createElement('div');
  bar.className = 'stacked-bar';

  const segmentMap = {
    comeco: { key: 'esquerdistas', label: 'Esquerdistas' },
    meio: { key: 'centrao', label: 'Centrão' },
    fim: { key: 'direitistas', label: 'Direitistas' }
  };

  const segments = [
    { cls: 'comeco', pct: positions.comeco_pct, name: 'Começo' },
    { cls: 'meio', pct: positions.meio_pct, name: 'Meio' },
    { cls: 'fim', pct: positions.fim_pct, name: 'Fim' }
  ];

  segments.forEach(seg => {
    if (seg.pct > 0) {
      const el = document.createElement('div');
      el.className = 'bar-segment ' + seg.cls + (clickable ? ' clickable' : '');
      el.style.flexBasis = seg.pct + '%';
      el.textContent = seg.pct >= 8 ? seg.pct + '%' : '';
      el.title = seg.name + ': ' + seg.pct + '% — clique para ver usuarios';

      if (clickable) {
        el.addEventListener('click', () => {
          // Toggle active state
          const allSegs = bar.querySelectorAll('.bar-segment');
          const wasActive = el.classList.contains('active');
          allSegs.forEach(s => s.classList.remove('active'));

          // Remove existing panel
          const existing = container.querySelector('.position-users-panel');
          if (existing) existing.remove();

          if (!wasActive) {
            el.classList.add('active');
            const info = segmentMap[seg.cls];
            togglePositionUsersList(container, info.key, info.label, seg.cls);
          }
        });
      }

      bar.appendChild(el);
    }
  });

  container.appendChild(bar);

  const legend = document.createElement('div');
  legend.className = 'stacked-bar-legend';

  segments.forEach(seg => {
    const item = document.createElement('span');
    item.className = 'legend-item';

    const dot = document.createElement('span');
    dot.className = 'legend-dot ' + seg.cls;

    const text = document.createTextNode(seg.name + ' (' + seg.pct + '%)');

    item.appendChild(dot);
    item.appendChild(text);
    legend.appendChild(item);
  });

  container.appendChild(legend);

  if (clickable) {
    const hint = document.createElement('div');
    hint.style.cssText = 'font-size: 0.7rem; color: var(--text-muted); margin-top: 0.3rem; opacity: 0.7;';
    hint.textContent = 'Clique em uma seção para ver os pererecos';
    container.appendChild(hint);
  }

  if (label) {
    const labelEl = document.createElement('div');
    const labelCls = label === 'esquerdista' ? 'esquerdista' : label === 'centrão' ? 'centrao' : 'direitista';
    labelEl.className = 'emote-position-label ' + labelCls;
    labelEl.textContent = label;
    container.appendChild(labelEl);
  }
}

export async function togglePositionUsersList(container, groupKey, groupLabel, segmentCls) {
  // Fetch data if not cached
  if (!state.emotePositionUsersCache) {
    const loadingPanel = document.createElement('div');
    loadingPanel.className = 'position-users-panel';
    loadingPanel.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-muted);">Carregando...</div>';
    container.appendChild(loadingPanel);

    try {
      const response = await fetch(apiUrl('/stats/emote-position-users'));
      if (!response.ok) throw new Error('API error');
      state.emotePositionUsersCache = await response.json();
    } catch (error) {
      console.error('Error fetching emote position users:', error);
      loadingPanel.innerHTML = '<div style="padding: 1rem; text-align: center; color: #e74c3c;">Erro ao carregar</div>';
      return;
    }
    loadingPanel.remove();
  }

  const users = state.emotePositionUsersCache[groupKey] || [];
  renderPositionUsersPanel(container, users, groupLabel, segmentCls);
}

export function renderPositionUsersPanel(container, users, title, segmentCls) {
  // Remove existing panel if any
  const existing = container.querySelector('.position-users-panel');
  if (existing) existing.remove();

  const panel = document.createElement('div');
  panel.className = 'position-users-panel';

  const headerCls = segmentCls === 'comeco' ? 'esquerdista' : segmentCls === 'meio' ? 'centrao' : 'direitista';

  const header = document.createElement('div');
  header.className = 'position-users-header ' + headerCls;

  const titleSpan = document.createElement('span');
  titleSpan.textContent = title + ' (' + users.length + ')';

  const closeBtn = document.createElement('button');
  closeBtn.className = 'position-close-btn';
  closeBtn.innerHTML = '&times;';
  closeBtn.onclick = () => {
    panel.remove();
    container.querySelectorAll('.bar-segment').forEach(s => s.classList.remove('active'));
  };

  header.appendChild(titleSpan);
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const list = document.createElement('div');
  list.className = 'position-users-list';

  if (users.length === 0) {
    list.innerHTML = '<div style="padding: 0.8rem; text-align: center; color: var(--text-muted);">Nenhum usuario</div>';
  } else {
    users.forEach(user => {
      const item = document.createElement('div');
      item.className = 'position-user-item';

      const rank = document.createElement('span');
      rank.className = 'position-user-rank';
      rank.textContent = '#' + user.rank;

      const name = document.createElement('span');
      name.className = 'position-user-name';
      name.textContent = user.display_name;
      name.onclick = () => hooks.selectUser(user.username, user.platform);

      const msgs = document.createElement('span');
      msgs.className = 'position-user-msgs';
      const posLabel = segmentCls === 'comeco' ? 'na esquerda' : segmentCls === 'meio' ? 'no fodasse' : 'na direita';
      msgs.textContent = user.position_count.toLocaleString('pt-BR') + ' emotes ' + posLabel;

      item.appendChild(rank);
      item.appendChild(name);
      item.appendChild(msgs);
      list.appendChild(item);
    });
  }

  panel.appendChild(list);
  container.appendChild(panel);
}

export async function fetchChatEmotePositions() {
  try {
    const response = await fetch(apiUrl('/stats/emote-position-users'));
    if (response.ok) {
      const data = await response.json();
      state.emotePositionUsersCache = data;

      const esq = (data.esquerdistas || []).length;
      const cen = (data.centrao || []).length;
      const dir = (data.direitistas || []).length;
      const total = esq + cen + dir;

      if (total === 0) return;

      const positions = {
        comeco: esq,
        meio: cen,
        fim: dir,
        comeco_pct: Math.round((esq / total) * 1000) / 10,
        meio_pct: Math.round((cen / total) * 1000) / 10,
        fim_pct: Math.round((dir / total) * 1000) / 10,
        total: total
      };

      const container = document.getElementById('chat-emote-positions');
      renderEmotePositionBar(container, positions, null, true);
    }
  } catch (error) {
    console.error('Error fetching emote positions:', error);
  }
}
export async function fetchEmoteAutocomplete(query) {
  if (!emoteAutocomplete) return;
  try {
    const response = await fetch(apiUrl('/stats/emotes/search', { q: query }));
    if (!response.ok) return;
    const results = await response.json();
    emoteAutocomplete.textContent = '';
    if (!results.length) {
      emoteAutocomplete.classList.remove('visible');
      return;
    }
    results.forEach((emote) => {
      const item = document.createElement('div');
      item.className = 'autocomplete-item';
      item.textContent = emote.emote_name;
      item.addEventListener('click', () => {
        emoteSearchInput.value = emote.emote_name;
        emoteAutocomplete.classList.remove('visible');
        navigateToEmote(emote.emote_name);
      });
      emoteAutocomplete.appendChild(item);
    });
    emoteAutocomplete.classList.add('visible');
    state.selectedEmoteAutocompleteIndex = -1;
  } catch (e) {
    console.error(e);
  }
}

if (emoteSearchInput) {
  emoteSearchInput.addEventListener('input', () => {
    const q = emoteSearchInput.value.trim();
    state.emoteRankingFilter = q;
    state.emoteRankingVisible = EMOTE_RANKING_PAGE;
    if (state.currentSection === 'emotes') {
      renderFilteredEmoteRanking();
    }
    if (state.emoteSearchTimeout) clearTimeout(state.emoteSearchTimeout);
    if (q.length < 1) {
      if (emoteAutocomplete) emoteAutocomplete.classList.remove('visible');
      return;
    }
    state.emoteSearchTimeout = setTimeout(() => fetchEmoteAutocomplete(q), 150);
  });
  emoteSearchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const name = emoteSearchInput.value.trim();
      if (name) navigateToEmote(name);
    }
  });
}
if (emoteSearchBtn) {
  emoteSearchBtn.addEventListener('click', () => {
    const name = (emoteSearchInput && emoteSearchInput.value.trim()) || '';
    if (name) navigateToEmote(name);
  });
}

if (btnEmotesCondensadas) {
  btnEmotesCondensadas.addEventListener('click', () => {
    hooks.navigateToSection('emotes');
    const details = document.getElementById('emotes-ranking-details');
    if (details) details.open = false;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}
if (btnEmotesBackRanking) {
  btnEmotesBackRanking.addEventListener('click', () => {
    hooks.navigateToSection('emotes');
  });
}

if (emotesRankingDetails) {
  emotesRankingDetails.addEventListener('toggle', () => {
    if (emotesRankingDetails.open) {
      fetchEmoteRanking(false);
    }
  });
}

export function renderSidebarTopEmotes(emotes) {
  leaderboard.textContent = '';
  const list = (emotes || []).slice(0, 10);
  if (!list.length) {
    leaderboard.innerHTML = '<div class="empty-state">Sem emotes</div>';
    return;
  }
  list.forEach((e, i) => {
    const item = document.createElement('div');
    item.className = 'leaderboard-entry';
    item.style.cursor = 'pointer';
    item.addEventListener('click', () => navigateToEmote(e.emote_name || e.name));
    const rank = document.createElement('span');
    rank.className = 'rank';
    rank.textContent = '#' + (e.rank || i + 1);
    const name = document.createElement('span');
    name.className = 'entry-name';
    name.textContent = e.emote_name || e.name || '—';
    const count = document.createElement('span');
    count.className = 'entry-count';
    count.textContent = (e.count || 0).toLocaleString('pt-BR');
    item.appendChild(rank);
    item.appendChild(name);
    item.appendChild(count);
    leaderboard.appendChild(item);
  });
}
