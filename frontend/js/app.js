/**
 * App orchestrator — ranqueada/folhinha boards, filters, sidebar, wiring.
 * Section UIs live in dedicated ES modules imported below.
 */
import { state, API_BASE, BASE_PATH, DEFAULT_TITLE, RESERVED_SECTIONS, COLLECTION_START, MEIA_TIMER_EMOTE_ID, SMOKE_TIME_EMOTE_ID } from './state.js';
import { apiUrl, setLeaderboardError } from './api.js';
import { hooks } from './hooks.js';
import { RANQUEADA_BOARDS, getRanqueadaBoard } from './boards/registry.js';
import { loadRanqueadaBoards } from './ranqueada.js';
import { loadFolhinhaBoards } from './folhinha_tab.js';
import * as viz from './viz.js';

import {
  loadTimerSection,
} from './timer.js';
import {
  loadEmotesSection,
  loadEmotesCondensadasSection,
  renderTopEmotes,
  renderEmotePositionBar,
  navigateToEmote,
  loadRandomNavEmoteIcon,
  fetchEmoteRanking,
  fetchChatTopEmotes,
  fetchLeastUsedEmotes,
  fetchChatEmotePositions,
  renderSidebarTopEmotes,
  renderFilteredEmoteRanking,
  fetchEmoteDetail,
  pushEmoteURL,
} from './emotes.js';
import {
  loadCoreStats,
  loadChartStats,
  loadInitialData,
  fetchLeaderboard,
  fetchActiveChatters,
  fetchChatActivity,
  fetchUniqueChatters,
  fetchOverallActivity,
  fetch7TVEmotes,
  filterActiveChatters,
  renderLeaderboard,
  renderActiveChatters,
} from './home.js';
import {
  fetchUserStats,
  showUserSectionPlaceholders,
  renderMessageWithEmotes,
  fetchUsernameHistory,
} from './user.js';
import {
  showGeneralView,
  showSectionPanel,
  updateNavActive,
  loadSectionData,
  navigateToSection,
  searchUser,
  selectUser,
  parseAppPath,
  getParamsFromURL,
  buildFilterQuery,
  pushUserURL,
  pushHomeURL,
  pushSectionURL,
  applyFiltersFromState,
  applyRoute,
  initFromURL,
  updateHomeNavIcon,
  updateLeaderboardSelection,
} from './nav.js';
import {
  loadRodaSection,
  fetchSmokeTime,
} from './roda.js';
import {
  loadCompararSection,
  runCompare,
  wireCompareAutocomplete,
} from './comparar.js';
import {
  syncExportDateInputs,
  renderExportNerdEmote,
  openExportModal,
  closeExportModal,
  startMessageExport,
  openRibbits,
  loadRibbit,
} from './modals.js';
import {
  searchUsersForAutocomplete,
  hideAutocomplete,
  fetchAutocomplete,
  updateAutocompleteSelection,
} from './autocomplete.js';
import { todayBRTISO, setEntryName, refreshEmoteNotes, getPeriodLabel, updatePeriodLabels, showError, hideError, renderSimpleRankList } from './shared.js';
import { usernameInput, searchBtn, chatGeralBtn, autocompleteDropdown, generalView, statsSection, leaderboard, risingList, hoursList, writersList, famosinhosList, folhinhaList, emoteView, ranqueadaBoardView, ranqueadaBoardTitleEl, ranqueadaBoardDescEl, ranqueadaBoardListEl, ranqueadaBoardPagerEl, ranqueadaBoardPageLabel, ranqueadaBoardPrevBtn, ranqueadaBoardNextBtn, ranqueadaBoardBackBtn, activeSearch, filterBtns, platformFilterBtns, customDateRow, customStartInput, customEndInput, customDateApply, top10Card, top10Toggle, usernameHistoryBtn, usernameHistoryPopup } from './dom.js';

// Expose viz for any leftover window.PererecosViz references
if (typeof window !== 'undefined') {
  window.PererecosViz = viz;
}

async function loadRanqueadaSection(force = false) {
  if (state.ranqueadaSectionLoaded && !force) return;
  state.ranqueadaSectionLoaded = true;
  refreshEmoteNotes();

  const boards = RANQUEADA_BOARDS || [];
  const fetchCache = new Map();
  const boardDataMap = {};
  let overviewTimer = null;

  const scheduleOverview = () => {
    if (overviewTimer) clearTimeout(overviewTimer);
    overviewTimer = setTimeout(() => renderRanqueadaOverview(boardDataMap), 50);
  };

  const fetchBoardData = (board) => {
    const key = board.endpoint + JSON.stringify(board.params || {});
    if (!fetchCache.has(key)) {
      fetchCache.set(
        key,
        fetch(apiUrl(board.endpoint, board.params || {}))
          .then((r) => {
            if (!r.ok) throw new Error('API ' + board.endpoint + ' ' + r.status);
            return r.json();
          })
      );
    }
    return fetchCache.get(key);
  };

  // Paint each board as soon as it returns (old fast path)
  await Promise.all(
    boards.map(async (board) => {
      const el = document.getElementById(board.listId);
      if (!el && board.id !== 'hour-leaders') return;
      try {
        const data = await fetchBoardData(board);
        boardDataMap[board.id] = data;
        const entries = extractBoardEntries(board, data, { detail: false });
        if (el) renderRanqueadaBoard(board, el, entries, data, { detail: false });
        scheduleEqualizeBoardCards();
        if (['hour-leaders', 'pererecoes', 'rising', 'emotes-rising', 'emotes-falling'].includes(board.id)) {
          scheduleOverview();
        }
      } catch (err) {
        console.error('Board', board.id, err);
        if (el) setLeaderboardError(el);
      }
    })
  );
  renderRanqueadaOverview(boardDataMap);
  equalizeBoardCards();
}

let equalizeBoardCardsTimer = null;
function scheduleEqualizeBoardCards() {
  if (equalizeBoardCardsTimer) clearTimeout(equalizeBoardCardsTimer);
  equalizeBoardCardsTimer = setTimeout(() => equalizeBoardCards(), 40);
}

/** Match Ranqueada/Folhinha board cards to the tallest in each grid. */
function equalizeBoardCards() {
  document.querySelectorAll('.ranqueada-grid').forEach((grid) => {
    const cards = Array.from(grid.children).filter(
      (el) => el.classList.contains('ranqueada-card') && !el.classList.contains('ranqueada-card--hours')
    );
    if (!cards.length) return;
    cards.forEach((c) => {
      c.style.minHeight = '';
    });
    const maxH = cards.reduce((m, c) => Math.max(m, c.offsetHeight), 0);
    if (maxH > 0) {
      const px = Math.ceil(maxH) + 'px';
      cards.forEach((c) => {
        c.style.minHeight = px;
      });
    }
  });
}

