import { state, BASE_PATH, DEFAULT_TITLE, RESERVED_SECTIONS } from './state.js';
import { updatePeriodLabels, hideError } from './shared.js';
import { usernameInput, chatGeralBtn, generalView, statsSection, leaderboard, emoteView, filterBtns, platformFilterBtns, customDateRow, customStartInput, customEndInput } from './dom.js';
import { hooks } from './hooks.js';

export function showGeneralView(updateUrl = true, section = 'home') {
  if (state.userStatsAbort) {
    state.userStatsAbort.abort();
    state.userStatsAbort = null;
  }
  state.currentUsername = '';
  state.currentUserPlatform = null;
  state.currentEmoteName = '';
  hooks.hideRanqueadaBoardView();
  statsSection.classList.remove('visible');
  if (emoteView) emoteView.classList.remove('visible');
  generalView.classList.remove('hidden');
  chatGeralBtn.classList.add('active');
  hideError();
  usernameInput.value = '';
  updateLeaderboardSelection();
  showSectionPanel(section);
  if (updateUrl) {
    if (section === 'home') pushHomeURL();
    else pushSectionURL(section);
  }
  loadSectionData(section);
}

export function showSectionPanel(section) {
  if (section === 'emotes-condensadas') section = 'emotes';
  const valid = ['emotes', 'roda', 'ranqueada', 'comparar', 'folhinha', 'timer'];
  state.currentSection = valid.includes(section) ? section : 'home';
  const homeEl = document.getElementById('section-home');
  const emotesEl = document.getElementById('section-emotes');
  const condensadasEl = document.getElementById('section-emotes-condensadas');
  const rodaEl = document.getElementById('section-roda');
  const timerEl = document.getElementById('section-timer');
  const ranqueadaEl = document.getElementById('section-ranqueada');
  const compararEl = document.getElementById('section-comparar');
  const folhinhaEl = document.getElementById('section-folhinha');
  if (homeEl) homeEl.classList.toggle('hidden', state.currentSection !== 'home');
  if (emotesEl) emotesEl.classList.toggle('hidden', state.currentSection !== 'emotes');
  if (condensadasEl) condensadasEl.classList.add('hidden');
  if (rodaEl) rodaEl.classList.toggle('hidden', state.currentSection !== 'roda');
  if (timerEl) timerEl.classList.toggle('hidden', state.currentSection !== 'timer');
  if (ranqueadaEl) ranqueadaEl.classList.toggle('hidden', state.currentSection !== 'ranqueada');
  if (compararEl) compararEl.classList.toggle('hidden', state.currentSection !== 'comparar');
  if (folhinhaEl) folhinhaEl.classList.toggle('hidden', state.currentSection !== 'folhinha');
  updateNavActive('section', state.currentSection);
  if (state.currentSection === 'home') document.title = DEFAULT_TITLE;
  else if (state.currentSection === 'emotes') document.title = 'Emotes - Pererecos Stats';
  else if (state.currentSection === 'roda') document.title = 'Roda - Pererecos Stats';
  else if (state.currentSection === 'timer') document.title = 'Timer - Pererecos Stats';
  else if (state.currentSection === 'ranqueada') document.title = 'Ranqueada - Pererecos Stats';
  else if (state.currentSection === 'comparar') document.title = 'Comparar - Pererecos Stats';
  else if (state.currentSection === 'folhinha') document.title = 'Folhinha - Pererecos Stats';
}

export function updateNavActive(mode, section) {
  document.querySelectorAll('.stats-nav-item').forEach(btn => {
    const isActive = mode !== 'user' && btn.dataset.section === (section || 'home');
    btn.classList.toggle('active', isActive);
  });
}

export function loadSectionData(section) {
  if (section === 'emotes-condensadas') section = 'emotes';
  // Set rail labels first (no extra fetches) so section loaders can fill data
  hooks.refreshSidebarContext(section === 'home' ? 'home' : section);
  if (section === 'emotes') hooks.loadEmotesSection();
  else if (section === 'roda') hooks.loadRodaSection();
  else if (section === 'timer') hooks.loadTimerSection();
  else if (section === 'ranqueada') hooks.loadRanqueadaSection();
  else if (section === 'folhinha') hooks.loadFolhinhaSection();
  else if (section === 'comparar') hooks.loadCompararSection();
  else {
    hooks.loadCoreStats();
    setTimeout(() => hooks.loadChartStats(), 300);
  }
}