function renderRanqueadaOverview(boardDataMap) {
  const viz = window.PererecosViz;
  const kpiEl = document.getElementById('ranqueada-kpi');
  const calloutsEl = document.getElementById('ranqueada-callouts');
  const weatherEl = document.getElementById('ranqueada-weather-story');
  const perEl = document.getElementById('ranqueada-pererecao-story');

  const perData = boardDataMap.pererecoes;
  const risingData = boardDataMap.rising;
  const weatherData = boardDataMap['emotes-rising'] || boardDataMap['emotes-falling'];
  const topPer = (perData && perData.leaderboard && perData.leaderboard[0]) || null;
  const topGirino = (risingData && risingData.entries && risingData.entries[0]) || null;
  const topRisingEmote = (weatherData && weatherData.rising && weatherData.rising[0]) || null;
  const topFallingEmote = (weatherData && weatherData.falling && weatherData.falling[0]) || null;

  // KPIs from leaderboard + overall if available
  if (kpiEl && viz) {
    kpiEl.textContent = '';
    const items = [];
    if (state.totalLeaderboardUsers > 0) {
      items.push({
        label: 'Pererecos',
        value: state.totalLeaderboardUsers.toLocaleString('pt-BR'),
        hint: 'Pererecos no ranking do período',
      });
    }
    const lb = document.getElementById('leaderboard');
    const topMsg = lb && lb.querySelector('.entry-count');
    // Prefer overall total if already loaded
    const overall = document.getElementById('overall-total');
    if (overall && overall.textContent && overall.textContent !== '0') {
      items.push({
        label: 'Msgs no período',
        value: overall.textContent,
        hint: 'Total de mensagens (home)',
      });
    }
    if (topPer) {
      items.push({
        label: 'Pererecão',
        value: topPer.display_name || topPer.username,
        hint: (topPer.points || 0).toLocaleString('pt-BR') + ' pts',
      });
    }
    if (topGirino) {
      items.push({
        label: 'Girino #1',
        value: topGirino.display_name || topGirino.username,
        hint: (topGirino.growth_percent >= 0 ? '+' : '')
          + (Number(topGirino.growth_percent) || 0).toFixed(0) + '%',
      });
    }
    if (!items.length) {
      kpiEl.innerHTML = '<div class="empty-state">Carregando KPIs...</div>';
      // Refresh once leaderboard lands
      setTimeout(() => {
        if (state.totalLeaderboardUsers > 0) renderRanqueadaOverview(boardDataMap);
      }, 800);
    } else {
      kpiEl.appendChild(viz.renderKpiStrip(items));
    }
  }

  if (calloutsEl && viz) {
    calloutsEl.textContent = '';
    if (topPer) {
      calloutsEl.appendChild(
        viz.renderInsightCard({
          value: (topPer.points || 0).toLocaleString('pt-BR') + ' pts',
          text: (topPer.display_name || topPer.username) + ' é o Pererecão #1',
        })
      );
    }
    if (topGirino) {
      const g = Number(topGirino.growth_percent) || 0;
      calloutsEl.appendChild(
        viz.renderInsightCard({
          value: (g >= 0 ? '+' : '') + g.toFixed(0) + '%',
          text: (topGirino.display_name || topGirino.username) + ' lidera os Girinos',
        })
      );
    }
    if (topRisingEmote) {
      calloutsEl.appendChild(
        viz.renderInsightCard({
          value: topRisingEmote.emote_name || '—',
          text: 'Emote em alta no clima do chat',
          hint: 'Crescimento vs janela anterior',
        })
      );
    }
    if (!calloutsEl.children.length) {
      calloutsEl.innerHTML = '<div class="empty-state">Sem callouts</div>';
    }
  }

  // Weather story: paired mini-bars
  if (weatherEl && viz) {
    weatherEl.textContent = '';
    const rising = (weatherData && weatherData.rising) || [];
    const falling = (weatherData && weatherData.falling) || [];
    const label = document.createElement('div');
    label.className = 'section-note';
    label.textContent = 'Em alta';
    weatherEl.appendChild(label);
    weatherEl.appendChild(
      viz.renderMiniBars(
        rising.slice(0, 4).map((e) => ({
          label: e.emote_name || '—',
          value: Math.abs(Number(e.delta_pct != null ? e.delta_pct : e.delta) || e.count || 0),
          sub: e.delta_pct != null
            ? ((e.delta_pct >= 0 ? '+' : '') + Number(e.delta_pct).toFixed(0) + '%')
            : (e.delta != null ? ((e.delta >= 0 ? '+' : '') + e.delta) : String(e.count || '')),
          onClick: e.emote_name ? () => navigateToEmote(e.emote_name) : undefined,
        })),
        { maxRows: 4 }
      )
    );
    const label2 = document.createElement('div');
    label2.className = 'section-note';
    label2.style.marginTop = '0.75rem';
    label2.textContent = 'Em baixa';
    weatherEl.appendChild(label2);
    weatherEl.appendChild(
      viz.renderMiniBars(
        falling.slice(0, 4).map((e) => ({
          label: e.emote_name || '—',
          value: Math.abs(Number(e.delta_pct != null ? e.delta_pct : e.delta) || e.count || 0),
          sub: e.delta_pct != null
            ? (Number(e.delta_pct).toFixed(0) + '%')
            : (e.delta != null ? String(e.delta) : String(e.count || '')),
          onClick: e.emote_name ? () => navigateToEmote(e.emote_name) : undefined,
        })),
        { maxRows: 4 }
      )
    );
  }

  // Pererecão breakdown
  if (perEl && viz) {
    perEl.textContent = '';
    if (!topPer) {
      perEl.innerHTML = '<div class="empty-state">Sem dados</div>';
    } else {
      const title = document.createElement('div');
      title.className = 'insight-text';
      title.style.marginBottom = '0.5rem';
      title.textContent = (topPer.display_name || topPer.username)
        + ' — '
        + (topPer.points || 0).toLocaleString('pt-BR')
        + ' pts';
      perEl.appendChild(title);
      const parts = (topPer.breakdown || []).slice(0, 8);
      perEl.appendChild(
        viz.renderMiniBars(
          parts.map((b) => ({
            label: b.board + ' (#' + b.position + ')',
            value: b.points || 0,
          })),
          { maxRows: 8 }
        )
      );
    }
  }

  // no-op: hours live in the board grid again
}

function renderFolhinhaTabEntry(el, entries, board) {
  if (!entries || !entries.length) {
    el.innerHTML = '<div class="empty-state">Nenhum dado ainda</div>';
    scheduleEqualizeBoardCards();
    return;
  }
  const isPct = board.render === 'folhinha-pct';
  const countKey = isPct ? 'avg_percentage' : (board.countKey || 'count');
  el.textContent = '';
  entries.forEach((entry) => {
    const item = document.createElement('div');
    item.className = 'leaderboard-entry';
    item.style.cursor = 'pointer';
    item.addEventListener('click', () => {
      if (entry.username) selectUser(entry.username, entry.platform || null);
    });

    const rank = document.createElement('span');
    rank.className = 'rank';
    rank.textContent = '#' + (entry.rank || '');

    const name = document.createElement('span');
    name.className = 'entry-name';
    setEntryName(name, entry.display_name || entry.username, entry.platform);

    const count = document.createElement('span');
    count.className = 'entry-count';
    const val = entry[countKey] != null ? entry[countKey] : entry.value;
    if (isPct) {
      count.classList.add('entry-count--stacked');
      const main = document.createElement('span');
      main.className = 'entry-count-main';
      main.textContent = (Number(val) || 0).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '%';
      const sub = document.createElement('span');
      sub.className = 'entry-count-sub';
      const bonks = entry.count != null ? entry.count : 0;
      sub.textContent = bonks.toLocaleString('pt-BR') + ' bonks';
      count.appendChild(main);
      count.appendChild(sub);
    } else {
      count.textContent = (val || 0).toLocaleString('pt-BR');
    }

    item.appendChild(rank);
    item.appendChild(name);
    item.appendChild(count);
    el.appendChild(item);
  });
  scheduleEqualizeBoardCards();
}

async function loadFolhinhaSection(force = false) {
  if (state.folhinhaSectionLoaded && !force) return;
  state.folhinhaSectionLoaded = true;

  // Prefer module loader when available; always have a direct fallback so a
  // broken ES-module graph cannot leave the tab stuck on "Carregando..."
  const paintBoards = (payload) => {
    const boards = window.FOLHINHA_BOARDS || [];
    const map = payload || {};
    if (boards.length) {
      boards.forEach((board) => {
        const el = document.getElementById(board.listId);
        if (!el) return;
        renderFolhinhaTabEntry(el, map[board.id] || [], board);
      });
    } else {
      // Registry missing — still paint known list ids from payload keys
      Object.keys(map).forEach((id) => {
        const el = document.getElementById('fh-' + id.replace(/_/g, '-') + '-list')
          || document.querySelector('[data-fh-board="' + id + '"] .leaderboard-list');
        if (!el) return;
        renderFolhinhaTabEntry(el, map[id] || [], {
          id,
          render: id === 'mais-fortes' || id === 'mais-fracos' ? 'folhinha-pct' : 'folhinha-count',
          countKey: id === 'mais-fortes' || id === 'mais-fracos' ? 'avg_percentage' : 'count',
        });
      });
    }
    if (state.sidebarContextMode === 'bonks' && map.bonkadores) {
      renderSimpleRankList(leaderboard, map.bonkadores, 'count');
    }
  };

  try {
    if (typeof loadFolhinhaBoards === 'function') {
      await loadFolhinhaBoards({
        apiUrl,
        setLeaderboardError,
        renderEntry: renderFolhinhaTabEntry,
        selectUser,
        navigateToBoard: (id) => navigateToRanqueadaBoard(id, true, 1, 'folhinha'),
        onLoaded: (boardsPayload) => {
          if (state.sidebarContextMode === 'bonks' && boardsPayload && boardsPayload.bonkadores) {
            renderSimpleRankList(leaderboard, boardsPayload.bonkadores, 'count');
          }
          equalizeBoardCards();
        },
      });
      return;
    }

    const res = await fetch(apiUrl('/stats/folhinha/tab', { limit: 10 }));
    if (!res.ok) throw new Error('API /stats/folhinha/tab ' + res.status);
    const data = await res.json();
    paintBoards(data.boards || {});
    equalizeBoardCards();
  } catch (err) {
    console.error(err);
    state.folhinhaSectionLoaded = false;
    document.querySelectorAll('#folhinha-grid .leaderboard-list').forEach((el) => {
      setLeaderboardError(el);
    });
  }
}

function extractBoardEntries(board, data, opts = {}) {
  if (typeof board.mapEntries === 'function') {
    return board.mapEntries(data, {
      detail: !!opts.detail,
      detailLimit: board.detailLimit || 50,
    });
  }
  if (board.render === 'weather-rising') return data.rising || [];
  if (board.render === 'weather-falling') return data.falling || [];
  if (board.responseKey) return data[board.responseKey] || [];
  return data;
}

function renderRanqueadaBoard(board, el, entries, rawData, opts = {}) {
  const detail = !!opts.detail;
  const maxRows = detail ? null : 10;

  switch (board.render) {
    case 'simple':
      renderSimpleRankList(el, sliceEntries(entries, maxRows), board.countKey || 'count');
      break;
    case 'duas-caras':
      renderDuasCaras(el, sliceEntries(entries, maxRows));
      break;
    case 'pererecoes':
      renderPererecoes(el, sliceEntries(entries, maxRows));
      break;
    case 'rising':
      renderRisingStars(sliceEntries(entries, maxRows), el);
      break;
    case 'writers':
      renderTopWriters(sliceEntries(entries, maxRows), el);
      break;
    case 'hours':
      renderHourLeaders(entries, el);
      break;
    case 'commands':
      renderFolhinhaCommands(el, entries, { maxRows: maxRows || entries.length });
      break;
    case 'weather-rising':
    case 'weather-falling':
      renderEmoteWeatherList(el, entries, { maxRows: maxRows || entries.length });
      break;
    case 'folhinha-count':
    case 'folhinha-pct':
      renderFolhinhaDetailList(el, sliceEntries(entries, maxRows), board);
      break;
    default:
      console.warn('Unknown board render:', board.render);
      setLeaderboardError(el, 'Render desconhecido');
  }
}

function boardValueKey(board) {
  if (board.render === 'folhinha-pct') return 'avg_percentage';
  if (board.render === 'rising') return 'growth_percent';
  if (board.render === 'writers') return 'score';
  if (board.render === 'pererecoes') return 'points';
  if (board.render === 'duas-caras') return 'name_count';
  if (board.countKey) return board.countKey;
  return 'count';
}

function formatBoardValue(board, entry, val) {
  const n = Number(val) || 0;
  if (board.render === 'folhinha-pct') {
    return n.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '%';
  }
  if (board.render === 'rising') {
    const g = entry.growth_percent != null ? entry.growth_percent : val;
    const num = Number(g) || 0;
    const s = num.toLocaleString('pt-BR', { maximumFractionDigits: 0 });
    return (num >= 0 ? '+' : '') + s + '%';
  }
  if (board.render === 'writers') {
    return n.toLocaleString('pt-BR', { maximumFractionDigits: 2 });
  }
  if (board.render === 'pererecoes') {
    return n.toLocaleString('pt-BR') + ' pts';
  }
  return n.toLocaleString('pt-BR');
}

function renderFolhinhaDetailList(el, entries, board) {
  const isPct = board.render === 'folhinha-pct';
  const countKey = isPct ? 'avg_percentage' : (board.countKey || 'count');
  el.textContent = '';
  if (!entries.length) {
    el.innerHTML = '<div class="empty-state">Nenhum dado ainda</div>';
    return;
  }
  entries.forEach((entry) => {
    const item = document.createElement('div');
    item.className = 'leaderboard-entry';
    item.style.cursor = 'pointer';
    item.addEventListener('click', () => {
      if (entry.username) selectUser(entry.username, entry.platform || null);
    });
    const rank = document.createElement('span');
    rank.className = 'rank';
    rank.textContent = '#' + (entry.rank || '');
    const name = document.createElement('span');
    name.className = 'entry-name';
    setEntryName(name, entry.display_name || entry.username, entry.platform);
    const count = document.createElement('span');
    count.className = 'entry-count';
    const val = entry[countKey] != null ? entry[countKey] : entry.value;
    if (isPct) {
      count.classList.add('entry-count--stacked');
      const main = document.createElement('span');
      main.className = 'entry-count-main';
      main.textContent = (Number(val) || 0).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '%';
      const sub = document.createElement('span');
      sub.className = 'entry-count-sub';
      sub.textContent = (entry.count || 0).toLocaleString('pt-BR') + ' bonks';
      count.appendChild(main);
      count.appendChild(sub);
    } else {
      count.textContent = (val || 0).toLocaleString('pt-BR');
    }
    item.appendChild(rank);
    item.appendChild(name);
    item.appendChild(count);
    el.appendChild(item);
  });
}

function sliceEntries(entries, maxRows) {
  if (!entries) return [];
  if (maxRows == null) return entries;
  return entries.slice(0, maxRows);
}

function resolveBoard(idOrSlug) {
  const key = String(idOrSlug || '').toLowerCase();
  if (typeof window.getFolhinhaBoard === 'function') {
    const fh = window.getFolhinhaBoard(key);
    if (fh) return fh;
  }
  if (typeof getRanqueadaBoard === 'function') {
    const rq = getRanqueadaBoard(key);
    if (rq) return rq;
  }
  const fromFh = (window.FOLHINHA_BOARDS || []).find((b) => b.id === key || b.slug === key);
  if (fromFh) return fromFh;
  return (RANQUEADA_BOARDS || []).find((b) => b.id === key || b.slug === key) || null;
}

function navigateToRanqueadaBoard(boardId, updateUrl = true, page = 1, source = null) {
  const board = resolveBoard(boardId);
  if (!board) {
    navigateToSection(source === 'folhinha' ? 'folhinha' : 'ranqueada', updateUrl);
    return;
  }
  const isFolhinha = !!(board.render && String(board.render).startsWith('folhinha'));
  state.currentBoardSource = source || (isFolhinha ? 'folhinha' : 'ranqueada');
  state.currentRanqueadaBoardId = board.id;
  state.currentUsername = '';
  state.currentUserPlatform = null;
  state.currentEmoteName = '';
  state.ranqueadaBoardPage = Math.max(1, parseInt(page, 10) || 1);
  hideError();
  generalView.classList.add('hidden');
  statsSection.classList.remove('visible');
  if (emoteView) emoteView.classList.remove('visible');
  if (ranqueadaBoardView) ranqueadaBoardView.classList.add('visible');
  chatGeralBtn.classList.remove('active');
  updateNavActive('section', state.currentBoardSource === 'folhinha' ? 'folhinha' : 'ranqueada');
  if (updateUrl) pushRanqueadaBoardURL(board.id, state.ranqueadaBoardPage);
  loadRanqueadaBoardDetail(board, true);
}