export function navigateToSection(section, updateUrl = true) {
  showGeneralView(updateUrl, section);
}

export async function searchUser() {
  const username = usernameInput.value.trim();
  if (!username) {
    showGeneralView();
    updateLeaderboardSelection();
    return;
  }

  selectUser(username, state.currentPlatform !== 'all' ? state.currentPlatform : null);
}
export function updateLeaderboardSelection() {
  document.querySelectorAll('.leaderboard-entry').forEach(el => {
    const matchesUser = state.currentUsername && el.dataset.username === state.currentUsername.toLowerCase();
    const matchesPlatform = !state.currentUserPlatform || el.dataset.platform === state.currentUserPlatform;
    el.classList.toggle('selected', matchesUser && matchesPlatform);
  });
}

export function selectUser(username, platform = null, updateUrl = true) {
  usernameInput.value = username;
  state.currentUsername = username;
  state.currentEmoteName = '';
  state.currentUserPlatform = platform || (state.currentPlatform !== 'all' ? state.currentPlatform : null);
  hooks.hideRanqueadaBoardView();
  hideError();
  generalView.classList.add('hidden');
  if (emoteView) emoteView.classList.remove('visible');
  chatGeralBtn.classList.remove('active');
  updateNavActive('user');
  if (updateUrl) {
    pushUserURL(username, state.currentUserPlatform || state.currentPlatform, state.currentPeriod);
  }
  hooks.fetchUserStats();
  updateLeaderboardSelection();
}

export function parseAppPath() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/';
  if (path === BASE_PATH || path === BASE_PATH + '/') {
    return { mode: 'home' };
  }
  if (!path.startsWith(BASE_PATH + '/')) {
    return { mode: 'home' };
  }
  const rest = path.slice((BASE_PATH + '/').length);
  if (!rest) return { mode: 'home' };

  const parts = rest.split('/').filter(Boolean);
  if (parts.length === 1) {
    let decoded;
    try {
      decoded = decodeURIComponent(parts[0]);
    } catch (e) {
      decoded = parts[0];
    }
    const lower = decoded.toLowerCase();
    if (RESERVED_SECTIONS.has(lower)) {
      return { mode: 'section', section: lower };
    }
    return { mode: 'user', username: decoded };
  }

  if (parts.length === 2 && parts[0].toLowerCase() === 'emotes') {
    let second;
    try {
      second = decodeURIComponent(parts[1]);
    } catch (e) {
      second = parts[1];
    }
    if (second.toLowerCase() === 'condensadas') {
      return { mode: 'section', section: 'emotes-condensadas' };
    }
    return { mode: 'emote', emoteName: second };
  }

  if (parts.length === 2 && (parts[0].toLowerCase() === 'ranqueada' || parts[0].toLowerCase() === 'folhinha')) {
    let boardId;
    try {
      boardId = decodeURIComponent(parts[1]);
    } catch (e) {
      boardId = parts[1];
    }
    return {
      mode: 'ranqueada-board',
      boardId,
      boardSource: parts[0].toLowerCase() === 'folhinha' ? 'folhinha' : 'ranqueada',
    };
  }

  return { mode: 'home' };
}

export function getParamsFromURL() {
  const params = new URLSearchParams(window.location.search);
  return {
    platform: params.get('platform') || 'all',
    period: params.get('period') || 'all',
    start_date: params.get('start_date') || null,
    end_date: params.get('end_date') || null,
    page: parseInt(params.get('page') || '1', 10) || 1,
  };
}

export function buildFilterQuery(platform, period) {
  const params = new URLSearchParams();
  if (platform && platform !== 'all') params.set('platform', platform);
  if (period && period !== 'all') params.set('period', period);
  if (period === 'custom' && state.customStartDate && state.customEndDate) {
    params.set('start_date', state.customStartDate);
    params.set('end_date', state.customEndDate);
  }
  const qs = params.toString();
  return qs ? '?' + qs : '';
}