function pushRanqueadaBoardURL(boardId, page = 1) {
  let qs = buildFilterQuery(state.currentPlatform, state.currentPeriod);
  if (page > 1) {
    qs = qs ? qs + '&page=' + page : '?page=' + page;
  }
  const section = state.currentBoardSource === 'folhinha' ? 'folhinha' : 'ranqueada';
  const url = BASE_PATH + '/' + section + '/' + encodeURIComponent(boardId) + qs;
  history.pushState({
    mode: 'ranqueada-board',
    boardId,
    page,
    boardSource: state.currentBoardSource,
    platform: state.currentPlatform,
    period: state.currentPeriod,
  }, '', url);
}

function hideRanqueadaBoardView() {
  state.currentRanqueadaBoardId = '';
  state.currentBoardSource = 'ranqueada';
  state.ranqueadaBoardEntries = [];
  state.ranqueadaBoardMeta = null;
  state.ranqueadaBoardPage = 1;
  if (ranqueadaBoardView) ranqueadaBoardView.classList.remove('visible');
}

async function loadRanqueadaBoardDetail(board, resetPage = false) {
  if (!board || !ranqueadaBoardListEl) return;
  if (resetPage) state.ranqueadaBoardPage = Math.max(1, state.ranqueadaBoardPage || 1);
  state.ranqueadaBoardMeta = board;
  if (ranqueadaBoardTitleEl) ranqueadaBoardTitleEl.textContent = board.title || board.id;
  if (ranqueadaBoardDescEl) ranqueadaBoardDescEl.textContent = board.description || '';
  document.title = (board.title || board.id) + ' - '
    + (state.currentBoardSource === 'folhinha' ? 'Folhinha' : 'Ranqueada')
    + ' - Pererecos Stats';
  ranqueadaBoardListEl.innerHTML = '<div class="empty-state loading">Carregando...</div>';
  if (ranqueadaBoardPagerEl) ranqueadaBoardPagerEl.hidden = true;

  const params = { ...(board.params || {}) };
  if (board.detailLimit) params.limit = board.detailLimit;
  // Weather / named boards need limit even if grid params omitted it
  if (!params.limit && board.detailLimit) params.limit = board.detailLimit;

  try {
    const response = await fetch(apiUrl(board.endpoint, params));
    if (!response.ok) throw new Error('API Error');
    const data = await response.json();
    if (state.currentRanqueadaBoardId !== board.id) return;
    state.ranqueadaBoardEntries = extractBoardEntries(board, data, { detail: true }) || [];
    const pageSize = board.pageSize || 20;
    const paginate = board.paginateDetail !== false && board.render !== 'hours';
    const totalPages = paginate
      ? Math.max(1, Math.ceil(state.ranqueadaBoardEntries.length / pageSize))
      : 1;
    if (state.ranqueadaBoardPage > totalPages) state.ranqueadaBoardPage = totalPages;
    renderRanqueadaBoardPage();
  } catch (err) {
    console.error('Board detail', board.id, err);
    setLeaderboardError(ranqueadaBoardListEl);
  }
}

function renderRanqueadaBoardPage() {
  const board = state.ranqueadaBoardMeta;
  if (!board || !ranqueadaBoardListEl) return;
  const paginate = board.paginateDetail !== false && board.render !== 'hours';
  const pageSize = board.pageSize || 20;
  const total = state.ranqueadaBoardEntries.length;
  const totalPages = paginate ? Math.max(1, Math.ceil(total / pageSize)) : 1;
  if (state.ranqueadaBoardPage < 1) state.ranqueadaBoardPage = 1;
  if (state.ranqueadaBoardPage > totalPages) state.ranqueadaBoardPage = totalPages;

  let pageEntries = state.ranqueadaBoardEntries;
  let rankOffset = 0;
  if (paginate) {
    const start = (state.ranqueadaBoardPage - 1) * pageSize;
    rankOffset = start;
    pageEntries = state.ranqueadaBoardEntries.slice(start, start + pageSize).map((e, i) => {
      if (e && e.rank != null) return e;
      return Object.assign({}, e, { rank: start + i + 1 });
    });
  }

  // Hours detail uses heatmap class on the list container
  if (board.render === 'hours') {
    ranqueadaBoardListEl.className = 'hour-heatmap';
  } else {
    ranqueadaBoardListEl.className = 'leaderboard-list';
  }

  renderRanqueadaBoard(board, ranqueadaBoardListEl, pageEntries, null, { detail: true });

  if (ranqueadaBoardPagerEl) {
    if (!paginate || totalPages <= 1) {
      ranqueadaBoardPagerEl.hidden = true;
    } else {
      ranqueadaBoardPagerEl.hidden = false;
      if (ranqueadaBoardPageLabel) {
        ranqueadaBoardPageLabel.textContent =
          'Página ' + state.ranqueadaBoardPage + ' de ' + totalPages
          + ' (' + total + ')';
      }
      if (ranqueadaBoardPrevBtn) ranqueadaBoardPrevBtn.disabled = state.ranqueadaBoardPage <= 1;
      if (ranqueadaBoardNextBtn) ranqueadaBoardNextBtn.disabled = state.ranqueadaBoardPage >= totalPages;
    }
  }
}

function setRanqueadaBoardPage(page, updateUrl = true) {
  state.ranqueadaBoardPage = page;
  renderRanqueadaBoardPage();
  if (updateUrl && state.currentRanqueadaBoardId) {
    pushRanqueadaBoardURL(state.currentRanqueadaBoardId, state.ranqueadaBoardPage);
  }
}

function renderFolhinhaCommands(el, cmds, opts = {}) {
  el.textContent = '';
  const maxRows = opts.maxRows != null ? opts.maxRows : 10;
  const list = (cmds || []).slice(0, maxRows);
  if (!list.length) {
    el.innerHTML = '<div class="empty-state">Nenhum comando</div>';
    return;
  }
  list.forEach((c) => {
    const row = document.createElement('div');
    row.className = 'leaderboard-entry';
    row.innerHTML = '<span class="rank"></span><span class="entry-name"></span><span class="entry-count"></span>';
    row.querySelector('.rank').textContent = '#' + c.rank;
    row.querySelector('.entry-name').textContent = '?' + c.command;
    row.querySelector('.entry-count').textContent = (c.count || 0).toLocaleString('pt-BR');
    el.appendChild(row);
  });
}

function renderEmoteWeatherList(container, rows, opts = {}) {
  container.textContent = '';
  if (!rows || !rows.length) {
    container.innerHTML = '<div class="empty-state">Nenhum dado</div>';
    return;
  }
  const maxRows = opts.maxRows != null ? opts.maxRows : 10;
  rows.slice(0, maxRows).forEach((e, i) => {
    const row = document.createElement('div');
    row.className = 'leaderboard-entry';
    row.style.cursor = 'pointer';
    row.addEventListener('click', () => navigateToEmote(e.emote_name));
    const delta = e.delta != null ? e.delta : ((e.count_now || 0) - (e.count_prev || 0));
    const pct = e.delta_pct != null ? e.delta_pct : null;

    const rank = document.createElement('span');
    rank.className = 'rank';
    // Prefer API/global rank when present; else position in this slice
    rank.textContent = '#' + (e.rank != null ? e.rank : (i + 1 + (opts.rankOffset || 0)));

    const name = document.createElement('span');
    name.className = 'entry-name';
    if (e.emote_id) {
      const img = document.createElement('img');
      img.src = 'https://cdn.7tv.app/emote/' + e.emote_id + '/1x.webp';
      img.alt = e.emote_name;
      img.width = 20;
      img.height = 20;
      img.loading = 'lazy';
      img.style.flexShrink = '0';
      name.appendChild(img);
    }
    const nameText = document.createElement('span');
    nameText.className = 'name-text';
    nameText.textContent = e.emote_name;
    nameText.title = e.emote_name;
    name.appendChild(nameText);

    const count = document.createElement('span');
    count.className = 'entry-count';
    const deltaLabel = (delta >= 0 ? '+' : '') + delta
      + (pct != null ? ' (' + (pct >= 0 ? '+' : '') + pct + '%)' : '');
    count.textContent = deltaLabel;
    count.title = deltaLabel;

    row.appendChild(rank);
    row.appendChild(name);
    row.appendChild(count);
    container.appendChild(row);
  });
}