export function pushUserURL(username, platform, period) {
  const url = BASE_PATH + '/' + encodeURIComponent(username) + buildFilterQuery(platform, period);
  history.pushState({ username, platform, period, mode: 'user' }, '', url);
}

export function pushHomeURL() {
  const url = BASE_PATH + '/' + buildFilterQuery(state.currentPlatform, state.currentPeriod);
  history.pushState({ home: true, mode: 'home', section: 'home', platform: state.currentPlatform, period: state.currentPeriod }, '', url);
}

export function pushSectionURL(section) {
  let pathSeg;
  if (section === 'emotes-condensadas') {
    pathSeg = 'emotes/condensadas';
  } else {
    pathSeg = section;
  }
  const url = BASE_PATH + '/' + pathSeg + buildFilterQuery(state.currentPlatform, state.currentPeriod);
  history.pushState({
    mode: 'section',
    section,
    platform: state.currentPlatform,
    period: state.currentPeriod,
  }, '', url);
}

export function applyFiltersFromState(filterState) {
  if (filterState.platform) {
    state.currentPlatform = filterState.platform;
    platformFilterBtns.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.platform === filterState.platform);
    });
    if (state.currentPlatform !== 'all') {
      state.currentUserPlatform = state.currentPlatform;
    }
  }
  if (filterState.period && filterState.period !== 'undefined' && filterState.period !== 'null') {
    state.currentPeriod = filterState.period;
    filterBtns.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.period === filterState.period);
    });
  } else if (!state.currentPeriod || state.currentPeriod === 'undefined') {
    state.currentPeriod = 'all';
  }
  if (filterState.period === 'custom' && filterState.start_date && filterState.end_date) {
    state.customStartDate = filterState.start_date;
    state.customEndDate = filterState.end_date;
    if (customDateRow) customDateRow.classList.add('visible');
    hooks.syncCustomDateInputs();
    if (customStartInput) customStartInput.value = state.customStartDate;
    if (customEndInput) customEndInput.value = state.customEndDate;
  } else if (filterState.period && filterState.period !== 'custom') {
    state.customStartDate = null;
    state.customEndDate = null;
    if (customDateRow) customDateRow.classList.remove('visible');
  }
  updatePeriodLabels();
}

export function applyRoute(route, updateUrl = false) {
  const params = getParamsFromURL();
  if (route.mode === 'user') {
    applyFiltersFromState(params);
    selectUser(route.username, params.platform !== 'all' ? params.platform : null, updateUrl);
    return;
  }
  if (route.mode === 'emote') {
    applyFiltersFromState(params);
    hooks.navigateToEmote(route.emoteName, updateUrl);
    return;
  }
  if (route.mode === 'ranqueada-board') {
    applyFiltersFromState(params);
    hooks.navigateToRanqueadaBoard(route.boardId, updateUrl, params.page || 1, route.boardSource || null);
    return;
  }
  if (route.mode === 'section') {
    applyFiltersFromState(params);
    navigateToSection(route.section, updateUrl);
    return;
  }
  applyFiltersFromState(params);
  navigateToSection('home', updateUrl);
}

window.addEventListener('popstate', (event) => {
  if (event.state) {
    if (event.state.mode === 'ranqueada-board' || event.state.boardId) {
      applyFiltersFromState(event.state);
      hooks.navigateToRanqueadaBoard(
        event.state.boardId,
        false,
        event.state.page || 1,
        event.state.boardSource || null
      );
      return;
    }
    if (event.state.mode === 'emote' || event.state.emoteName) {
      applyFiltersFromState(event.state);
      hooks.navigateToEmote(event.state.emoteName, false);
      return;
    }
    if (event.state.mode === 'user' || event.state.username) {
      applyFiltersFromState(event.state);
      usernameInput.value = event.state.username;
      state.currentUsername = event.state.username;
      state.currentEmoteName = '';
      hooks.hideRanqueadaBoardView();
      state.currentUserPlatform = event.state.platform && event.state.platform !== 'all'
        ? event.state.platform
        : (state.currentPlatform !== 'all' ? state.currentPlatform : null);
      generalView.classList.add('hidden');
      if (emoteView) emoteView.classList.remove('visible');
      chatGeralBtn.classList.remove('active');
      updateNavActive('user');
      hooks.fetchUserStats(false);
      updateLeaderboardSelection();
      return;
    }
    if (event.state.mode === 'section' || event.state.section) {
      applyFiltersFromState(event.state);
      navigateToSection(event.state.section || 'home', false);
      return;
    }
    if (event.state.home || event.state.mode === 'home') {
      applyFiltersFromState(event.state);
      navigateToSection('home', false);
      return;
    }
  }
  applyRoute(parseAppPath(), false);
});