function refreshAllData() {
  loadCoreStats();
  if (state.currentRanqueadaBoardId) {
    const board = resolveBoard(state.currentRanqueadaBoardId);
    if (board) loadRanqueadaBoardDetail(board, true);
  } else if (!state.currentUsername && !state.currentEmoteName) {
    refreshSidebarContext(state.currentSection);
    if (state.currentSection === 'home') {
      setTimeout(loadChartStats, 300);
    } else if (state.currentSection === 'emotes') {
      state.emotesSectionLoaded = false;
      state.emoteRankingCache = null;
      loadEmotesSection(true);
    } else if (state.currentSection === 'emotes-condensadas') {
      state.emotesSectionLoaded = false;
      state.emoteRankingCache = null;
      loadEmotesSection(true);
    } else if (state.currentSection === 'roda') {
      state.smokeTimeLoaded = false;
      loadRodaSection(true);
    } else if (state.currentSection === 'ranqueada') {
      state.ranqueadaSectionLoaded = false;
      loadRanqueadaSection(true);
    } else if (state.currentSection === 'folhinha') {
      state.folhinhaSectionLoaded = false;
      loadFolhinhaSection(true);
    } else if (state.currentSection === 'comparar') {
      state.compararSectionLoaded = false;
      loadCompararSection(true);
    }
  }
  if (state.currentUsername) fetchUserStats(true);
  if (state.currentEmoteName) fetchEmoteDetail(state.currentEmoteName);
}

searchBtn?.addEventListener('click', () => {
  hideAutocomplete();
  searchUser();
});

chatGeralBtn?.addEventListener('click', () => {
  navigateToSection('home');
});

document.querySelectorAll('.stats-nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    const section = btn.dataset.section || 'home';
    navigateToSection(section);
  });
});

usernameInput?.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
    if (state.selectedAutocompleteIndex >= 0 && items[state.selectedAutocompleteIndex]) {
      items[state.selectedAutocompleteIndex].click();
    } else {
      hideAutocomplete();
      searchUser();
    }
  }
});

usernameInput?.addEventListener('keydown', (e) => {
  const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    state.selectedAutocompleteIndex = Math.min(state.selectedAutocompleteIndex + 1, items.length - 1);
    updateAutocompleteSelection(items);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    state.selectedAutocompleteIndex = Math.max(state.selectedAutocompleteIndex - 1, -1);
    updateAutocompleteSelection(items);
  } else if (e.key === 'Escape') {
    hideAutocomplete();
  }
});

usernameInput?.addEventListener('input', () => {
  const query = usernameInput.value.trim();
  if (state.searchTimeout) clearTimeout(state.searchTimeout);

  if (query.length < 2) {
    hideAutocomplete();
    return;
  }

  state.searchTimeout = setTimeout(() => {
    fetchAutocomplete(query);
  }, 150);
});

usernameInput?.addEventListener('focus', () => {
  const query = usernameInput.value.trim();
  if (query.length >= 2) {
    fetchAutocomplete(query);
  }
});

document.addEventListener('click', (e) => {
  if (!e.target.closest('.search-wrapper')) {
    hideAutocomplete();
  }
});

activeSearch?.addEventListener('input', () => {
  filterActiveChatters(activeSearch.value);
});


function syncCustomDateInputs() {
  const today = todayBRTISO();
  if (customStartInput) {
    customStartInput.min = COLLECTION_START;
    customStartInput.max = today;
    if (!customStartInput.value) customStartInput.value = state.customStartDate || COLLECTION_START;
  }
  if (customEndInput) {
    customEndInput.min = COLLECTION_START;
    customEndInput.max = today;
    if (!customEndInput.value) customEndInput.value = state.customEndDate || today;
  }
}

function applyPeriodChange() {
  if (state.currentUsername) {
    pushUserURL(state.currentUsername, state.currentUserPlatform || state.currentPlatform, state.currentPeriod);
  } else if (state.currentEmoteName) {
    pushEmoteURL(state.currentEmoteName);
  } else if (state.currentRanqueadaBoardId) {
    state.ranqueadaBoardPage = 1;
    pushRanqueadaBoardURL(state.currentRanqueadaBoardId, 1);
  } else if (['emotes', 'emotes-condensadas', 'roda', 'ranqueada', 'comparar', 'folhinha', 'timer'].includes(state.currentSection)) {
    pushSectionURL(state.currentSection);
  } else {
    pushHomeURL();
  }
  updatePeriodLabels();
  state.emotesSectionLoaded = false;
  state.emotesCondensadasLoaded = false;
  state.emoteRankingCache = null;
  state.smokeTimeLoaded = false;
  state.timerSectionLoaded = false;
  state.chatSyncLoaded = false;
  state.ranqueadaSectionLoaded = false;
  state.folhinhaSectionLoaded = false;
  state.compararSectionLoaded = false;
  refreshAllData();
}

filterBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const period = btn.dataset.period;
    if (period === 'custom') {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentPeriod = 'custom';
      if (customDateRow) customDateRow.classList.add('visible');
      syncCustomDateInputs();
      return;
    }
    filterBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.currentPeriod = period;
    state.customStartDate = null;
    state.customEndDate = null;
    if (customDateRow) customDateRow.classList.remove('visible');
    applyPeriodChange();
  });
});

if (customDateApply) {
  customDateApply.addEventListener('click', () => {
    const start = customStartInput && customStartInput.value;
    const end = customEndInput && customEndInput.value;
    if (!start || !end) return;
    if (start > end) {
      alert('A data inicial deve ser anterior ou igual a data final.');
      return;
    }
    state.customStartDate = start;
    state.customEndDate = end;
    state.currentPeriod = 'custom';
    filterBtns.forEach(b => b.classList.toggle('active', b.dataset.period === 'custom'));
    applyPeriodChange();
  });
}

platformFilterBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    platformFilterBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.currentPlatform = btn.dataset.platform;
    if (state.currentPlatform !== 'all') {
      state.currentUserPlatform = state.currentPlatform;
    }
    if (state.currentUsername) {
      pushUserURL(state.currentUsername, state.currentUserPlatform || state.currentPlatform, state.currentPeriod);
    } else if (state.currentEmoteName) {
      pushEmoteURL(state.currentEmoteName);
    } else if (state.currentRanqueadaBoardId) {
      state.ranqueadaBoardPage = 1;
      pushRanqueadaBoardURL(state.currentRanqueadaBoardId, 1);
    } else if (['emotes', 'emotes-condensadas', 'roda', 'ranqueada', 'comparar', 'folhinha', 'timer'].includes(state.currentSection)) {
      pushSectionURL(state.currentSection);
      state.emotesSectionLoaded = false;
      state.emotesCondensadasLoaded = false;
      state.emoteRankingCache = null;
      state.smokeTimeLoaded = false;
      state.timerSectionLoaded = false;
      state.chatSyncLoaded = false;
      state.ranqueadaSectionLoaded = false;
      state.folhinhaSectionLoaded = false;
      state.compararSectionLoaded = false;
    } else {
      pushHomeURL();
    }
    refreshAllData();
  });
});

document.querySelectorAll('.ranqueada-card-title').forEach((btn) => {
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    const boardId = btn.dataset.boardId;
    const source = btn.dataset.boardSource || null;
    if (boardId) navigateToRanqueadaBoard(boardId, true, 1, source);
  });
});