export function initFromURL() {
  const route = parseAppPath();
  const params = getParamsFromURL();
  applyFiltersFromState(params);

  if (route.mode === 'user') {
    usernameInput.value = route.username;
    state.currentUsername = route.username;
    state.currentUserPlatform = params.platform !== 'all' ? params.platform : null;
    generalView.classList.add('hidden');
    if (emoteView) emoteView.classList.remove('visible');
    chatGeralBtn.classList.remove('active');
    updateNavActive('user');
    history.replaceState(
      { mode: 'user', username: route.username, platform: params.platform, period: params.period },
      '',
      window.location.pathname + window.location.search
    );
    hooks.fetch7TVEmotes();
    hooks.loadCoreStats();
    hooks.loadRandomNavEmoteIcon();
    hooks.fetchUserStats();
    updateLeaderboardSelection();
    return;
  }

  if (route.mode === 'emote') {
    history.replaceState(
      { mode: 'emote', emoteName: route.emoteName, platform: params.platform, period: params.period },
      '',
      window.location.pathname + window.location.search
    );
    hooks.fetch7TVEmotes();
    hooks.loadCoreStats();
    hooks.loadRandomNavEmoteIcon();
    hooks.navigateToEmote(route.emoteName, false);
    return;
  }

  if (route.mode === 'ranqueada-board') {
    history.replaceState(
      {
        mode: 'ranqueada-board',
        boardId: route.boardId,
        page: params.page || 1,
        boardSource: route.boardSource || 'ranqueada',
        platform: params.platform,
        period: params.period,
      },
      '',
      window.location.pathname + window.location.search
    );
    hooks.fetch7TVEmotes();
    hooks.loadCoreStats();
    hooks.loadRandomNavEmoteIcon();
    hooks.navigateToRanqueadaBoard(route.boardId, false, params.page || 1, route.boardSource || null);
    return;
  }

  const section = route.mode === 'section' ? route.section : 'home';
  chatGeralBtn.classList.add('active');
  let initPath;
  if (section === 'home') {
    initPath = BASE_PATH + '/';
  } else if (section === 'emotes-condensadas') {
    initPath = BASE_PATH + '/emotes/condensadas';
  } else {
    initPath = BASE_PATH + '/' + section;
  }
  history.replaceState(
    { mode: section === 'home' ? 'home' : 'section', section, home: section === 'home', platform: params.platform, period: params.period },
    '',
    initPath + buildFilterQuery(params.platform, params.period)
  );
  hooks.fetch7TVEmotes();
  hooks.loadRandomNavEmoteIcon();
  showSectionPanel(section);
  if (section === 'home') {
    hooks.loadInitialData();
  } else {
    hooks.loadCoreStats();
    loadSectionData(section);
  }
}
const HOME_ICON_DAY = 'https://cdn.7tv.app/emote/01FT0SJFNR0001M6SADSSJ9P4Q/2x.webp';
const HOME_ICON_NIGHT = 'https://cdn.7tv.app/emote/01GQWT7FJ0000DRYKWFK0ZNX75/2x.webp';

export function updateHomeNavIcon() {
  const icon = document.getElementById('nav-home-icon');
  if (!icon) return;
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Sao_Paulo', hour: 'numeric', minute: 'numeric', hour12: false,
  }).formatToParts(new Date());
  const hour = Number(parts.find((p) => p.type === 'hour').value) % 24;
  const minute = Number(parts.find((p) => p.type === 'minute').value);
  const minutes = hour * 60 + minute;
  const isDay = minutes >= 360 && minutes <= 1080; // 06:00 ate 18:00
  icon.src = isDay ? HOME_ICON_DAY : HOME_ICON_NIGHT;
  icon.title = isDay ? 'Life' : 'RealLife';
}

updateHomeNavIcon();
setInterval(updateHomeNavIcon, 60 * 1000);