if (ranqueadaBoardBackBtn) {
  ranqueadaBoardBackBtn.addEventListener('click', () => {
    navigateToSection(state.currentBoardSource === 'folhinha' ? 'folhinha' : 'ranqueada');
  });
}
if (ranqueadaBoardPrevBtn) {
  ranqueadaBoardPrevBtn.addEventListener('click', () => {
    if (state.ranqueadaBoardPage > 1) setRanqueadaBoardPage(state.ranqueadaBoardPage - 1);
  });
}
if (ranqueadaBoardNextBtn) {
  ranqueadaBoardNextBtn.addEventListener('click', () => {
    setRanqueadaBoardPage(state.ranqueadaBoardPage + 1);
  });
}

// Right panel is Top 10 only; other boards live in Ranqueada
function switchTab(tab) {
  state.currentTab = tab || 'top';
}

let chatActivityCounter = 0;
let pollCounter = 0;

function startAutoRefresh() {
  if (state.refreshInterval) clearInterval(state.refreshInterval);
  state.refreshInterval = setInterval(() => {
    pollCounter++;

    // Leaderboard: every 15s (always visible in right panel)
    if (pollCounter % 3 === 0) fetchLeaderboard();

    // User profile: every 60s (avoid flicker / load)
    if (state.currentUsername && pollCounter % 12 === 0) fetchUserStats(true);

    // Active chatters: every 10s
    if (pollCounter % 2 === 0) fetchActiveChatters();

    // Chat activity charts: every 30s, only while Home is visible
    chatActivityCounter++;
    if (!state.currentUsername && state.currentSection === 'home' && chatActivityCounter >= 6) {
      fetchChatActivity();
      fetchUniqueChatters();
      chatActivityCounter = 0;
    }
  }, 5000);
}
async function fetchRisingStars() {
  try {
    const response = await fetch(apiUrl('/stats/rising-stars', { limit: 10 }));
    if (!response.ok) throw new Error('API Error');

    const data = await response.json();
    renderRisingStars(data.entries);
  } catch (error) {
    console.error('Error loading rising stars:', error);
    risingList.textContent = '';
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'Erro ao carregar';
    risingList.appendChild(empty);
  }
}

async function fetchHourLeaders() {
  try {
    const response = await fetch(apiUrl('/stats/hour-leaders'));
    if (!response.ok) throw new Error('API Error');

    const data = await response.json();
    renderHourLeaders(data.entries);
  } catch (error) {
    console.error('Error loading hour leaders:', error);
    setLeaderboardError(hoursList);
  }
}

async function fetchTopWriters() {
  try {
    const response = await fetch(apiUrl('/stats/top-writers', { limit: 10 }));
    if (!response.ok) throw new Error('API Error');

    const data = await response.json();
    renderTopWriters(data.entries);
  } catch (error) {
    console.error('Error loading top writers:', error);
    setLeaderboardError(writersList);
  }
}
function renderDuasCaras(container, entries) {
  if (!container) return;
  container.textContent = '';
  if (!entries || !entries.length) {
    container.innerHTML = '<div class="empty-state">Nenhum dado</div>';
    return;
  }
  entries.forEach((entry) => {
    const item = document.createElement('div');
    item.className = 'leaderboard-entry';
    item.style.cursor = 'pointer';
    const names = (entry.known_usernames || []).join(', ');
    if (names) item.title = names;
    item.addEventListener('click', () => {
      if (entry.username) selectUser(entry.username, entry.platform || null);
    });

    const rank = document.createElement('span');
    rank.className = 'rank';
    rank.textContent = '#' + (entry.rank || '');

    const name = document.createElement('span');
    name.className = 'entry-name';
    setEntryName(name, entry.display_name || entry.username, entry.platform);

    const count = document.createElement('span');
    count.className = 'entry-count';
    const n = entry.name_count || 0;
    count.textContent = n + (n === 1 ? ' nome' : ' nomes');

    item.appendChild(rank);
    item.appendChild(name);
    item.appendChild(count);
    container.appendChild(item);
  });
}

function renderPererecoes(container, entries) {
  container.textContent = '';
  if (!entries || !entries.length) {
    container.innerHTML = '<div class="empty-state">Nenhum dado</div>';
    return;
  }
  entries.forEach((entry) => {
    const item = document.createElement('div');
    item.className = 'leaderboard-entry';
    item.style.cursor = 'pointer';
    item.addEventListener('click', () => {
      if (entry.username) selectUser(entry.username, entry.platform || null);
    });

    const breakdown = (entry.breakdown || [])
      .map((b) => b.board + ': #' + b.position + ' (+' + b.points + ')')
      .join('\n');
    if (breakdown) item.title = breakdown;

    const rank = document.createElement('span');
    rank.className = 'rank';
    rank.textContent = '#' + (entry.rank || '');

    const name = document.createElement('span');
    name.className = 'entry-name';
    setEntryName(name, entry.display_name || entry.username, entry.platform);

    const count = document.createElement('span');
    count.className = 'entry-count';
    count.textContent = (entry.points || 0).toLocaleString('pt-BR') + ' pts';

    item.appendChild(rank);
    item.appendChild(name);
    item.appendChild(count);
    container.appendChild(item);
  });
}

async function fetchPererecoes() {
  const el = document.getElementById('pererecoes-list');
  if (!el) return;
  try {
    const response = await fetch(apiUrl('/stats/pererecoes'));
    if (!response.ok) throw new Error('API Error');
    const data = await response.json();
    renderPererecoes(el, data.leaderboard);
  } catch (error) {
    console.error('Error fetching pererecoes:', error);
    setLeaderboardError(el);
  }
}

async function fetchEmoteCreators() {
  const el = document.getElementById('emote-creators-list');
  if (!el) return;
  try {
    const response = await fetch(apiUrl('/stats/emotes/creators'));
    if (response.ok) {
      const data = await response.json();
      renderSimpleRankList(el, data.creators, 'emote_count');
    }
  } catch (error) {
    console.error('Error fetching emote creators:', error);
  }
}

async function fetchDiversidade() {
  const el = document.getElementById('emote-diversidade-list');
  if (!el) return;
  try {
    const response = await fetch(apiUrl('/stats/emotes/diversidade', { period: state.currentPeriod }));
    if (response.ok) {
      const data = await response.json();
      renderSimpleRankList(el, data.leaderboard, 'unique_emotes');
    }
  } catch (error) {
    console.error('Error fetching diversidade:', error);
  }
}

async function fetchFamosinhos() {
  if (!famosinhosList) return;
  try {
    const response = await fetch(apiUrl('/stats/famosinhos'));
    if (!response.ok) throw new Error('API Error');
    const data = await response.json();
    renderSimpleRankList(famosinhosList, data.leaderboard, 'count');
  } catch (error) {
    console.error('Error fetching famosinhos:', error);
    setLeaderboardError(famosinhosList);
  }
}

async function fetchFolhinha() {
  if (!folhinhaList) return;
  try {
    const response = await fetch(apiUrl('/stats/folhinha'));
    if (!response.ok) throw new Error('API Error');
    const data = await response.json();
    renderSimpleRankList(folhinhaList, data.leaderboard, 'count');
  } catch (error) {
    console.error('Error fetching folhinha:', error);
    setLeaderboardError(folhinhaList);
  }
}
function renderRisingStars(entries, container) {
  const target = container || risingList;
  if (!target) return;
  target.textContent = '';
  if (!entries || entries.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'Nenhum dado';
    target.appendChild(empty);
    return;
  }

  entries.forEach(entry => {
    const entryPlatform = entry.platform || 'twitch';
    const isPositive = entry.growth_percent >= 0;
    const growthDisplay = isPositive ? '+' + entry.growth_percent.toFixed(0) + '%' : entry.growth_percent.toFixed(0) + '%';

    const div = document.createElement('div');
    div.className = 'leaderboard-entry';
    div.onclick = () => selectUser(entry.username, entryPlatform);

    const rankSpan = document.createElement('span');
    rankSpan.className = 'rank';
    rankSpan.textContent = '#' + entry.rank;

    const nameSpan = document.createElement('span');
    nameSpan.className = 'entry-name';
    setEntryName(nameSpan, entry.display_name, entryPlatform);

    const growthSpan = document.createElement('span');
    growthSpan.className = 'growth-badge' + (isPositive ? '' : ' negative');
    growthSpan.textContent = growthDisplay;

    div.appendChild(rankSpan);
    div.appendChild(nameSpan);
    div.appendChild(growthSpan);
    target.appendChild(div);
  });
}

function renderHourLeaders(entries, container) {
  const target = container || hoursList;
  if (!target) return;
  target.textContent = '';
  if (!entries || entries.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'Nenhum dado';
    target.appendChild(empty);
    return;
  }

  const hourMap = {};
  let maxCount = 1;
  entries.forEach(e => {
    hourMap[e.hour] = e;
    const n = e.message_count != null ? e.message_count : e.count;
    if (n > maxCount) maxCount = n;
  });

  for (let hour = 0; hour < 24; hour++) {
    const entry = hourMap[hour];
    const div = document.createElement('div');
    div.className = 'hour-heatmap-cell';
    const msgCount = entry
      ? (entry.message_count != null ? entry.message_count : entry.count) || 0
      : 0;
    const intensity = entry ? Math.max(0.12, msgCount / maxCount) : 0.05;
    div.style.background = 'rgba(46, 204, 113, ' + intensity.toFixed(2) + ')';
    if (entry) {
      div.title = hour + 'h: ' + entry.display_name + ' (' + msgCount + ')';
      div.onclick = () => selectUser(entry.username, entry.platform || 'twitch');
    }

    const h = document.createElement('div');
    h.className = 'hh-hour';
    h.textContent = hour + 'h';
    div.appendChild(h);

    const n = document.createElement('div');
    n.className = 'hh-name';
    n.textContent = entry ? entry.display_name : '—';
    div.appendChild(n);

    target.appendChild(div);
  }
}

function renderTopWriters(entries, container) {
  const target = container || writersList;
  if (!target) return;
  target.textContent = '';
  if (!entries || entries.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'Nenhum dado';
    target.appendChild(empty);
    return;
  }

  entries.forEach(entry => {
    const entryPlatform = entry.platform || 'twitch';
    const div = document.createElement('div');
    div.className = 'writer-entry';
    div.onclick = () => selectUser(entry.username, entryPlatform);

    const rankSpan = document.createElement('span');
    rankSpan.className = 'rank';
    rankSpan.textContent = '#' + entry.rank;

    const nameSpan = document.createElement('span');
    nameSpan.className = 'entry-name';
    setEntryName(nameSpan, entry.display_name, entryPlatform);

    const avgSpan = document.createElement('span');
    avgSpan.className = 'writer-avg';
    avgSpan.textContent = entry.score.toFixed(2);

    div.appendChild(rankSpan);
    div.appendChild(nameSpan);
    div.appendChild(avgSpan);
    target.appendChild(div);
  });
}
let top10Collapsed = false;
try {
  top10Collapsed = localStorage.getItem('pererecos-top10-collapsed') === '1';
} catch (e) { /* ignore */ }
function applyTop10Collapsed() {
  if (!top10Card || !top10Toggle) return;
  top10Card.classList.toggle('is-collapsed', top10Collapsed);
  top10Toggle.textContent = top10Collapsed ? 'Mostrar' : 'Ocultar';
  top10Toggle.setAttribute('aria-expanded', top10Collapsed ? 'false' : 'true');
}
applyTop10Collapsed();
if (top10Toggle) {
  top10Toggle.addEventListener('click', () => {
    top10Collapsed = !top10Collapsed;
    try {
      localStorage.setItem('pererecos-top10-collapsed', top10Collapsed ? '1' : '0');
    } catch (e) { /* ignore */ }
    applyTop10Collapsed();
  });
}

async function refreshSidebarContext(section) {
  const note = document.getElementById('note-top');
  const titleEl = document.getElementById('top10-title');
  if (!titleEl || !leaderboard) return;

  if (section === 'folhinha') {
    state.sidebarContextMode = 'bonks';
    titleEl.textContent = 'Top Bonkadores';
    if (note) note.textContent = 'Quem mais usou ?bonk no período (' + getPeriodLabel() + ')';
    // Filled by Folhinha tab onLoaded — only show placeholder if empty
    if (!leaderboard.querySelector('.leaderboard-entry')) {
      leaderboard.innerHTML = '<div class="empty-state loading">Carregando...</div>';
    }
    return;
  }
  if (section === 'emotes' || section === 'emotes-condensadas') {
    state.sidebarContextMode = 'emotes';
    titleEl.textContent = 'Top Emotes';
    if (note) note.textContent = 'Emotes mais usados no período (' + getPeriodLabel() + ')';
    if (!leaderboard.querySelector('.leaderboard-entry')) {
      leaderboard.innerHTML = '<div class="empty-state loading">Carregando...</div>';
    }
    return;
  }
  state.sidebarContextMode = 'messages';
  titleEl.textContent = 'Top 10';
  if (note) {
    note.textContent = 'Quem mais mandou mensagens no periodo (' + getPeriodLabel() + ')';
  }
  fetchLeaderboard();
}

// Subathon header timer: tick from ends_at + server_now clock offset
(function initSubathonTimer() {
  const labelEl = document.getElementById('subathon-timer-label');
  const valueEl = document.getElementById('subathon-timer-value');
  const wrapEl = document.getElementById('subathon-timer');
  if (!labelEl || !valueEl || !wrapEl) return;

  let endsAtMs = null;
  let offsetMs = 0;
  let mode = 'untilStart';
  let stale = false;
  let remainingFallback = null;
  let tickTimer = null;
  let syncTimer = null;

  function formatCountdown(totalSeconds) {
    const s = Math.max(0, Math.floor(totalSeconds));
    const days = Math.floor(s / 86400);
    const hours = Math.floor((s % 86400) / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = s % 60;
    const hms =
      String(hours).padStart(2, '0') + ':' +
      String(mins).padStart(2, '0') + ':' +
      String(secs).padStart(2, '0');
    if (days > 0) return days + 'd ' + hms;
    const totalHours = Math.floor(s / 3600);
    return (
      String(totalHours) + ':' +
      String(mins).padStart(2, '0') + ':' +
      String(secs).padStart(2, '0')
    );
  }

  function remainingNow() {
    if (endsAtMs != null) {
      return Math.max(0, Math.floor((endsAtMs - (Date.now() + offsetMs)) / 1000));
    }
    return remainingFallback;
  }

  function render() {
    wrapEl.dataset.mode = mode;
    wrapEl.classList.toggle('ended', mode === 'ended');
    wrapEl.dataset.stale = stale ? 'true' : 'false';

    if (mode === 'untilStart') {
      labelEl.textContent = 'Subathon começa em';
    } else if (mode === 'paused') {
      labelEl.textContent = 'Subathon pausada';
    } else if (mode === 'locked') {
      labelEl.textContent = 'Subathon bloqueada';
    } else if (mode === 'ended') {
      labelEl.textContent = 'Subathon encerrada';
    } else if (mode === 'unavailable') {
      labelEl.textContent = 'Timer indisponível';
    } else {
      labelEl.textContent = 'Horas de live restantes';
    }

    const rem = remainingNow();
    if (rem == null) {
      valueEl.textContent = '--:--:--';
      return;
    }
    if (mode === 'ended' || rem <= 0 && mode !== 'untilStart') {
      valueEl.textContent = '0:00:00';
      wrapEl.classList.add('ended');
      return;
    }
    if (mode === 'untilStart' && rem <= 0) {
      labelEl.textContent = 'Aguardando a live';
      valueEl.textContent = '—';
      return;
    }
    let text = formatCountdown(rem);
    if (stale) {
      text += ' · desatualizado';
    }
    valueEl.textContent = text;
  }

  function tick() {
    if (mode === 'paused' || mode === 'locked') {
      render();
      return;
    }
    render();
  }

  async function syncFromApi() {
    try {
      const res = await fetch(API_BASE + '/subathon/timer');
      if (!res.ok) throw new Error('timer http ' + res.status);
      const data = await res.json();
      mode = data.mode || 'untilStart';
      stale = !!data.stale;
      if (data.server_now) {
        offsetMs = Date.parse(data.server_now) - Date.now();
      }
      if (data.ends_at) {
        endsAtMs = Date.parse(data.ends_at);
        remainingFallback = null;
      } else {
        endsAtMs = null;
        remainingFallback = Math.max(0, Number(data.remaining_seconds) || 0);
      }
      render();
    } catch (err) {
      console.error('Subathon timer sync failed', err);
      // Keep ticking from last known ends_at rather than blanking out.
      render();
    }
  }

  syncFromApi();
  tickTimer = setInterval(tick, 1000);
  syncTimer = setInterval(syncFromApi, 20000);
})();

// Username history

usernameHistoryBtn?.addEventListener('click', (e) => {
  e.stopPropagation();
  usernameHistoryPopup?.classList.toggle('open');
});

document.addEventListener('click', (e) => {
  if (!e.target.closest('.name-wrapper')) {
    usernameHistoryPopup?.classList.remove('open');
  }
});
async function fetchFolhinhaCommands() {
  const el = document.getElementById('folhinha-commands-list');
  if (!el) return;
  try {
    const response = await fetch(apiUrl('/stats/folhinha/commands'));
    if (!response.ok) throw new Error('API');
    const data = await response.json();
    const cmds = (data.commands || []).slice(0, 10);
    el.textContent = '';
    if (!cmds.length) {
      el.innerHTML = '<div class="empty-state">Nenhum comando</div>';
      return;
    }
    cmds.forEach((c) => {
      const row = document.createElement('div');
      row.className = 'leaderboard-entry';
      row.innerHTML = '<span class="rank"></span><span class="entry-name"></span><span class="entry-count"></span>';
      row.querySelector('.rank').textContent = '#' + c.rank;
      row.querySelector('.entry-name').textContent = '?' + c.command;
      row.querySelector('.entry-count').textContent = (c.count || 0).toLocaleString('pt-BR');
      el.appendChild(row);
    });
  } catch (e) {
    console.error(e);
    setLeaderboardError(el);
  }
}

async function fetchEmoteWeather() {
  const risingEl = document.getElementById('emote-weather-rising');
  const fallingEl = document.getElementById('emote-weather-falling');
  if (!risingEl || !fallingEl) return;
  try {
    const response = await fetch(apiUrl('/stats/emotes/weather'));
    if (!response.ok) throw new Error('API');
    const data = await response.json();
    const renderWeather = (container, rows) => {
      container.textContent = '';
      if (!rows || !rows.length) {
        container.innerHTML = '<div class="empty-state">Nenhum dado</div>';
        return;
      }
      rows.slice(0, 10).forEach((e, i) => {
        const row = document.createElement('div');
        row.className = 'leaderboard-entry';
        row.style.cursor = 'pointer';
        row.addEventListener('click', () => navigateToEmote(e.emote_name));
        const delta = e.delta != null ? e.delta : ((e.count_now || 0) - (e.count_prev || 0));
        const pct = e.delta_pct != null ? e.delta_pct : null;

        const rank = document.createElement('span');
        rank.className = 'rank';
        rank.textContent = '#' + (i + 1);

        const name = document.createElement('span');
        name.className = 'entry-name';
        if (e.emote_id) {
          const img = document.createElement('img');
          img.src = 'https://cdn.7tv.app/emote/' + e.emote_id + '/1x.webp';
          img.alt = e.emote_name;
          img.width = 20;
          img.height = 20;
          img.loading = 'lazy';
          img.style.flexShrink = '0';
          name.appendChild(img);
        }
        const nameText = document.createElement('span');
        nameText.className = 'name-text';
        nameText.textContent = e.emote_name;
        nameText.title = e.emote_name;
        name.appendChild(nameText);

        const count = document.createElement('span');
        count.className = 'entry-count';
        const deltaLabel = (delta >= 0 ? '+' : '') + delta
          + (pct != null ? ' (' + (pct >= 0 ? '+' : '') + pct + '%)' : '');
        count.textContent = deltaLabel;
        count.title = deltaLabel;

        row.appendChild(rank);
        row.appendChild(name);
        row.appendChild(count);
        container.appendChild(row);
      });
    };
    renderWeather(risingEl, data.rising);
    renderWeather(fallingEl, data.falling);
  } catch (e) {
    console.error(e);
    setLeaderboardError(risingEl);
    setLeaderboardError(fallingEl);
  }
}
async function copyCurrentLink(kind) {
  try {
    await navigator.clipboard.writeText(window.location.href);
    const idMap = {
      emote: 'copy-emote-link',
      user: 'copy-user-link',
      board: 'copy-ranqueada-board-link',
    };
    const btn = document.getElementById(idMap[kind] || 'copy-user-link');
    if (btn) {
      const prev = btn.textContent;
      btn.textContent = 'Copiado!';
      setTimeout(() => { btn.textContent = prev; }, 1500);
    }
  } catch (e) { console.error(e); }
}

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  ['export-modal', 'feedback-modal', 'ribbits-modal'].forEach((id) => {
    const el = document.getElementById(id);
    if (el && el.classList.contains('visible')) el.classList.remove('visible');
  });
});

document.getElementById('copy-user-link')?.addEventListener('click', () => copyCurrentLink('user'));
document.getElementById('copy-emote-link')?.addEventListener('click', () => copyCurrentLink('emote'));
document.getElementById('copy-ranqueada-board-link')?.addEventListener('click', () => copyCurrentLink('board'));
document.getElementById('compare-btn')?.addEventListener('click', runCompare);
document.getElementById('compare-user2')?.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') runCompare();
});

window.addEventListener('resize', scheduleEqualizeBoardCards);
/** Wire late-bound cross-module callbacks */
Object.assign(hooks, {
  selectUser,
  navigateToEmote,
  navigateToSection,
  navigateToRanqueadaBoard,
  hideRanqueadaBoardView,
  updateNavActive,
  showGeneralView,
  loadSectionData,
  refreshSidebarContext,
  updatePeriodLabels,
  syncCustomDateInputs,
  renderExportNerdEmote,
  refreshEmoteNotes,
  renderTopEmotes,
  renderEmotePositionBar,
  renderMessageWithEmotes,
  searchUsersForAutocomplete,
  loadEmotesSection,
  loadEmotesCondensadasSection,
  loadRodaSection,
  loadTimerSection,
  loadRanqueadaSection,
  loadFolhinhaSection,
  loadCompararSection,
  loadCoreStats,
  loadChartStats,
  loadInitialData,
  fetchUserStats,
  fetch7TVEmotes,
  loadRandomNavEmoteIcon,
  renderSimpleRankList,
  showError,
  hideError,
  pushHomeURL,
  pushSectionURL,
  pushUserURL,
  buildFilterQuery,
  applyFiltersFromState,
  getParamsFromURL,
  fetchEmoteRanking,
  fetchChatTopEmotes,
  fetchLeastUsedEmotes,
  fetchChatEmotePositions,
  fetchSmokeTime,
  fetchActiveChatters,
  fetchChatActivity,
  fetchUniqueChatters,
  fetchOverallActivity,
  fetchLeaderboard,
  filterActiveChatters,
  renderFilteredEmoteRanking,
  openExportModal,
  closeExportModal,
  openRibbits,
  loadRibbit,
  renderSidebarTopEmotes,
  updateHomeNavIcon,
  applyTop10Collapsed,
  startMessageExport,
  fetchUsernameHistory,
  runCompare,
  hideAutocomplete,
  renderLeaderboard,
  renderActiveChatters,
  scheduleEqualizeBoardCards,
  showSectionPanel,
  searchUser,
  updateLeaderboardSelection,
  parseAppPath,
  applyRoute,
  initFromURL,
  refreshAllData,
  applyPeriodChange,
  switchTab,
  startAutoRefresh,
});

// Boot
try {
  initFromURL();
  updateHomeNavIcon();
  startAutoRefresh();
} catch (err) {
  console.error('App boot failed', err);
}
