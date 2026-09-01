const API_BASE = '/pererecos-stats-subathon/api/v1';
    const BASE_PATH = '/pererecos-stats-subathon';
    const DEFAULT_TITLE = 'Pererecos Stats Subathon';
    const RESERVED_SECTIONS = new Set(['emotes', 'roda', 'ranqueada', 'comparar', 'folhinha']);
    const SMOKE_TIME_EMOTE_ID = '01FEHRN6PR000AEZ0QNPT4F4MF';

    let currentUsername = '';
    let currentPeriod = 'all';
    let currentPlatform = 'all';
    let currentUserPlatform = null;
    let currentTab = 'top';
    let currentSection = 'home'; // 'home' | 'emotes' | 'emotes-condensadas' | 'roda' | 'ranqueada'
    let refreshInterval = null;
    let searchTimeout = null;
    let selectedAutocompleteIndex = -1;
    let userStatsAbort = null;
    let emotesSectionLoaded = false;
    let emotesCondensadasLoaded = false;
    let smokeTimeLoaded = false;
    let ranqueadaSectionLoaded = false;
    let folhinhaSectionLoaded = false;
    let compararSectionLoaded = false;
    let sidebarContextMode = 'messages'; // messages | bonks | emotes
    let emoteRankingCache = null;
    let emoteRankingFilter = '';
    let emoteRankingVisible = 50;
    const EMOTE_RANKING_PAGE = 50;

    const usernameInput = document.getElementById('username-input');
    const searchBtn = document.getElementById('search-btn');
    const chatGeralBtn = document.getElementById('chat-geral-btn');
    const autocompleteDropdown = document.getElementById('autocomplete-dropdown');
    const generalView = document.getElementById('general-view');
    const statsSection = document.getElementById('stats-section');
    const userStatusEl = document.getElementById('user-status');
    const displayNameEl = document.getElementById('display-name');
    const totalMessagesEl = document.getElementById('total-messages');
    const percentileText = document.getElementById('percentile-text');
    const lastMessageText = document.getElementById('last-message-text');
    const peakHoursText = document.getElementById('peak-hours-text');
    const favoriteHourText = document.getElementById('favorite-hour-text');
    const rankingsGrid = document.getElementById('rankings-grid');
    const hourlyChart = document.getElementById('hourly-chart');
    const messagesList = document.getElementById('messages-list');
    const rivalInfo = document.getElementById('rival-info');
    const repliesList = document.getElementById('replies-list');
    const leaderboard = document.getElementById('leaderboard');
    const risingList = document.getElementById('rising-list');
    const hoursList = document.getElementById('hours-list');
    const writersList = document.getElementById('writers-list');
    const famosinhosList = document.getElementById('famosinhos-list');
    const folhinhaList = document.getElementById('folhinha-list');
    const emoteView = document.getElementById('emote-view');
    const emoteSearchInput = document.getElementById('emote-search-input');
    const emoteAutocomplete = document.getElementById('emote-autocomplete');
    let currentEmoteName = '';
    let currentRanqueadaBoardId = '';
    let currentBoardSource = 'ranqueada'; // 'ranqueada' | 'folhinha'
    let ranqueadaBoardEntries = [];
    let ranqueadaBoardPage = 1;
    let ranqueadaBoardMeta = null;
    let emoteSearchTimeout = null;
    let selectedEmoteAutocompleteIndex = -1;
    const ranqueadaBoardView = document.getElementById('ranqueada-board-view');
    const ranqueadaBoardTitleEl = document.getElementById('ranqueada-board-title');
    const ranqueadaBoardDescEl = document.getElementById('ranqueada-board-description');
    const ranqueadaBoardListEl = document.getElementById('ranqueada-board-full-list');
    const ranqueadaBoardPagerEl = document.getElementById('ranqueada-board-pager');
    const ranqueadaBoardPageLabel = document.getElementById('ranqueada-board-page-label');
    const ranqueadaBoardPrevBtn = document.getElementById('ranqueada-board-prev');
    const ranqueadaBoardNextBtn = document.getElementById('ranqueada-board-next');
    const ranqueadaBoardBackBtn = document.getElementById('ranqueada-board-back');
    const copyRanqueadaBoardLinkBtn = document.getElementById('copy-ranqueada-board-link');
    const activeChattersList = document.getElementById('active-chatters-list');
    const activeSearch = document.getElementById('active-search');
    const onlineCountEl = document.getElementById('online-count');
    const chatActivityChart = document.getElementById('chat-activity-chart');
    const totalTodayEl = document.getElementById('total-today');
    const peakInfoEl = document.getElementById('peak-info');
    const overallActivityChart = document.getElementById('overall-activity-chart');
    const overallTotalEl = document.getElementById('overall-total');
    const overallPeakEl = document.getElementById('overall-peak');
    const averageActivityChart = document.getElementById('average-activity-chart');
    const averageDaysEl = document.getElementById('average-days');
    const averagePeakEl = document.getElementById('average-peak');
    const uniqueChattersChart = document.getElementById('unique-chatters-chart');
    const uniqueTotalEl = document.getElementById('unique-total');
    const uniquePeakEl = document.getElementById('unique-peak');
    const chatTopEmotes = document.getElementById('chat-top-emotes');
    const userTopEmotes = document.getElementById('user-top-emotes');
    const errorMessage = document.getElementById('error-message');
    const filterBtns = document.querySelectorAll('.filter-btn');
    const platformFilterBtns = document.querySelectorAll('.platform-filter-btn');
    const tabBtns = document.querySelectorAll('.tab-btn');

    let allActiveChatters = [];
    let totalLeaderboardUsers = 0;
    let seenOnlineUsers = new Map(); // platform:username -> {display_name, platform, last_seen}
    let sevenTVEmotes = new Map(); // emote name -> emote URL

    let customStartDate = null;
    let customEndDate = null;
    const COLLECTION_START = '2026-09-01';

    function periodQueryParams(extra = {}) {
      const params = { ...extra };
      const period = (currentPeriod && currentPeriod !== 'undefined' && currentPeriod !== 'null')
        ? currentPeriod
        : 'all';
      params.period = period;
      if (period === 'custom' && customStartDate && customEndDate) {
        params.start_date = customStartDate;
        params.end_date = customEndDate;
      } else {
        delete params.start_date;
        delete params.end_date;
      }
      return params;
    }

    function apiUrl(path, params = {}) {
      const merged = { platform: currentPlatform || 'all', ...periodQueryParams(params) };
      const search = new URLSearchParams();
      Object.entries(merged).forEach(([key, value]) => {
        if (value == null || value === '' || value === 'undefined' || value === 'null') return;
        search.set(key, String(value));
      });
      const qs = search.toString();
      return `${API_BASE}${path}${qs ? `?${qs}` : ''}`;
    }

    function setLeaderboardError(el, message = 'Erro ao carregar') {
      if (!el) return;
      el.textContent = '';
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = message;
      el.appendChild(empty);
    }

    function todayBRTISO() {
      const fmt = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/Sao_Paulo',
        year: 'numeric', month: '2-digit', day: '2-digit',
      });
      return fmt.format(new Date());
    }

    function setEntryName(container, displayName, platform) {
      container.textContent = '';
      const nameText = document.createElement('span');
      nameText.className = 'name-text';
      nameText.textContent = displayName || '';
      container.appendChild(nameText);
      appendPlatformBadge(container, platform);
    }

    function fillEmoteNote(el, names) {
      if (!el) return;
      el.textContent = '';
      names.forEach((name) => {
        const url = sevenTVEmotes.get(name);
        if (url) {
          const img = document.createElement('img');
          img.src = url;
          img.alt = name;
          img.title = name;
          el.appendChild(img);
        } else {
          const span = document.createElement('span');
          span.textContent = name;
          el.appendChild(span);
        }
      });
    }

    function refreshEmoteNotes() {
      fillEmoteNote(document.getElementById('tragadores-note'), ['peepoSuscetivel', 'SmokeTime']);
      fillEmoteNote(document.getElementById('roda-note'), ['peepoSuscetivel', 'SmokeTime']);
    }

    function formatBRDate(iso) {
      if (!iso) return '';
      const parts = iso.split('-');
      if (parts.length !== 3) return iso;
      return parts[2] + '/' + parts[1] + '/' + parts[0];
    }

    function getPeriodLabel() {
      if (currentPeriod === 'day') return 'ultimo dia';
      if (currentPeriod === 'week') return 'ultimos 7 dias';
      if (currentPeriod === 'month') return 'ultimos 30 dias';
      if (currentPeriod === 'custom' && customStartDate && customEndDate) {
        return formatBRDate(customStartDate) + ' – ' + formatBRDate(customEndDate);
      }
      return 'desde 01/09/2026';
    }

    function updatePeriodLabels() {
      const label = getPeriodLabel();
      const map = {
        'note-top-emotes': 'Emotes mais usados (' + label + ') — clique para ver detalhes',
        'note-least-emotes': 'Os 10 menos usados (com pelo menos 1 uso) no periodo: ' + label,
        'note-unused-emotes': 'Emotes do catalogo com 0 usos no periodo: ' + label,
        'note-emote-ranking': 'Todos os emotes do catalogo por usos (' + label + ') — clique para detalhes',
        'note-user-emotes': 'Emotes mais usados (' + label + ')',
        'note-chat-activity': 'Mensagens por hora no periodo (' + label + ')',
        'note-unique-chatters': 'Usuarios distintos por hora no periodo (' + label + ')',
        'note-overall-total': 'Soma de mensagens por hora no periodo (' + label + ')',
        'note-overall-avg': 'Media diaria por hora no periodo (' + label + ')',
      };
      if (sidebarContextMode === 'bonks') {
        map['note-top'] = 'Quem mais usou ?bonk no período (' + label + ')';
      } else if (sidebarContextMode === 'emotes') {
        map['note-top'] = 'Emotes mais usados no período (' + label + ')';
      } else {
        map['note-top'] = 'Quem mais mandou mensagens no periodo (' + label + ')';
      }
      Object.keys(map).forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.textContent = map[id];
      });
    }

    function getUserPlatformParam() {
      if (currentPlatform !== 'all') return currentPlatform;
      return currentUserPlatform || 'all';
    }

    function shouldShowPlatformBadges() {
      return currentPlatform === 'all';
    }

    function createPlatformBadge(platform) {
      const badge = document.createElement('span');
      badge.className = 'platform-badge ' + platform;
      badge.textContent = platform === 'kick' ? 'Kick' : 'Twitch';
      return badge;
    }

    function appendPlatformBadge(parent, platform) {
      if (shouldShowPlatformBadges() && platform) {
        parent.appendChild(createPlatformBadge(platform));
      }
    }

    function loadEmotesSection(force = false) {
      if (emotesSectionLoaded && !force) return;
      emotesSectionLoaded = true;
      // Condensadas visuals are the above-the-fold default — keep light.
      if (force) emotePositionUsersCache = null;
      emotesCondensadasLoaded = true;
      fetchChatTopEmotes().then((emotes) => {
        if (sidebarContextMode === 'emotes' && emotes) {
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
        if (currentSection === 'emotes') fetchChatEmotePositions();
      }, 1200);
    }

    function loadEmotesCondensadasSection(force = false) {
      // Deep-link compat: show main Emotes tab (condensadas-first)
      navigateToSection('emotes', false);
      loadEmotesSection(force);
    }

    function loadRodaSection(force = false) {
      if (smokeTimeLoaded && !force) return;
      smokeTimeLoaded = true;
      fetchSmokeTime();
    }

    async function loadRanqueadaSection(force = false) {
      if (ranqueadaSectionLoaded && !force) return;
      ranqueadaSectionLoaded = true;
      refreshEmoteNotes();

      const boards = window.RANQUEADA_BOARDS || [];
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
        if (totalLeaderboardUsers > 0) {
          items.push({
            label: 'Pererecos',
            value: totalLeaderboardUsers.toLocaleString('pt-BR'),
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
            if (totalLeaderboardUsers > 0) renderRanqueadaOverview(boardDataMap);
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
      if (folhinhaSectionLoaded && !force) return;
      folhinhaSectionLoaded = true;

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
        if (sidebarContextMode === 'bonks' && map.bonkadores) {
          renderSimpleRankList(leaderboard, map.bonkadores, 'count');
        }
      };

      try {
        const mod = window.PererecosModules;
        if (mod && typeof mod.loadFolhinhaBoards === 'function') {
          await mod.loadFolhinhaBoards({
            apiUrl,
            setLeaderboardError,
            renderEntry: renderFolhinhaTabEntry,
            selectUser,
            navigateToBoard: (id) => navigateToRanqueadaBoard(id, true, 1, 'folhinha'),
            onLoaded: (boardsPayload) => {
              if (sidebarContextMode === 'bonks' && boardsPayload && boardsPayload.bonkadores) {
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
        folhinhaSectionLoaded = false;
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
      if (typeof window.getRanqueadaBoard === 'function') {
        const rq = window.getRanqueadaBoard(key);
        if (rq) return rq;
      }
      const fromFh = (window.FOLHINHA_BOARDS || []).find((b) => b.id === key || b.slug === key);
      if (fromFh) return fromFh;
      return (window.RANQUEADA_BOARDS || []).find((b) => b.id === key || b.slug === key) || null;
    }

    function navigateToRanqueadaBoard(boardId, updateUrl = true, page = 1, source = null) {
      const board = resolveBoard(boardId);
      if (!board) {
        navigateToSection(source === 'folhinha' ? 'folhinha' : 'ranqueada', updateUrl);
        return;
      }
      const isFolhinha = !!(board.render && String(board.render).startsWith('folhinha'));
      currentBoardSource = source || (isFolhinha ? 'folhinha' : 'ranqueada');
      currentRanqueadaBoardId = board.id;
      currentUsername = '';
      currentUserPlatform = null;
      currentEmoteName = '';
      ranqueadaBoardPage = Math.max(1, parseInt(page, 10) || 1);
      hideError();
      generalView.classList.add('hidden');
      statsSection.classList.remove('visible');
      if (emoteView) emoteView.classList.remove('visible');
      if (ranqueadaBoardView) ranqueadaBoardView.classList.add('visible');
      chatGeralBtn.classList.remove('active');
      updateNavActive('section', currentBoardSource === 'folhinha' ? 'folhinha' : 'ranqueada');
      if (updateUrl) pushRanqueadaBoardURL(board.id, ranqueadaBoardPage);
      loadRanqueadaBoardDetail(board, true);
    }

    function pushRanqueadaBoardURL(boardId, page = 1) {
      let qs = buildFilterQuery(currentPlatform, currentPeriod);
      if (page > 1) {
        qs = qs ? qs + '&page=' + page : '?page=' + page;
      }
      const section = currentBoardSource === 'folhinha' ? 'folhinha' : 'ranqueada';
      const url = BASE_PATH + '/' + section + '/' + encodeURIComponent(boardId) + qs;
      history.pushState({
        mode: 'ranqueada-board',
        boardId,
        page,
        boardSource: currentBoardSource,
        platform: currentPlatform,
        period: currentPeriod,
      }, '', url);
    }

    function hideRanqueadaBoardView() {
      currentRanqueadaBoardId = '';
      currentBoardSource = 'ranqueada';
      ranqueadaBoardEntries = [];
      ranqueadaBoardMeta = null;
      ranqueadaBoardPage = 1;
      if (ranqueadaBoardView) ranqueadaBoardView.classList.remove('visible');
    }

    async function loadRanqueadaBoardDetail(board, resetPage = false) {
      if (!board || !ranqueadaBoardListEl) return;
      if (resetPage) ranqueadaBoardPage = Math.max(1, ranqueadaBoardPage || 1);
      ranqueadaBoardMeta = board;
      if (ranqueadaBoardTitleEl) ranqueadaBoardTitleEl.textContent = board.title || board.id;
      if (ranqueadaBoardDescEl) ranqueadaBoardDescEl.textContent = board.description || '';
      document.title = (board.title || board.id) + ' - '
        + (currentBoardSource === 'folhinha' ? 'Folhinha' : 'Ranqueada')
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
        if (currentRanqueadaBoardId !== board.id) return;
        ranqueadaBoardEntries = extractBoardEntries(board, data, { detail: true }) || [];
        const pageSize = board.pageSize || 20;
        const paginate = board.paginateDetail !== false && board.render !== 'hours';
        const totalPages = paginate
          ? Math.max(1, Math.ceil(ranqueadaBoardEntries.length / pageSize))
          : 1;
        if (ranqueadaBoardPage > totalPages) ranqueadaBoardPage = totalPages;
        renderRanqueadaBoardPage();
      } catch (err) {
        console.error('Board detail', board.id, err);
        setLeaderboardError(ranqueadaBoardListEl);
      }
    }

    function renderRanqueadaBoardPage() {
      const board = ranqueadaBoardMeta;
      if (!board || !ranqueadaBoardListEl) return;
      const paginate = board.paginateDetail !== false && board.render !== 'hours';
      const pageSize = board.pageSize || 20;
      const total = ranqueadaBoardEntries.length;
      const totalPages = paginate ? Math.max(1, Math.ceil(total / pageSize)) : 1;
      if (ranqueadaBoardPage < 1) ranqueadaBoardPage = 1;
      if (ranqueadaBoardPage > totalPages) ranqueadaBoardPage = totalPages;

      let pageEntries = ranqueadaBoardEntries;
      let rankOffset = 0;
      if (paginate) {
        const start = (ranqueadaBoardPage - 1) * pageSize;
        rankOffset = start;
        pageEntries = ranqueadaBoardEntries.slice(start, start + pageSize).map((e, i) => {
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
              'Página ' + ranqueadaBoardPage + ' de ' + totalPages
              + ' (' + total + ')';
          }
          if (ranqueadaBoardPrevBtn) ranqueadaBoardPrevBtn.disabled = ranqueadaBoardPage <= 1;
          if (ranqueadaBoardNextBtn) ranqueadaBoardNextBtn.disabled = ranqueadaBoardPage >= totalPages;
        }
      }
    }

    function setRanqueadaBoardPage(page, updateUrl = true) {
      ranqueadaBoardPage = page;
      renderRanqueadaBoardPage();
      if (updateUrl && currentRanqueadaBoardId) {
        pushRanqueadaBoardURL(currentRanqueadaBoardId, ranqueadaBoardPage);
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

    function loadCoreStats() {
      fetchLeaderboard();
      fetchActiveChatters();
    }

    function loadChartStats() {
      fetchChatActivity();
      fetchUniqueChatters();
      fetchOverallActivity();
    }

    function loadInitialData() {
      updatePeriodLabels();
      fetch7TVEmotes();
      loadCoreStats();
      setTimeout(loadChartStats, 500);
    }

    function refreshAllData() {
      loadCoreStats();
      if (currentRanqueadaBoardId) {
        const board = resolveBoard(currentRanqueadaBoardId);
        if (board) loadRanqueadaBoardDetail(board, true);
      } else if (!currentUsername && !currentEmoteName) {
        refreshSidebarContext(currentSection);
        if (currentSection === 'home') {
          setTimeout(loadChartStats, 300);
        } else if (currentSection === 'emotes') {
          emotesSectionLoaded = false;
          emoteRankingCache = null;
          loadEmotesSection(true);
        } else if (currentSection === 'emotes-condensadas') {
          emotesSectionLoaded = false;
          emoteRankingCache = null;
          loadEmotesSection(true);
        } else if (currentSection === 'roda') {
          smokeTimeLoaded = false;
          loadRodaSection(true);
        } else if (currentSection === 'ranqueada') {
          ranqueadaSectionLoaded = false;
          loadRanqueadaSection(true);
        } else if (currentSection === 'folhinha') {
          folhinhaSectionLoaded = false;
          loadFolhinhaSection(true);
        } else if (currentSection === 'comparar') {
          compararSectionLoaded = false;
          loadCompararSection(true);
        }
      }
      if (currentUsername) fetchUserStats(true);
      if (currentEmoteName) fetchEmoteDetail(currentEmoteName);
    }

    searchBtn.addEventListener('click', () => {
      hideAutocomplete();
      searchUser();
    });

    chatGeralBtn.addEventListener('click', () => {
      navigateToSection('home');
    });

    document.querySelectorAll('.stats-nav-item').forEach(btn => {
      btn.addEventListener('click', () => {
        const section = btn.dataset.section || 'home';
        navigateToSection(section);
      });
    });

    usernameInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
        if (selectedAutocompleteIndex >= 0 && items[selectedAutocompleteIndex]) {
          items[selectedAutocompleteIndex].click();
        } else {
          hideAutocomplete();
          searchUser();
        }
      }
    });

    usernameInput.addEventListener('keydown', (e) => {
      const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedAutocompleteIndex = Math.min(selectedAutocompleteIndex + 1, items.length - 1);
        updateAutocompleteSelection(items);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedAutocompleteIndex = Math.max(selectedAutocompleteIndex - 1, -1);
        updateAutocompleteSelection(items);
      } else if (e.key === 'Escape') {
        hideAutocomplete();
      }
    });

    usernameInput.addEventListener('input', () => {
      const query = usernameInput.value.trim();
      if (searchTimeout) clearTimeout(searchTimeout);

      if (query.length < 2) {
        hideAutocomplete();
        return;
      }

      searchTimeout = setTimeout(() => {
        fetchAutocomplete(query);
      }, 150);
    });

    usernameInput.addEventListener('focus', () => {
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

    activeSearch.addEventListener('input', () => {
      filterActiveChatters(activeSearch.value);
    });

    const customDateRow = document.getElementById('custom-date-row');
    const customStartInput = document.getElementById('custom-start-date');
    const customEndInput = document.getElementById('custom-end-date');
    const customDateApply = document.getElementById('custom-date-apply');

    function syncCustomDateInputs() {
      const today = todayBRTISO();
      if (customStartInput) {
        customStartInput.min = COLLECTION_START;
        customStartInput.max = today;
        if (!customStartInput.value) customStartInput.value = customStartDate || COLLECTION_START;
      }
      if (customEndInput) {
        customEndInput.min = COLLECTION_START;
        customEndInput.max = today;
        if (!customEndInput.value) customEndInput.value = customEndDate || today;
      }
    }

    function applyPeriodChange() {
      if (currentUsername) {
        pushUserURL(currentUsername, currentUserPlatform || currentPlatform, currentPeriod);
      } else if (currentEmoteName) {
        pushEmoteURL(currentEmoteName);
      } else if (currentRanqueadaBoardId) {
        ranqueadaBoardPage = 1;
        pushRanqueadaBoardURL(currentRanqueadaBoardId, 1);
      } else if (['emotes', 'emotes-condensadas', 'roda', 'ranqueada', 'comparar', 'folhinha'].includes(currentSection)) {
        pushSectionURL(currentSection);
      } else {
        pushHomeURL();
      }
      updatePeriodLabels();
      emotesSectionLoaded = false;
      emotesCondensadasLoaded = false;
      emoteRankingCache = null;
      smokeTimeLoaded = false;
      ranqueadaSectionLoaded = false;
      folhinhaSectionLoaded = false;
      compararSectionLoaded = false;
      refreshAllData();
    }

    filterBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const period = btn.dataset.period;
        if (period === 'custom') {
          filterBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          currentPeriod = 'custom';
          if (customDateRow) customDateRow.classList.add('visible');
          syncCustomDateInputs();
          return;
        }
        filterBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentPeriod = period;
        customStartDate = null;
        customEndDate = null;
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
        customStartDate = start;
        customEndDate = end;
        currentPeriod = 'custom';
        filterBtns.forEach(b => b.classList.toggle('active', b.dataset.period === 'custom'));
        applyPeriodChange();
      });
    }

    platformFilterBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        platformFilterBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentPlatform = btn.dataset.platform;
        if (currentPlatform !== 'all') {
          currentUserPlatform = currentPlatform;
        }
        if (currentUsername) {
          pushUserURL(currentUsername, currentUserPlatform || currentPlatform, currentPeriod);
        } else if (currentEmoteName) {
          pushEmoteURL(currentEmoteName);
        } else if (currentRanqueadaBoardId) {
          ranqueadaBoardPage = 1;
          pushRanqueadaBoardURL(currentRanqueadaBoardId, 1);
        } else if (['emotes', 'emotes-condensadas', 'roda', 'ranqueada', 'comparar', 'folhinha'].includes(currentSection)) {
          pushSectionURL(currentSection);
          emotesSectionLoaded = false;
          emotesCondensadasLoaded = false;
          emoteRankingCache = null;
          smokeTimeLoaded = false;
          ranqueadaSectionLoaded = false;
          folhinhaSectionLoaded = false;
          compararSectionLoaded = false;
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
        navigateToSection(currentBoardSource === 'folhinha' ? 'folhinha' : 'ranqueada');
      });
    }
    if (ranqueadaBoardPrevBtn) {
      ranqueadaBoardPrevBtn.addEventListener('click', () => {
        if (ranqueadaBoardPage > 1) setRanqueadaBoardPage(ranqueadaBoardPage - 1);
      });
    }
    if (ranqueadaBoardNextBtn) {
      ranqueadaBoardNextBtn.addEventListener('click', () => {
        setRanqueadaBoardPage(ranqueadaBoardPage + 1);
      });
    }

    // Right panel is Top 10 only; other boards live in Ranqueada
    function switchTab(tab) {
      currentTab = tab || 'top';
    }

    let chatActivityCounter = 0;
    let pollCounter = 0;

    function startAutoRefresh() {
      if (refreshInterval) clearInterval(refreshInterval);
      refreshInterval = setInterval(() => {
        pollCounter++;

        // Leaderboard: every 15s (always visible in right panel)
        if (pollCounter % 3 === 0) fetchLeaderboard();

        // User profile: every 60s (avoid flicker / load)
        if (currentUsername && pollCounter % 12 === 0) fetchUserStats(true);

        // Active chatters: every 10s
        if (pollCounter % 2 === 0) fetchActiveChatters();

        // Chat activity charts: every 30s, only while Home is visible
        chatActivityCounter++;
        if (!currentUsername && currentSection === 'home' && chatActivityCounter >= 6) {
          fetchChatActivity();
          fetchUniqueChatters();
          chatActivityCounter = 0;
        }
      }, 5000);
    }

    function showGeneralView(updateUrl = true, section = 'home') {
      if (userStatsAbort) {
        userStatsAbort.abort();
        userStatsAbort = null;
      }
      currentUsername = '';
      currentUserPlatform = null;
      currentEmoteName = '';
      hideRanqueadaBoardView();
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

    function showSectionPanel(section) {
      if (section === 'emotes-condensadas') section = 'emotes';
      const valid = ['emotes', 'roda', 'ranqueada', 'comparar', 'folhinha'];
      currentSection = valid.includes(section) ? section : 'home';
      const homeEl = document.getElementById('section-home');
      const emotesEl = document.getElementById('section-emotes');
      const condensadasEl = document.getElementById('section-emotes-condensadas');
      const rodaEl = document.getElementById('section-roda');
      const ranqueadaEl = document.getElementById('section-ranqueada');
      const compararEl = document.getElementById('section-comparar');
      const folhinhaEl = document.getElementById('section-folhinha');
      if (homeEl) homeEl.classList.toggle('hidden', currentSection !== 'home');
      if (emotesEl) emotesEl.classList.toggle('hidden', currentSection !== 'emotes');
      if (condensadasEl) condensadasEl.classList.add('hidden');
      if (rodaEl) rodaEl.classList.toggle('hidden', currentSection !== 'roda');
      if (ranqueadaEl) ranqueadaEl.classList.toggle('hidden', currentSection !== 'ranqueada');
      if (compararEl) compararEl.classList.toggle('hidden', currentSection !== 'comparar');
      if (folhinhaEl) folhinhaEl.classList.toggle('hidden', currentSection !== 'folhinha');
      updateNavActive('section', currentSection);
      if (currentSection === 'home') document.title = DEFAULT_TITLE;
      else if (currentSection === 'emotes') document.title = 'Emotes - Pererecos Stats';
      else if (currentSection === 'roda') document.title = 'Roda - Pererecos Stats';
      else if (currentSection === 'ranqueada') document.title = 'Ranqueada - Pererecos Stats';
      else if (currentSection === 'comparar') document.title = 'Comparar - Pererecos Stats';
      else if (currentSection === 'folhinha') document.title = 'Folhinha - Pererecos Stats';
    }

    function updateNavActive(mode, section) {
      document.querySelectorAll('.stats-nav-item').forEach(btn => {
        const isActive = mode !== 'user' && btn.dataset.section === (section || 'home');
        btn.classList.toggle('active', isActive);
      });
    }

    function loadSectionData(section) {
      if (section === 'emotes-condensadas') section = 'emotes';
      // Set rail labels first (no extra fetches) so section loaders can fill data
      refreshSidebarContext(section === 'home' ? 'home' : section);
      if (section === 'emotes') loadEmotesSection();
      else if (section === 'roda') loadRodaSection();
      else if (section === 'ranqueada') loadRanqueadaSection();
      else if (section === 'folhinha') loadFolhinhaSection();
      else if (section === 'comparar') loadCompararSection();
      else {
        loadCoreStats();
        setTimeout(loadChartStats, 300);
      }
    }

    function navigateToSection(section, updateUrl = true) {
      showGeneralView(updateUrl, section);
    }

    async function searchUser() {
      const username = usernameInput.value.trim();
      if (!username) {
        showGeneralView();
        updateLeaderboardSelection();
        return;
      }

      selectUser(username, currentPlatform !== 'all' ? currentPlatform : null);
    }

    function showSectionLoading(el, text) {
      if (!el) return;
      el.innerHTML = '<div class="empty-state loading">' + (text || 'Carregando...') + '</div>';
    }

    function showUserSectionPlaceholders() {
      showSectionLoading(rankingsGrid);
      showSectionLoading(rivalInfo);
      showSectionLoading(repliesList);
      showSectionLoading(userTopEmotes);
      showSectionLoading(document.getElementById('user-emote-positions'));
      showSectionLoading(messagesList);
      const smokeSection = document.getElementById('user-smoke-section');
      if (smokeSection) smokeSection.style.display = 'none';
      const fhSection = document.getElementById('user-folhinha-section');
      if (fhSection) fhSection.style.display = 'none';
      if (hourlyChart) showSectionLoading(hourlyChart);
      if (peakHoursText) peakHoursText.textContent = '';
      if (favoriteHourText) favoriteHourText.textContent = '';
    }

    async function fetchUserStats(silent = false) {
      if (!currentUsername) return;

      if (userStatsAbort) userStatsAbort.abort();
      userStatsAbort = new AbortController();
      const signal = userStatsAbort.signal;
      const requestedUser = currentUsername;

      if (!silent) {
        showUserSectionPlaceholders();
      }

      try {
        const coreResponse = await fetch(
          apiUrl(`/stats/user/${encodeURIComponent(currentUsername)}/core`, {
            period: currentPeriod,
            platform: getUserPlatformParam(),
          }),
          { signal }
        );

        if (!coreResponse.ok) {
          if (coreResponse.status === 404) {
            if (!silent) showError('Usuario nao encontrado ou sem mensagens');
            statsSection.classList.remove('visible');
            return;
          }
          throw new Error('API Error');
        }

        const core = await coreResponse.json();
        if (signal.aborted || currentUsername !== requestedUser) return;

        renderUserCore(core, silent);
        statsSection.classList.add('visible');

        fetchAndRenderActivity(signal, requestedUser);
        fetchAndRenderRankings(signal, requestedUser);
        fetchAndRenderSocial(signal, requestedUser);
        fetchAndRenderEmotes(signal, requestedUser);
        fetchAndRenderRecentMessages(signal, requestedUser);
        fetchAndRenderSmokeStats(signal, requestedUser);
        fetchAndRenderFolhinhaStats(signal, requestedUser);
        fetchUsernameHistory(core.username, core.platform);
      } catch (error) {
        if (error.name === 'AbortError') return;
        console.error('Error loading user core:', error);
        if (!silent) showError('Erro ao buscar dados');
      }
    }

    function renderUserCore(data, silent = false) {
      displayNameEl.textContent = '';
      displayNameEl.appendChild(document.createTextNode(data.display_name));
      currentUserPlatform = data.platform || currentUserPlatform;
      appendPlatformBadge(displayNameEl, data.platform);
      document.title = data.display_name + ' - Pererecos Stats';

      const isOnline = allActiveChatters.some(
        c => c.username === data.username && c.platform === data.platform
      );
      userStatusEl.textContent = '';
      const statusBadge = document.createElement('span');
      statusBadge.className = 'status-badge ' + (isOnline ? 'online' : 'offline');
      const statusDot = document.createElement('span');
      statusDot.className = 'status-dot';
      statusBadge.appendChild(statusDot);
      statusBadge.appendChild(document.createTextNode(isOnline ? ' Online' : ' Offline'));
      userStatusEl.appendChild(statusBadge);

      if (!silent) {
        animateNumber(totalMessagesEl, data.total_messages);
      } else {
        totalMessagesEl.textContent = data.total_messages.toLocaleString('pt-BR');
      }

      if (data.percentile > 0) {
        percentileText.textContent = '';
        percentileText.appendChild(document.createTextNode('Voce conversa mais que '));
        const span = document.createElement('span');
        span.textContent = Math.round(data.percentile) + '%';
        percentileText.appendChild(span);
        percentileText.appendChild(document.createTextNode(' dos pererecos'));
      } else {
        percentileText.textContent = '';
      }

      if (data.last_message_date) {
        lastMessageText.textContent = '';
        const date = new Date(data.last_message_date);
        const dateStr = date.toLocaleString('pt-BR', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          timeZone: 'America/Sao_Paulo'
        });
        lastMessageText.appendChild(document.createTextNode('Ultima mensagem: '));
        const span = document.createElement('span');
        span.textContent = dateStr;
        lastMessageText.appendChild(span);
      } else {
        lastMessageText.textContent = '';
      }

      if (data.hourly_activity) {
        renderHourlyChart(data.hourly_activity);
      }
      renderPeakHours(data.peak_hours);
      renderFavoriteHour(data.favorite_hour);
    }

    function renderPeakHours(peakHours) {
      if (peakHours && peakHours.length > 0) {
        const peakStart = peakHours[0];
        const peakEnd = peakHours[peakHours.length - 1];
        peakHoursText.textContent = '';
        peakHoursText.appendChild(document.createTextNode('Horario de pico: '));
        const span = document.createElement('span');
        span.textContent = peakStart + 'h - ' + peakEnd + 'h';
        peakHoursText.appendChild(span);
      } else {
        peakHoursText.textContent = '';
      }
    }

    function renderFavoriteHour(favoriteHour) {
      if (favoriteHour) {
        favoriteHourText.textContent = '';
        favoriteHourText.appendChild(document.createTextNode('Horario favorito: '));
        const span = document.createElement('span');
        span.textContent = favoriteHour.hour + 'h (' + favoriteHour.percentage + '% das msgs)';
        favoriteHourText.appendChild(span);
      } else {
        favoriteHourText.textContent = '';
      }
    }

    async function fetchAndRenderActivity(signal, requestedUser) {
      try {
        const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/activity`, {
          period: currentPeriod,
          platform: getUserPlatformParam(),
        }), { signal });
        if (!res.ok || currentUsername !== requestedUser) return;
        const data = await res.json();
        renderHourlyChart(data.hourly_activity || []);
        renderPeakHours(data.peak_hours);
        renderFavoriteHour(data.favorite_hour);
      } catch (e) {
        if (e.name !== 'AbortError') console.error('activity:', e);
      }
    }

    async function fetchAndRenderRankings(signal, requestedUser) {
      try {
        const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/rankings`, {
          period: currentPeriod,
          platform: getUserPlatformParam(),
        }), { signal });
        if (!res.ok || currentUsername !== requestedUser) return;
        const data = await res.json();
        renderRankings(data.rankings);
      } catch (e) {
        if (e.name !== 'AbortError') console.error('rankings:', e);
      }
    }

    async function fetchAndRenderSocial(signal, requestedUser) {
      try {
        const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/social`, {
          period: currentPeriod,
          platform: getUserPlatformParam(),
        }), { signal });
        if (!res.ok || currentUsername !== requestedUser) return;
        const data = await res.json();
        renderRival(data.rival);
        renderTopReplies(data.top_replies || []);
      } catch (e) {
        if (e.name !== 'AbortError') console.error('social:', e);
      }
    }

    async function fetchAndRenderEmotes(signal, requestedUser) {
      try {
        const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/emotes`, {
          period: currentPeriod,
          platform: getUserPlatformParam(),
        }), { signal });
        if (!res.ok || currentUsername !== requestedUser) return;
        const data = await res.json();
        renderTopEmotes(userTopEmotes, data.top_emotes || []);
        const container = document.getElementById('user-emote-positions');
        if (data.emote_position) {
          renderEmotePositionBar(container, data.emote_position.positions, data.emote_position.label);
        } else if (container) {
          container.innerHTML = '<div class="empty-state">Nenhum dado de emotes</div>';
        }
      } catch (e) {
        if (e.name !== 'AbortError') console.error('emotes:', e);
      }
    }

    async function fetchAndRenderRecentMessages(signal, requestedUser) {
      try {
        const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/recent`, {
          platform: getUserPlatformParam(),
        }), { signal });
        if (!res.ok || currentUsername !== requestedUser) return;
        const data = await res.json();
        renderRecentMessages(data.recent_messages || []);
      } catch (e) {
        if (e.name !== 'AbortError') console.error('recent:', e);
      }
    }

    async function fetchAndRenderSmokeStats(signal, requestedUser) {
      try {
        const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/smoke`, {
          platform: getUserPlatformParam(),
        }), { signal });
        if (!res.ok || currentUsername !== requestedUser) return;
        const data = await res.json();
        renderUserSmokeStats(data.smoke_stats);
      } catch (e) {
        if (e.name !== 'AbortError') console.error('smoke:', e);
      }
    }

    function renderRival(rival) {
      rivalInfo.textContent = '';
      if (!rival) {
        const emptySpan = document.createElement('span');
        emptySpan.className = 'empty-state';
        emptySpan.style.padding = '0.5rem';
        emptySpan.style.fontSize = '0.8rem';
        emptySpan.textContent = 'Nenhum rival';
        rivalInfo.appendChild(emptySpan);
        return;
      }

      const nameSpan = document.createElement('span');
      nameSpan.className = 'rival-name';
      nameSpan.textContent = rival.display_name;
      nameSpan.onclick = () => selectUser(rival.username, rival.platform);

      const scoreSpan = document.createElement('span');
      scoreSpan.className = 'rival-score';
      scoreSpan.textContent = rival.similarity_score + '% similar';

      rivalInfo.appendChild(nameSpan);
      rivalInfo.appendChild(scoreSpan);
    }

    function renderTopReplies(replies) {
      repliesList.textContent = '';
      if (!replies || replies.length === 0) {
        const emptySpan = document.createElement('span');
        emptySpan.className = 'empty-state';
        emptySpan.style.padding = '0.5rem';
        emptySpan.style.fontSize = '0.8rem';
        emptySpan.textContent = 'Nenhum dado';
        repliesList.appendChild(emptySpan);
        return;
      }

      replies.forEach(r => {
        const item = document.createElement('div');
        item.className = 'reply-item';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'reply-name';
        nameSpan.textContent = r.display_name;
        nameSpan.onclick = () => selectUser(r.username, r.platform);

        const countSpan = document.createElement('span');
        countSpan.className = 'reply-count';
        countSpan.textContent = r.reply_count + 'x';

        item.appendChild(nameSpan);
        item.appendChild(countSpan);
        repliesList.appendChild(item);
      });
    }

    function renderUserSmokeStats(smoke) {
      const section = document.getElementById('user-smoke-section');
      if (!section) return;

      if (!smoke || !smoke.count) {
        section.style.display = 'none';
        return;
      }

      section.style.display = '';

      const countEl = document.getElementById('user-smoke-count');
      const rankEl = document.getElementById('user-smoke-rank');
      const streakEl = document.getElementById('user-smoke-streak');
      const longestEl = document.getElementById('user-smoke-longest');
      const firstEl = document.getElementById('user-smoke-first');
      const lastEl = document.getElementById('user-smoke-last');

      if (countEl) countEl.textContent = smoke.count.toLocaleString('pt-BR');
      if (rankEl) rankEl.textContent = smoke.rank ? '#' + smoke.rank : '—';
      if (streakEl) {
        streakEl.textContent = smoke.streak_current > 0
          ? '🔥' + smoke.streak_current
          : '—';
      }
      if (longestEl) {
        longestEl.textContent = smoke.streak_longest > 0
          ? smoke.streak_longest + ' dias'
          : '—';
      }
      if (firstEl) firstEl.textContent = smoke.first_session ? formatDate(smoke.first_session) : '—';
      if (lastEl) lastEl.textContent = smoke.last_session ? formatDate(smoke.last_session) : '—';
    }

    function renderFolhinhaPartnerList(el, partners, opts = {}) {
      if (!el) return;
      el.textContent = '';
      if (!partners || !partners.length) {
        const empty = document.createElement('span');
        empty.className = 'empty-state';
        empty.style.padding = '0.5rem';
        empty.style.fontSize = '0.8rem';
        empty.textContent = 'Nenhum dado';
        el.appendChild(empty);
        return;
      }
      partners.forEach((p) => {
        const item = document.createElement('div');
        item.className = 'reply-item';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'reply-name';
        nameSpan.textContent = p.display_name || p.username;
        nameSpan.onclick = () => selectUser(p.username, p.platform);

        const countSpan = document.createElement('span');
        countSpan.className = 'reply-count';
        if (opts.showPct && p.avg_percentage != null) {
          countSpan.textContent =
            p.count +
            'x · ' +
            p.avg_percentage.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) +
            '%';
        } else {
          countSpan.textContent = p.count + 'x';
        }

        item.appendChild(nameSpan);
        item.appendChild(countSpan);
        el.appendChild(item);
      });
    }

    function renderUserFolhinhaStats(fh) {
      const section = document.getElementById('user-folhinha-section');
      if (!section) return;
      if (!fh) {
        section.style.display = 'none';
        return;
      }
      section.style.display = '';

      const set = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
      };
      set('user-fh-bonks-given', (fh.bonks_given || 0).toLocaleString('pt-BR'));
      set('user-fh-bonks-recv', (fh.bonks_received || 0).toLocaleString('pt-BR'));
      set(
        'user-fh-avg-pct',
        fh.avg_bonk_pct != null
          ? fh.avg_bonk_pct.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '%'
          : '—'
      );
      set('user-fh-hugs-given', (fh.abracos_given || 0).toLocaleString('pt-BR'));
      set('user-fh-hugs-recv', (fh.abracos_received || 0).toLocaleString('pt-BR'));
      set(
        'user-fh-roulette',
        (fh.roulette_survives || 0).toLocaleString('pt-BR') +
          ' / ' +
          (fh.roulette_deaths || 0).toLocaleString('pt-BR')
      );
      set(
        'user-fh-cookies',
        fh.cookies_balance != null ? fh.cookies_balance.toLocaleString('pt-BR') : '—'
      );
      set(
        'user-fh-slot',
        '+' +
          (fh.slot_won || 0).toLocaleString('pt-BR') +
          ' / −' +
          (fh.slot_lost || 0).toLocaleString('pt-BR')
      );

      renderFolhinhaPartnerList(
        document.getElementById('user-fh-bonk-targets'),
        fh.top_bonk_targets,
        { showPct: true }
      );
      renderFolhinhaPartnerList(
        document.getElementById('user-fh-bonk-from'),
        fh.top_bonk_from,
        { showPct: true }
      );
      renderFolhinhaPartnerList(
        document.getElementById('user-fh-hug-targets'),
        fh.top_abraco_targets
      );
      renderFolhinhaPartnerList(
        document.getElementById('user-fh-hug-from'),
        fh.top_abraco_from
      );
    }

    async function fetchAndRenderFolhinhaStats(signal, requestedUser) {
      try {
        const res = await fetch(
          apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/folhinha`, {
            period: currentPeriod,
            platform: getUserPlatformParam(),
          }),
          { signal }
        );
        if (!res.ok || signal.aborted || currentUsername !== requestedUser) return;
        const data = await res.json();
        if (signal.aborted || currentUsername !== requestedUser) return;
        renderUserFolhinhaStats(data.folhinha_stats);
      } catch (e) {
        if (e.name !== 'AbortError') console.error('folhinha:', e);
      }
    }

    function renderRankings(rankings) {
      rankingsGrid.textContent = '';

      if (!rankings) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.style.gridColumn = '1 / -1';
        empty.textContent = 'Sem dados de ranking';
        rankingsGrid.appendChild(empty);
        return;
      }

      function addRank(label, rank, extra) {
        const item = document.createElement('div');
        item.className = 'ranking-item';
        const lab = document.createElement('span');
        lab.className = 'ranking-label';
        lab.textContent = label;
        const value = document.createElement('span');
        value.className = 'ranking-value';
        value.textContent = rank != null ? '#' + rank : '—';
        if (extra) value.appendChild(extra);
        item.appendChild(lab);
        item.appendChild(value);
        rankingsGrid.appendChild(item);
      }

      let changeEl = null;
      if (rankings.top_rank_change != null && rankings.top_rank_change !== 0) {
        changeEl = document.createElement('span');
        changeEl.className = 'rank-change ' + (rankings.top_rank_change > 0 ? 'up' : 'down');
        changeEl.textContent = rankings.top_rank_change > 0
          ? '+' + rankings.top_rank_change
          : String(rankings.top_rank_change);
      }
      addRank('Perereco Rank', rankings.top_rank, changeEl);
      addRank('Girinos', rankings.rising_rank);
      addRank('Textões', rankings.writers_rank);

      const hoursItem = document.createElement('div');
      hoursItem.className = 'ranking-item';
      const hoursLabel = document.createElement('span');
      hoursLabel.className = 'ranking-label';
      hoursLabel.textContent = 'Top1 da(s) hora(s)';
      const hoursValue = document.createElement('span');
      hoursValue.className = 'ranking-value';
      if (rankings.hours_dominated && rankings.hours_dominated.length > 0) {
        hoursValue.textContent = rankings.hours_dominated.map(h => h + 'h').join(', ');
      } else {
        hoursValue.textContent = '—';
      }
      hoursItem.appendChild(hoursLabel);
      hoursItem.appendChild(hoursValue);
      rankingsGrid.appendChild(hoursItem);

      addRank('Famosinhos', rankings.famosinhos_rank);
      addRank('Folhinha', rankings.folhinha_rank);
      addRank('Maria vai com as outras', rankings.maria_vai_com_as_outras_rank);
      addRank('Escritor roubado', rankings.escritor_roubado_rank);
      addRank(
        'Diversidade' + (rankings.diversidade_count != null ? ' (' + rankings.diversidade_count + ')' : ''),
        rankings.diversidade_rank
      );
      addRank('Roda', rankings.smoke_rank);
      if (rankings.pererecoes_rank != null || rankings.pererecoes_points) {
        addRank(
          'Pererecães' + (rankings.pererecoes_points != null ? ' (' + rankings.pererecoes_points + ' pts)' : ''),
          rankings.pererecoes_rank
        );
      }
      if (rankings.creators_count) {
        addRank('Criadores (' + rankings.creators_count + ')', rankings.creators_rank);
      }
      if (rankings.duas_caras_count != null && rankings.duas_caras_count >= 2) {
        addRank(
          'Duas Caras (' + rankings.duas_caras_count + ')',
          rankings.duas_caras_rank
        );
      }
    }

    function renderHourlyChart(hourlyData) {
      // Hours are already in Brasília timezone (UTC-3)
      const maxCount = Math.max(...hourlyData.map(h => h.count), 1);

      hourlyChart.textContent = '';
      hourlyData.forEach(h => {
        const height = Math.max((h.count / maxCount) * 100, 2);
        const wrapper = document.createElement('div');
        wrapper.className = 'bar-wrapper';
        wrapper.dataset.tooltip = h.hour + 'h: ' + h.count.toLocaleString('pt-BR');

        const bar = document.createElement('div');
        bar.className = 'bar';
        bar.style.height = height + '%';

        wrapper.appendChild(bar);
        hourlyChart.appendChild(wrapper);
      });
    }

    function renderMessageWithEmotes(container, text) {
      // Split by whitespace but keep the delimiters
      const parts = text.split(/(\s+)/);
      parts.forEach(part => {
        if (part.match(/^\s+$/)) {
          // Whitespace - preserve it
          container.appendChild(document.createTextNode(part));
        } else {
          const emoteUrl = sevenTVEmotes.get(part);
          if (emoteUrl) {
            const img = document.createElement('img');
            img.src = emoteUrl;
            img.alt = part;
            img.title = part;
            img.className = 'chat-emote';
            img.loading = 'lazy';
            container.appendChild(img);
          } else {
            container.appendChild(document.createTextNode(part));
          }
        }
      });
    }

    function renderRecentMessages(messages) {
      messagesList.textContent = '';
      if (messages.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'Nenhuma mensagem';
        messagesList.appendChild(empty);
        return;
      }

      messages.forEach(msg => {
        const date = new Date(msg.timestamp);
        // Display in Brasília timezone (UTC-3)
        const timeStr = date.toLocaleString('pt-BR', {
          day: '2-digit',
          month: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          timeZone: 'America/Sao_Paulo'
        });

        const item = document.createElement('div');
        item.className = 'message-item';

        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        renderMessageWithEmotes(textDiv, msg.message);

        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = timeStr;

        item.appendChild(textDiv);
        item.appendChild(timeDiv);
        messagesList.appendChild(item);
      });
    }

    function animateNumber(element, target) {
      const duration = 600;
      const start = parseInt(element.textContent.replace(/\D/g, '')) || 0;
      const startTime = performance.now();

      function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(start + (target - start) * eased);
        element.textContent = current.toLocaleString('pt-BR');

        if (progress < 1) requestAnimationFrame(update);
      }

      requestAnimationFrame(update);
    }

    async function searchUsersForAutocomplete(query) {
      const lowerQuery = query.toLowerCase();

      // Filter online users that match
      const onlineMatches = [];
      seenOnlineUsers.forEach((data, key) => {
        const username = key.includes(':') ? key.split(':').slice(1).join(':') : key;
        if (username.includes(lowerQuery) || data.display_name.toLowerCase().includes(lowerQuery)) {
          onlineMatches.push({
            username,
            display_name: data.display_name,
            platform: data.platform || 'twitch',
            isOnline: true
          });
        }
      });

      // Sort by relevance (starts with query first)
      onlineMatches.sort((a, b) => {
        const aStarts = a.username.startsWith(lowerQuery) ? 0 : 1;
        const bStarts = b.username.startsWith(lowerQuery) ? 0 : 1;
        return aStarts - bStarts;
      });

      // Fetch from API
      let apiResults = [];
      try {
        const response = await fetch(apiUrl('/stats/search', { q: query }));
        if (response.ok) {
          apiResults = await response.json();
        }
      } catch (error) {
        console.error('Search error:', error);
      }

      // Filter out users already in online matches
      const onlineUsernames = new Set(onlineMatches.map(u => `${u.platform}:${u.username}`));
      const apiMatches = apiResults
        .filter(u => !onlineUsernames.has(`${u.platform || 'twitch'}:${u.username}`))
        .map(u => ({
          username: u.username,
          display_name: u.display_name,
          platform: u.platform || 'twitch',
          total_messages: u.total_messages,
          isOnline: false
        }));

      return {
        online: onlineMatches.slice(0, 5),
        all: apiMatches.slice(0, 5),
      };
    }

    async function fetchAutocomplete(query) {
      const matches = await searchUsersForAutocomplete(query);
      renderAutocomplete(matches.online, matches.all);
    }

    function renderAutocomplete(onlineUsers, allUsers) {
      autocompleteDropdown.textContent = '';
      selectedAutocompleteIndex = -1;

      if (onlineUsers.length === 0 && allUsers.length === 0) {
        hideAutocomplete();
        return;
      }

      if (onlineUsers.length > 0) {
        const section = document.createElement('div');
        section.className = 'autocomplete-section';

        const header = document.createElement('div');
        header.className = 'autocomplete-header';
        header.textContent = 'Online agora';
        section.appendChild(header);

        onlineUsers.forEach(user => {
          const item = createAutocompleteItem(user, true);
          section.appendChild(item);
        });

        autocompleteDropdown.appendChild(section);
      }

      if (allUsers.length > 0) {
        const section = document.createElement('div');
        section.className = 'autocomplete-section';

        const header = document.createElement('div');
        header.className = 'autocomplete-header';
        header.textContent = 'Todos os usuarios';
        section.appendChild(header);

        allUsers.forEach(user => {
          const item = createAutocompleteItem(user, false);
          section.appendChild(item);
        });

        autocompleteDropdown.appendChild(section);
      }

      autocompleteDropdown.classList.add('visible');
    }

    function createAutocompleteItem(user, isOnline) {
      const item = document.createElement('div');
      item.className = 'autocomplete-item';
      item.onclick = () => {
        usernameInput.value = user.username;
        hideAutocomplete();
        selectUser(user.username, user.platform);
      };

      const nameSpan = document.createElement('span');
      nameSpan.className = 'autocomplete-name';
      nameSpan.textContent = user.display_name;
      appendPlatformBadge(nameSpan, user.platform);

      const badge = document.createElement('span');
      badge.className = 'autocomplete-badge ' + (isOnline ? 'online' : 'msgs');
      badge.textContent = isOnline ? 'online' : (user.total_messages + ' msgs');

      item.appendChild(nameSpan);
      item.appendChild(badge);

      return item;
    }

    function updateAutocompleteSelection(items) {
      items.forEach((item, i) => {
        if (i === selectedAutocompleteIndex) {
          item.classList.add('selected');
        } else {
          item.classList.remove('selected');
        }
      });
    }

    function hideAutocomplete() {
      autocompleteDropdown.classList.remove('visible');
      selectedAutocompleteIndex = -1;
    }

    async function fetchLeaderboard() {
      if (!leaderboard) return;
      if (sidebarContextMode !== 'messages') return;
      try {
        const response = await fetch(apiUrl('/stats/leaderboard', { limit: 10 }));
        if (!response.ok) throw new Error('API Error');

        const data = await response.json();
        if (sidebarContextMode !== 'messages') return;
        if (data.total_users != null) totalLeaderboardUsers = data.total_users;
        renderLeaderboard(data.leaderboard);
      } catch (error) {
        console.error('Error loading leaderboard:', error);
      }
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

    async function fetchActiveChatters() {
      try {
        const response = await fetch(apiUrl('/stats/active-chatters'));
        if (!response.ok) throw new Error('API Error');

        const data = await response.json();
        allActiveChatters = data.chatters;
        totalLeaderboardUsers = data.total_users;

        // Update online count
        onlineCountEl.textContent = data.count;

        // Track users seen online for autocomplete
        allActiveChatters.forEach(chatter => {
          seenOnlineUsers.set(`${chatter.platform || 'twitch'}:${chatter.username}`, {
            display_name: chatter.display_name,
            platform: chatter.platform || 'twitch',
            last_seen: Date.now()
          });
        });

        renderActiveChatters(allActiveChatters);
      } catch (error) {
        console.error('Error loading active chatters:', error);
        activeChattersList.textContent = '';
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'Erro ao carregar';
        activeChattersList.appendChild(empty);
      }
    }

    async function fetchChatActivity() {
      try {
        const response = await fetch(apiUrl('/stats/chat-activity'));
        if (!response.ok) throw new Error('API Error');

        const data = await response.json();
        renderChatActivity(data);
      } catch (error) {
        console.error('Error loading chat activity:', error);
      }
    }

    function renderChatActivity(data) {
      chatActivityChart.textContent = '';

      // Get current hour in Brasília timezone (UTC-3)
      const now = new Date();
      const utcHour = now.getUTCHours();
      const currentBrtHour = (utcHour - 3 + 24) % 24;

      // Hours are already in Brasília timezone (UTC-3)
      const maxCount = Math.max(...data.activity.map(a => a.count), 1);

      data.activity.forEach(a => {
        const wrapper = document.createElement('div');
        wrapper.className = 'bar-wrapper';
        wrapper.dataset.tooltip = a.hour + 'h: ' + a.count.toLocaleString('pt-BR') + ' msgs';

        const bar = document.createElement('div');
        bar.className = 'bar' + (a.hour === currentBrtHour ? ' current' : '');
        // Use square root scaling to make small values more visible
        const ratio = a.count / maxCount;
        const height = a.count > 0 ? Math.max(Math.sqrt(ratio) * 100, 8) : 2;
        bar.style.height = height + '%';

        wrapper.appendChild(bar);
        chatActivityChart.appendChild(wrapper);
      });

      totalTodayEl.textContent = data.total_today.toLocaleString('pt-BR');
      peakInfoEl.textContent = data.peak_hour + 'h (' + data.peak_count + ' msgs)';
    }

    async function fetchUniqueChatters() {
      try {
        const response = await fetch(apiUrl('/stats/unique-chatters'));
        if (!response.ok) throw new Error('API Error');

        const data = await response.json();
        renderUniqueChatters(data);
      } catch (error) {
        console.error('Error loading unique chatters:', error);
      }
    }

    function renderUniqueChatters(data) {
      uniqueChattersChart.textContent = '';

      // Get current hour in Brasília timezone (UTC-3)
      const now = new Date();
      const utcHour = now.getUTCHours();
      const currentBrtHour = (utcHour - 3 + 24) % 24;

      // Hours are already in Brasília timezone (UTC-3)
      const maxCount = Math.max(...data.activity.map(a => a.count), 1);

      data.activity.forEach(a => {
        const wrapper = document.createElement('div');
        wrapper.className = 'bar-wrapper';
        wrapper.dataset.tooltip = a.hour + 'h: ' + a.count.toLocaleString('pt-BR') + ' usuarios';

        const bar = document.createElement('div');
        bar.className = 'bar' + (a.hour === currentBrtHour ? ' current' : '');
        // Use square root scaling to make small values more visible
        const ratio = a.count / maxCount;
        const height = a.count > 0 ? Math.max(Math.sqrt(ratio) * 100, 8) : 2;
        bar.style.height = height + '%';

        wrapper.appendChild(bar);
        uniqueChattersChart.appendChild(wrapper);
      });

      uniqueTotalEl.textContent = data.total_unique.toLocaleString('pt-BR');
      uniquePeakEl.textContent = data.peak_hour + 'h (' + data.peak_count + ' usuarios)';
    }

    async function fetchOverallActivity() {
      try {
        const response = await fetch(apiUrl('/stats/overall-activity'));
        if (!response.ok) throw new Error('API Error');

        const data = await response.json();
        renderOverallActivity(data);
      } catch (error) {
        console.error('Error loading overall activity:', error);
      }
    }

    async function fetch7TVEmotes() {
      try {
        // Fetch global 7TV emotes
        const globalRes = await fetch('https://7tv.io/v3/emote-sets/global');
        if (globalRes.ok) {
          const globalData = await globalRes.json();
          if (globalData.emotes) {
            globalData.emotes.forEach(emote => {
              sevenTVEmotes.set(emote.name, `https://cdn.7tv.app/emote/${emote.id}/1x.webp`);
            });
          }
        }

        // Fetch channel emotes for omeiaum (specific emote set)
        const channelRes = await fetch('https://7tv.io/v3/emote-sets/01HR3ABJ800007QJQMTQH1J05C');
        if (channelRes.ok) {
          const channelData = await channelRes.json();
          if (channelData.emotes) {
            channelData.emotes.forEach(emote => {
              sevenTVEmotes.set(emote.name, `https://cdn.7tv.app/emote/${emote.id}/1x.webp`);
            });
          }
        }

        console.log('Loaded ' + sevenTVEmotes.size + ' 7TV emotes');
        refreshEmoteNotes();
        renderExportNerdEmote();
      } catch (error) {
        console.error('Error loading 7TV emotes:', error);
      }
    }

    function renderOverallActivity(data) {
      overallActivityChart.textContent = '';
      averageActivityChart.textContent = '';

      // Hours are already in Brasília timezone (UTC-3)
      const maxCount = Math.max(...data.activity.map(a => a.count), 1);
      const avgSeries = data.average_activity || [];
      const maxAvg = Math.max(...avgSeries.map(a => a.count), 1);

      data.activity.forEach(a => {
        const wrapper = document.createElement('div');
        wrapper.className = 'bar-wrapper';
        wrapper.dataset.tooltip = a.hour + 'h: ' + a.count.toLocaleString('pt-BR') + ' msgs (total)';

        const bar = document.createElement('div');
        bar.className = 'bar';
        // Use square root scaling to make small values more visible
        const ratio = a.count / maxCount;
        const height = a.count > 0 ? Math.max(Math.sqrt(ratio) * 100, 8) : 2;
        bar.style.height = height + '%';

        wrapper.appendChild(bar);
        overallActivityChart.appendChild(wrapper);
      });

      avgSeries.forEach(a => {
        const wrapper = document.createElement('div');
        wrapper.className = 'bar-wrapper';
        wrapper.dataset.tooltip = a.hour + 'h: ~' + a.count.toLocaleString('pt-BR') + ' msgs/dia';

        const bar = document.createElement('div');
        bar.className = 'bar';
        const ratio = a.count / maxAvg;
        const height = a.count > 0 ? Math.max(Math.sqrt(ratio) * 100, 8) : 2;
        bar.style.height = height + '%';

        wrapper.appendChild(bar);
        averageActivityChart.appendChild(wrapper);
      });

      overallTotalEl.textContent = data.total_messages.toLocaleString('pt-BR');
      overallPeakEl.textContent = data.peak_hour + 'h (' + data.peak_count.toLocaleString('pt-BR') + ' msgs)';
      averageDaysEl.textContent = (data.days || 0).toLocaleString('pt-BR');
      const avgPeak = data.avg_peak_count != null
        ? Number(data.avg_peak_count).toLocaleString('pt-BR', { maximumFractionDigits: 1 })
        : '0';
      averagePeakEl.textContent = (data.avg_peak_hour ?? 0) + 'h (~' + avgPeak + ' msgs/dia)';
    }

    function renderTopEmotes(container, emotes, { showRank = true } = {}) {
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

    function renderEmoteRankingList(container, emotes, { filter = '', preserveRank = true, limit = null } = {}) {
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
          emoteRankingVisible += EMOTE_RANKING_PAGE;
          renderFilteredEmoteRanking();
        });
        container.appendChild(more);
      }
    }

    function renderFilteredEmoteRanking() {
      const list = emoteRankingCache && emoteRankingCache.emotes;
      renderEmoteRankingList(
        document.getElementById('emote-ranking-list'),
        list,
        { filter: emoteRankingFilter, preserveRank: true, limit: emoteRankingVisible }
      );
      const note = document.getElementById('note-emote-ranking');
      if (note && emoteRankingCache) {
        const label = getPeriodLabel();
        const base = 'Todos os emotes do catalogo por usos (' + label + ') — clique para detalhes';
        note.textContent = base +
          ' · ' + (emoteRankingCache.total_emotes || 0).toLocaleString('pt-BR') +
          ' emotes · ' + (emoteRankingCache.total_uses || 0).toLocaleString('pt-BR') + ' usos';
      }
      updateEmotePareto(list || []);
    }

    function updateEmotePareto(emotes) {
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

    async function fetchEmoteRanking(force = false) {
      if (emoteRankingCache && !force) {
        renderFilteredEmoteRanking();
        return emoteRankingCache;
      }
      const listEl = document.getElementById('emote-ranking-list');
      if (listEl && currentSection === 'emotes') {
        listEl.innerHTML = '<div class="empty-state">Carregando...</div>';
      }
      try {
        const response = await fetch(apiUrl('/stats/emotes/ranking'));
        if (!response.ok) throw new Error('API Error');
        emoteRankingCache = await response.json();
        emoteRankingVisible = EMOTE_RANKING_PAGE;
        renderFilteredEmoteRanking();
        return emoteRankingCache;
      } catch (error) {
        console.error('Error fetching emote ranking:', error);
        if (listEl) listEl.innerHTML = '<div class="empty-state">Erro ao carregar ranking</div>';
        return null;
      }
    }

    async function fetchChatTopEmotes() {
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

    async function fetchLeastUsedEmotes() {
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

    function renderSimpleRankList(container, entries, countKey) {
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

        const rank = document.createElement('span');
        rank.className = 'rank';
        rank.textContent = '#' + (entry.rank || '');

        const name = document.createElement('span');
        name.className = 'entry-name';
        setEntryName(name, entry.display_name || entry.username, entry.platform);

        const count = document.createElement('span');
        count.className = 'entry-count';
        const val = entry[countKey] != null ? entry[countKey] : entry.count;
        count.textContent = (val || 0).toLocaleString('pt-BR');

        item.appendChild(rank);
        item.appendChild(name);
        item.appendChild(count);
        container.appendChild(item);
      });
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
        const response = await fetch(apiUrl('/stats/emotes/diversidade', { period: currentPeriod }));
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

    async function fetchEmoteDetail(emoteName) {
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
            ? () => selectUser(data.creator_username)
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

    function navigateToEmote(emoteName, updateUrl = true) {
      if (!emoteName) return;
      currentEmoteName = emoteName;
      currentUsername = '';
      currentUserPlatform = null;
      hideRanqueadaBoardView();
      hideError();
      generalView.classList.add('hidden');
      statsSection.classList.remove('visible');
      if (emoteView) emoteView.classList.add('visible');
      chatGeralBtn.classList.remove('active');
      updateNavActive('section', 'emotes');
      if (updateUrl) pushEmoteURL(emoteName);
      fetchEmoteDetail(emoteName);
    }

    function pushEmoteURL(emoteName) {
      const url = BASE_PATH + '/emotes/' + encodeURIComponent(emoteName) + buildFilterQuery(currentPlatform, currentPeriod);
      history.pushState({
        mode: 'emote',
        emoteName,
        platform: currentPlatform,
        period: currentPeriod,
      }, '', url);
    }

    async function loadRandomNavEmoteIcon() {
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

    let emotePositionUsersCache = null;

    function renderEmotePositionBar(container, positions, label, clickable = false) {
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

    async function togglePositionUsersList(container, groupKey, groupLabel, segmentCls) {
      // Fetch data if not cached
      if (!emotePositionUsersCache) {
        const loadingPanel = document.createElement('div');
        loadingPanel.className = 'position-users-panel';
        loadingPanel.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-muted);">Carregando...</div>';
        container.appendChild(loadingPanel);

        try {
          const response = await fetch(apiUrl('/stats/emote-position-users'));
          if (!response.ok) throw new Error('API error');
          emotePositionUsersCache = await response.json();
        } catch (error) {
          console.error('Error fetching emote position users:', error);
          loadingPanel.innerHTML = '<div style="padding: 1rem; text-align: center; color: #e74c3c;">Erro ao carregar</div>';
          return;
        }
        loadingPanel.remove();
      }

      const users = emotePositionUsersCache[groupKey] || [];
      renderPositionUsersPanel(container, users, groupLabel, segmentCls);
    }

    function renderPositionUsersPanel(container, users, title, segmentCls) {
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
          name.onclick = () => selectUser(user.username, user.platform);

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

    async function fetchChatEmotePositions() {
      try {
        const response = await fetch(apiUrl('/stats/emote-position-users'));
        if (response.ok) {
          const data = await response.json();
          emotePositionUsersCache = data;

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

    function formatDate(dateStr) {
      if (!dateStr) return '—';
      const [y, m, d] = dateStr.split('-');
      return d + '/' + m + '/' + y;
    }

    async function fetchSmokeTime() {
      try {
        const response = await fetch(apiUrl('/stats/smoke-time'));
        if (!response.ok) throw new Error('API Error');
        const data = await response.json();
        renderSmokeTime(data);
      } catch (error) {
        console.error('Error loading smoke time:', error);
        const el = document.getElementById('tragadores-leaderboard');
        if (el) el.innerHTML = '<div class="empty-state">Erro ao carregar</div>';
      }
    }

    function renderSmokeTime(data) {
      if (document.getElementById('tragadores-leaderboard')) {
        renderTragadoresLeaderboard(data.leaderboard);
      }
      renderTragadoresHighlights(data);
      renderTragadores5DayChart(data.last_5_days || []);
      renderTragadoresLongestStreaks(data.longest_streaks);
      renderTragadoresToday(data.today);
      renderRodaCalendar(data);
      renderFirstToday(data.first_today);

      const highlights = document.getElementById('tragadores-highlights');
      const todayEl = document.getElementById('tragadores-today');
      if (highlights) highlights.style.display = '';
      if (todayEl) todayEl.style.display = '';
    }

    function renderTragadoresLeaderboard(leaderboard) {
      const container = document.getElementById('tragadores-leaderboard');
      if (!container) return;
      container.textContent = '';

      if (!leaderboard || leaderboard.length === 0) {
        container.innerHTML = '<div class="empty-state">Nenhum tragador ainda. Seja o primeiro às 16:20!</div>';
        return;
      }

      leaderboard.forEach((entry, i) => {
        const row = document.createElement('div');
        row.className = 'tragador-row';

        const left = document.createElement('div');
        left.className = 'tragador-left';

        const rank = document.createElement('span');
        rank.className = 'tragador-rank';
        if (i === 0) rank.classList.add('top1');
        else if (i === 1) rank.classList.add('top2');
        else if (i === 2) rank.classList.add('top3');
        rank.textContent = '#' + (i + 1);

        const name = document.createElement('span');
        name.className = 'tragador-name';
        name.textContent = entry.display_name;
        name.title = entry.username;
        name.onclick = () => selectUser(entry.username, entry.platform);
        appendPlatformBadge(name, entry.platform);

        left.appendChild(rank);
        left.appendChild(name);

        const right = document.createElement('div');
        right.className = 'tragador-right';

        const count = document.createElement('span');
        count.className = 'tragador-count';
        count.textContent = entry.count + ' tragadas';

        const streak = document.createElement('span');
        streak.className = 'tragador-streak';
        if (entry.streak_current > 0) {
          streak.classList.add('active');
          streak.textContent = '🔥' + entry.streak_current;
        } else {
          streak.textContent = '—';
        }
        streak.title = entry.streak_current > 0
          ? 'Sequência atual: ' + entry.streak_current + ' dias'
          : 'Sem sequência ativa';

        right.appendChild(count);
        right.appendChild(streak);
        row.appendChild(left);
        row.appendChild(right);
        container.appendChild(row);
      });
    }

    function renderTragadoresHighlights(data) {
      const bestEl = document.getElementById('hl-best-day');
      const uniqueEl = document.getElementById('hl-unique');
      const totalEl = document.getElementById('hl-total');
      const streakEl = document.getElementById('hl-streak');
      const firstEl = document.getElementById('hl-first');

      if (bestEl) {
        if (data.best_day && data.best_day.participants > 0) {
          bestEl.textContent =
            data.best_day.participants + ' pererecos (' + formatDate(data.best_day.date) + ')';
        } else {
          bestEl.textContent = '—';
        }
      }

      if (uniqueEl) {
        uniqueEl.textContent = (data.total_unique_participants || 0).toLocaleString('pt-BR');
      }
      if (totalEl) {
        totalEl.textContent = (data.total_sessions || 0).toLocaleString('pt-BR');
      }

      if (streakEl) {
        if (data.longest_streaks && data.longest_streaks.length > 0) {
          const top = data.longest_streaks[0];
          streakEl.textContent = top.display_name + ' (' + top.streak + ' dias)';
        } else {
          streakEl.textContent = '—';
        }
      }

      if (firstEl) {
        firstEl.textContent = data.first_session ? formatDate(data.first_session) : '—';
      }
    }

    function renderTragadores5DayChart(last5Days) {
      const chart = document.getElementById('tragadores-5day-chart');
      const labels = document.getElementById('tragadores-5day-labels');
      if (!chart || !labels) return;
      chart.textContent = '';
      labels.textContent = '';

      if (!last5Days || last5Days.length === 0) return;

      // Display oldest → newest (left to right)
      const days = [...last5Days].reverse();
      const maxCount = Math.max(...days.map(d => d.participants), 1);

      days.forEach(day => {
        const wrapper = document.createElement('div');
        wrapper.className = 'bar-wrapper';
        wrapper.dataset.tooltip = formatDate(day.date) + ': ' + day.participants + ' tragadores';

        const bar = document.createElement('div');
        bar.className = 'bar';
        const ratio = day.participants / maxCount;
        const height = day.participants > 0 ? Math.max(Math.sqrt(ratio) * 100, 8) : 2;
        bar.style.height = height + '%';

        wrapper.appendChild(bar);
        chart.appendChild(wrapper);

        const label = document.createElement('span');
        label.className = 'chart-label';
        const parts = day.date.split('-');
        label.textContent = parts[2] + '/' + parts[1];
        labels.appendChild(label);
      });
    }

    function renderTragadoresLongestStreaks(streaks) {
      const container = document.getElementById('tragadores-streaks-list');
      if (!container) return;
      container.textContent = '';

      if (!streaks || streaks.length === 0) {
        container.innerHTML = '<div class="empty-state">Nenhuma sequência ainda</div>';
        return;
      }

      streaks.forEach((entry, i) => {
        const row = document.createElement('div');
        row.className = 'tragador-streak-row';

        const name = document.createElement('span');
        name.className = 'tragador-name';
        name.textContent = '#' + (i + 1) + ' ' + entry.display_name;
        name.onclick = () => selectUser(entry.username, entry.platform);
        appendPlatformBadge(name, entry.platform);

        const days = document.createElement('span');
        days.className = 'tragador-streak-days';
        days.textContent = entry.streak + ' dias 🔥';

        row.appendChild(name);
        row.appendChild(days);
        container.appendChild(row);
      });
    }

    function renderTragadoresToday(today) {
      const el = document.getElementById('tragadores-today');
      if (!el) return;
      const count = (today && today.participants) || 0;
      if (count > 0) {
        el.innerHTML = 'Hoje: <strong>' + count + '</strong> tragador' +
          (count > 1 ? 'es' : '') + ' já acendeu o seu às 16:20 🔥';
      } else {
        el.innerHTML = 'Hoje: ninguém tragou ainda... Aguardando as 16:20 👀';
      }
    }

    function filterActiveChatters(query) {
      const filtered = query
        ? allActiveChatters.filter(c =>
          c.username.toLowerCase().includes(query.toLowerCase()) ||
          c.display_name.toLowerCase().includes(query.toLowerCase())
        )
        : allActiveChatters;
      renderActiveChatters(filtered);
    }

    function renderLeaderboard(entries) {
      leaderboard.textContent = '';
      if (entries.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'Nenhum dado';
        leaderboard.appendChild(empty);
        return;
      }

      entries.forEach(entry => {
        const entryPlatform = entry.platform || 'twitch';
        const isSelected = currentUsername
          && entry.username === currentUsername.toLowerCase()
          && (currentUserPlatform === entryPlatform || currentPlatform === entryPlatform);
        const div = document.createElement('div');
        div.dataset.username = entry.username;
        div.dataset.platform = entryPlatform;
        div.className = 'leaderboard-entry' + (isSelected ? ' selected' : '');
        div.onclick = () => selectUser(entry.username, entryPlatform);

        const rankSpan = document.createElement('span');
        rankSpan.className = 'rank';
        rankSpan.textContent = '#' + entry.rank;

        const nameSpan = document.createElement('span');
        nameSpan.className = 'entry-name';
        setEntryName(nameSpan, entry.display_name, entryPlatform);

        const countSpan = document.createElement('span');
        countSpan.className = 'entry-count';
        countSpan.textContent = entry.message_count.toLocaleString('pt-BR');

        div.appendChild(rankSpan);
        div.appendChild(nameSpan);
        div.appendChild(countSpan);
        leaderboard.appendChild(div);
      });
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

    function renderActiveChatters(chatters) {
      activeChattersList.textContent = '';
      if (!chatters || chatters.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'Nenhum perereco ativo';
        activeChattersList.appendChild(empty);
        return;
      }

      chatters.forEach(chatter => {
        const div = document.createElement('div');
        div.className = 'active-chatter';
        div.onclick = () => selectUser(chatter.username, chatter.platform);

        const leftGroup = document.createElement('div');
        leftGroup.className = 'active-chatter-left';

        const rankSpan = document.createElement('span');
        rankSpan.className = 'active-chatter-rank';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'active-chatter-name';
        setEntryName(nameSpan, chatter.display_name, chatter.platform);

        let colorClass = null;
        if (chatter.rank && totalLeaderboardUsers > 0) {
          rankSpan.textContent = '#' + chatter.rank;
          const percentile = (chatter.rank / totalLeaderboardUsers) * 100;
          if (percentile <= 3) colorClass = 'gold';
          else if (percentile <= 7) colorClass = 'silver';
          else if (percentile <= 15) colorClass = 'bronze';
          if (colorClass) {
            rankSpan.classList.add(colorClass);
            nameSpan.classList.add(colorClass);
          }
        } else {
          rankSpan.textContent = '-';
        }

        leftGroup.appendChild(rankSpan);
        leftGroup.appendChild(nameSpan);

        const countSpan = document.createElement('span');
        countSpan.className = 'active-chatter-count';
        countSpan.textContent = chatter.message_count + ' msgs';

        div.appendChild(leftGroup);
        div.appendChild(countSpan);
        activeChattersList.appendChild(div);
      });
    }

    function updateLeaderboardSelection() {
      document.querySelectorAll('.leaderboard-entry').forEach(el => {
        const matchesUser = currentUsername && el.dataset.username === currentUsername.toLowerCase();
        const matchesPlatform = !currentUserPlatform || el.dataset.platform === currentUserPlatform;
        el.classList.toggle('selected', matchesUser && matchesPlatform);
      });
    }

    function selectUser(username, platform = null, updateUrl = true) {
      usernameInput.value = username;
      currentUsername = username;
      currentEmoteName = '';
      currentUserPlatform = platform || (currentPlatform !== 'all' ? currentPlatform : null);
      hideRanqueadaBoardView();
      hideError();
      generalView.classList.add('hidden');
      if (emoteView) emoteView.classList.remove('visible');
      chatGeralBtn.classList.remove('active');
      updateNavActive('user');
      if (updateUrl) {
        pushUserURL(username, currentUserPlatform || currentPlatform, currentPeriod);
      }
      fetchUserStats();
      updateLeaderboardSelection();
    }

    function parseAppPath() {
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

    function getParamsFromURL() {
      const params = new URLSearchParams(window.location.search);
      return {
        platform: params.get('platform') || 'all',
        period: params.get('period') || 'all',
        start_date: params.get('start_date') || null,
        end_date: params.get('end_date') || null,
        page: parseInt(params.get('page') || '1', 10) || 1,
      };
    }

    function buildFilterQuery(platform, period) {
      const params = new URLSearchParams();
      if (platform && platform !== 'all') params.set('platform', platform);
      if (period && period !== 'all') params.set('period', period);
      if (period === 'custom' && customStartDate && customEndDate) {
        params.set('start_date', customStartDate);
        params.set('end_date', customEndDate);
      }
      const qs = params.toString();
      return qs ? '?' + qs : '';
    }

    function pushUserURL(username, platform, period) {
      const url = BASE_PATH + '/' + encodeURIComponent(username) + buildFilterQuery(platform, period);
      history.pushState({ username, platform, period, mode: 'user' }, '', url);
    }

    function pushHomeURL() {
      const url = BASE_PATH + '/' + buildFilterQuery(currentPlatform, currentPeriod);
      history.pushState({ home: true, mode: 'home', section: 'home', platform: currentPlatform, period: currentPeriod }, '', url);
    }

    function pushSectionURL(section) {
      let pathSeg;
      if (section === 'emotes-condensadas') {
        pathSeg = 'emotes/condensadas';
      } else {
        pathSeg = section;
      }
      const url = BASE_PATH + '/' + pathSeg + buildFilterQuery(currentPlatform, currentPeriod);
      history.pushState({
        mode: 'section',
        section,
        platform: currentPlatform,
        period: currentPeriod,
      }, '', url);
    }

    function applyFiltersFromState(state) {
      if (state.platform) {
        currentPlatform = state.platform;
        platformFilterBtns.forEach(btn => {
          btn.classList.toggle('active', btn.dataset.platform === state.platform);
        });
        if (currentPlatform !== 'all') {
          currentUserPlatform = currentPlatform;
        }
      }
      if (state.period && state.period !== 'undefined' && state.period !== 'null') {
        currentPeriod = state.period;
        filterBtns.forEach(btn => {
          btn.classList.toggle('active', btn.dataset.period === state.period);
        });
      } else if (!currentPeriod || currentPeriod === 'undefined') {
        currentPeriod = 'all';
      }
      if (state.period === 'custom' && state.start_date && state.end_date) {
        customStartDate = state.start_date;
        customEndDate = state.end_date;
        if (customDateRow) customDateRow.classList.add('visible');
        syncCustomDateInputs();
        if (customStartInput) customStartInput.value = customStartDate;
        if (customEndInput) customEndInput.value = customEndDate;
      } else if (state.period && state.period !== 'custom') {
        customStartDate = null;
        customEndDate = null;
        if (customDateRow) customDateRow.classList.remove('visible');
      }
      updatePeriodLabels();
    }

    function applyRoute(route, updateUrl = false) {
      const params = getParamsFromURL();
      if (route.mode === 'user') {
        applyFiltersFromState(params);
        selectUser(route.username, params.platform !== 'all' ? params.platform : null, updateUrl);
        return;
      }
      if (route.mode === 'emote') {
        applyFiltersFromState(params);
        navigateToEmote(route.emoteName, updateUrl);
        return;
      }
      if (route.mode === 'ranqueada-board') {
        applyFiltersFromState(params);
        navigateToRanqueadaBoard(route.boardId, updateUrl, params.page || 1, route.boardSource || null);
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
          navigateToRanqueadaBoard(
            event.state.boardId,
            false,
            event.state.page || 1,
            event.state.boardSource || null
          );
          return;
        }
        if (event.state.mode === 'emote' || event.state.emoteName) {
          applyFiltersFromState(event.state);
          navigateToEmote(event.state.emoteName, false);
          return;
        }
        if (event.state.mode === 'user' || event.state.username) {
          applyFiltersFromState(event.state);
          usernameInput.value = event.state.username;
          currentUsername = event.state.username;
          currentEmoteName = '';
          hideRanqueadaBoardView();
          currentUserPlatform = event.state.platform && event.state.platform !== 'all'
            ? event.state.platform
            : (currentPlatform !== 'all' ? currentPlatform : null);
          generalView.classList.add('hidden');
          if (emoteView) emoteView.classList.remove('visible');
          chatGeralBtn.classList.remove('active');
          updateNavActive('user');
          fetchUserStats(false);
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

    function initFromURL() {
      const route = parseAppPath();
      const params = getParamsFromURL();
      applyFiltersFromState(params);

      if (route.mode === 'user') {
        usernameInput.value = route.username;
        currentUsername = route.username;
        currentUserPlatform = params.platform !== 'all' ? params.platform : null;
        generalView.classList.add('hidden');
        if (emoteView) emoteView.classList.remove('visible');
        chatGeralBtn.classList.remove('active');
        updateNavActive('user');
        history.replaceState(
          { mode: 'user', username: route.username, platform: params.platform, period: params.period },
          '',
          window.location.pathname + window.location.search
        );
        fetch7TVEmotes();
        loadCoreStats();
        loadRandomNavEmoteIcon();
        fetchUserStats();
        updateLeaderboardSelection();
        return;
      }

      if (route.mode === 'emote') {
        history.replaceState(
          { mode: 'emote', emoteName: route.emoteName, platform: params.platform, period: params.period },
          '',
          window.location.pathname + window.location.search
        );
        fetch7TVEmotes();
        loadCoreStats();
        loadRandomNavEmoteIcon();
        navigateToEmote(route.emoteName, false);
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
        fetch7TVEmotes();
        loadCoreStats();
        loadRandomNavEmoteIcon();
        navigateToRanqueadaBoard(route.boardId, false, params.page || 1, route.boardSource || null);
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
      fetch7TVEmotes();
      loadRandomNavEmoteIcon();
      showSectionPanel(section);
      if (section === 'home') {
        loadInitialData();
      } else {
        loadCoreStats();
        loadSectionData(section);
      }
    }

    function showError(msg) {
      errorMessage.textContent = msg;
      errorMessage.classList.add('visible');
    }

    function hideError() {
      errorMessage.classList.remove('visible');
    }

    // Export modal
    const exportBtn = document.getElementById('export-btn');
    const exportModal = document.getElementById('export-modal');
    const exportModalClose = document.getElementById('export-modal-close');
    const exportStartInput = document.getElementById('export-start-date');
    const exportEndInput = document.getElementById('export-end-date');
    const exportDownloadBtn = document.getElementById('export-download-btn');
    const exportNerdEmote = document.getElementById('export-nerd-emote');

    function syncExportDateInputs() {
      const today = todayBRTISO();
      if (exportStartInput) {
        exportStartInput.min = COLLECTION_START;
        exportStartInput.max = today;
        if (!exportStartInput.value) exportStartInput.value = COLLECTION_START;
      }
      if (exportEndInput) {
        exportEndInput.min = COLLECTION_START;
        exportEndInput.max = today;
        if (!exportEndInput.value) exportEndInput.value = today;
      }
    }

    function renderExportNerdEmote() {
      if (!exportNerdEmote) return;
      const cached = sevenTVEmotes.get('NERD');
      if (cached) {
        exportNerdEmote.src = cached;
        exportNerdEmote.style.display = '';
        return;
      }
      fetch(apiUrl('/stats/emotes/search', { q: 'NERD' }))
        .then((res) => (res.ok ? res.json() : []))
        .then((results) => {
          const hit = (results || []).find((e) => e.emote_name === 'NERD') || (results || [])[0];
          if (!hit) return;
          const url = `https://cdn.7tv.app/emote/${hit.emote_id}/2x.webp`;
          sevenTVEmotes.set('NERD', url);
          exportNerdEmote.src = url;
          exportNerdEmote.style.display = '';
        })
        .catch(() => {});
    }

    function openExportModal() {
      if (!exportModal) return;
      syncExportDateInputs();
      renderExportNerdEmote();
      exportModal.classList.add('visible');
    }

    function closeExportModal() {
      if (exportModal) exportModal.classList.remove('visible');
    }

    function startMessageExport() {
      const start = exportStartInput && exportStartInput.value;
      const end = exportEndInput && exportEndInput.value;
      if (!start || !end) {
        alert('Selecione as datas de inicio e fim.');
        return;
      }
      if (start > end) {
        alert('A data inicial deve ser anterior ou igual a data final.');
        return;
      }
      const params = new URLSearchParams({
        platform: currentPlatform,
        start_date: start,
        end_date: end,
      });
      closeExportModal();
      window.location.href = `${API_BASE}/export/messages?${params.toString()}`;
    }

    if (exportBtn) exportBtn.addEventListener('click', openExportModal);
    if (exportModalClose) exportModalClose.addEventListener('click', closeExportModal);
    if (exportDownloadBtn) exportDownloadBtn.addEventListener('click', startMessageExport);
    if (exportModal) {
      exportModal.addEventListener('click', (e) => {
        if (e.target === exportModal) closeExportModal();
      });
    }

    // Feedback modal
    const feedbackBtn = document.getElementById('feedback-btn');
    const feedbackModal = document.getElementById('feedback-modal');
    const modalClose = document.getElementById('modal-close');
    const feedbackForm = document.getElementById('feedback-form');
    const feedbackType = document.getElementById('feedback-type');
    const feedbackMessage = document.getElementById('feedback-message');
    const feedbackSubmit = document.getElementById('feedback-submit');
    const feedbackResult = document.getElementById('feedback-result');
    const charCount = document.getElementById('char-count');

    feedbackBtn.addEventListener('click', () => {
      feedbackModal.classList.add('visible');
      feedbackResult.style.display = 'none';
      feedbackForm.reset();
      charCount.textContent = '0';
    });

    modalClose.addEventListener('click', () => {
      feedbackModal.classList.remove('visible');
    });

    feedbackModal.addEventListener('click', (e) => {
      if (e.target === feedbackModal) {
        feedbackModal.classList.remove('visible');
      }
    });

    feedbackMessage.addEventListener('input', () => {
      charCount.textContent = feedbackMessage.value.length;
    });

    feedbackForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      feedbackSubmit.disabled = true;
      feedbackSubmit.textContent = 'Enviando...';
      feedbackResult.style.display = 'none';

      try {
        const response = await fetch(`${API_BASE}/feedback`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            type: feedbackType.value,
            message: feedbackMessage.value
          })
        });

        if (response.ok) {
          feedbackResult.className = 'form-message success';
          feedbackResult.textContent = 'Enviado com sucesso! Obrigado pelo feedback.';
          feedbackResult.style.display = 'block';
          feedbackForm.reset();
          charCount.textContent = '0';
          setTimeout(() => {
            feedbackModal.classList.remove('visible');
          }, 2000);
        } else {
          const data = await response.json();
          throw new Error(data.detail || 'Erro ao enviar');
        }
      } catch (error) {
        feedbackResult.className = 'form-message error';
        feedbackResult.textContent = error.message || 'Erro ao enviar. Tente novamente.';
        feedbackResult.style.display = 'block';
      } finally {
        feedbackSubmit.disabled = false;
        feedbackSubmit.textContent = 'Enviar';
      }
    });

    // Emote search autocomplete + ranking filter
    async function fetchEmoteAutocomplete(query) {
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
        selectedEmoteAutocompleteIndex = -1;
      } catch (e) {
        console.error(e);
      }
    }

    if (emoteSearchInput) {
      emoteSearchInput.addEventListener('input', () => {
        const q = emoteSearchInput.value.trim();
        emoteRankingFilter = q;
        emoteRankingVisible = EMOTE_RANKING_PAGE;
        if (currentSection === 'emotes') {
          renderFilteredEmoteRanking();
        }
        if (emoteSearchTimeout) clearTimeout(emoteSearchTimeout);
        if (q.length < 1) {
          if (emoteAutocomplete) emoteAutocomplete.classList.remove('visible');
          return;
        }
        emoteSearchTimeout = setTimeout(() => fetchEmoteAutocomplete(q), 150);
      });
      emoteSearchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const name = emoteSearchInput.value.trim();
          if (name) navigateToEmote(name);
        }
      });
    }
    const emoteSearchBtn = document.getElementById('emote-search-btn');
    if (emoteSearchBtn) {
      emoteSearchBtn.addEventListener('click', () => {
        const name = (emoteSearchInput && emoteSearchInput.value.trim()) || '';
        if (name) navigateToEmote(name);
      });
    }

    const btnEmotesCondensadas = document.getElementById('btn-emotes-condensadas');
    if (btnEmotesCondensadas) {
      btnEmotesCondensadas.addEventListener('click', () => {
        navigateToSection('emotes');
        const details = document.getElementById('emotes-ranking-details');
        if (details) details.open = false;
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }
    const btnEmotesBackRanking = document.getElementById('btn-emotes-back-ranking');
    if (btnEmotesBackRanking) {
      btnEmotesBackRanking.addEventListener('click', () => {
        navigateToSection('emotes');
      });
    }

    const emotesRankingDetails = document.getElementById('emotes-ranking-details');
    if (emotesRankingDetails) {
      emotesRankingDetails.addEventListener('toggle', () => {
        if (emotesRankingDetails.open) {
          fetchEmoteRanking(false);
        }
      });
    }

    // Top 10 rail: collapsible + context-aware
    const top10Card = document.getElementById('top10-card');
    const top10Toggle = document.getElementById('top10-toggle');
    const top10TitleEl = document.getElementById('top10-title');
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
        sidebarContextMode = 'bonks';
        titleEl.textContent = 'Top Bonkadores';
        if (note) note.textContent = 'Quem mais usou ?bonk no período (' + getPeriodLabel() + ')';
        // Filled by Folhinha tab onLoaded — only show placeholder if empty
        if (!leaderboard.querySelector('.leaderboard-entry')) {
          leaderboard.innerHTML = '<div class="empty-state loading">Carregando...</div>';
        }
        return;
      }
      if (section === 'emotes' || section === 'emotes-condensadas') {
        sidebarContextMode = 'emotes';
        titleEl.textContent = 'Top Emotes';
        if (note) note.textContent = 'Emotes mais usados no período (' + getPeriodLabel() + ')';
        if (!leaderboard.querySelector('.leaderboard-entry')) {
          leaderboard.innerHTML = '<div class="empty-state loading">Carregando...</div>';
        }
        return;
      }
      sidebarContextMode = 'messages';
      titleEl.textContent = 'Top 10';
      if (note) {
        note.textContent = 'Quem mais mandou mensagens no periodo (' + getPeriodLabel() + ')';
      }
      fetchLeaderboard();
    }

    function renderSidebarTopEmotes(emotes) {
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
    // Ribbits do passado
    const ribbitsModal = document.getElementById('ribbits-modal');
    const ribbitsBody = document.getElementById('ribbits-body');
    const ribbitsProfileBtn = document.getElementById('ribbits-profile');
    let ribbitsFocusUser = null;
    async function openRibbits() {
      if (!ribbitsModal) return;
      ribbitsModal.classList.add('visible');
      await loadRibbit();
    }
    async function loadRibbit() {
      if (!ribbitsBody) return;
      ribbitsBody.innerHTML = '<div class="empty-state">Carregando...</div>';
      if (ribbitsProfileBtn) ribbitsProfileBtn.style.display = 'none';
      ribbitsFocusUser = null;
      try {
        const response = await fetch(apiUrl('/stats/random-message'));
        if (!response.ok) throw new Error('fail');
        const data = await response.json();
        const focus = data.focus || data;
        ribbitsBody.textContent = '';

        function appendRow(msg, kind) {
          if (!msg) return null;
          const row = document.createElement('div');
          row.className = 'ribbits-row ' + kind;
          const meta = document.createElement('div');
          meta.className = 'ribbits-meta';
          const when = new Date(msg.timestamp).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
          meta.textContent = (msg.display_name || msg.username) + ' · ' + when;
          appendPlatformBadge(meta, msg.platform);
          const text = document.createElement('div');
          text.className = 'ribbits-message';
          renderMessageWithEmotes(text, msg.message || '');
          row.appendChild(meta);
          row.appendChild(text);
          ribbitsBody.appendChild(row);
          return row;
        }

        const beforeList = Array.isArray(data.before) ? data.before : (data.before ? [data.before] : []);
        const afterList = Array.isArray(data.after) ? data.after : (data.after ? [data.after] : []);
        beforeList.forEach((m) => appendRow(m, 'context'));
        const focusRow = appendRow(focus, 'focus');
        afterList.forEach((m) => appendRow(m, 'context'));

        ribbitsFocusUser = { username: focus.username, platform: focus.platform };
        if (ribbitsProfileBtn) ribbitsProfileBtn.style.display = '';

        if (focusRow) {
          requestAnimationFrame(() => {
            focusRow.scrollIntoView({ block: 'center', behavior: 'smooth' });
          });
        }
      } catch (e) {
        ribbitsBody.innerHTML = '<div class="empty-state">Nao foi possivel carregar um ribbit</div>';
      }
    }
    ['ribbits-btn', 'ribbits-side-btn'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('click', openRibbits);
    });
    const ribbitsClose = document.getElementById('ribbits-close');
    if (ribbitsClose) ribbitsClose.addEventListener('click', () => ribbitsModal.classList.remove('visible'));
    if (ribbitsModal) {
      ribbitsModal.addEventListener('click', (e) => {
        if (e.target === ribbitsModal) ribbitsModal.classList.remove('visible');
      });
    }
    const ribbitsAgain = document.getElementById('ribbits-again');
    if (ribbitsAgain) ribbitsAgain.addEventListener('click', loadRibbit);
    if (ribbitsProfileBtn) {
      ribbitsProfileBtn.addEventListener('click', () => {
        if (!ribbitsFocusUser) return;
        ribbitsModal.classList.remove('visible');
        selectUser(ribbitsFocusUser.username, ribbitsFocusUser.platform);
      });
    }

    // Icone do Inicio: Life de dia (06:00-18:00 Brasilia), RealLife de noite
    const HOME_ICON_DAY = 'https://cdn.7tv.app/emote/01FT0SJFNR0001M6SADSSJ9P4Q/2x.webp';   // Life
    const HOME_ICON_NIGHT = 'https://cdn.7tv.app/emote/01GQWT7FJ0000DRYKWFK0ZNX75/2x.webp'; // RealLife
    function updateHomeNavIcon() {
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

    // Subathon dual timer: untilStart → remainingLive
    (function initSubathonTimer() {
      const labelEl = document.getElementById('subathon-timer-label');
      const valueEl = document.getElementById('subathon-timer-value');
      const wrapEl = document.getElementById('subathon-timer');
      if (!labelEl || !valueEl || !wrapEl) return;

      let remainingSeconds = null;
      let mode = 'untilStart';
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
        if (mode === 'untilStart' && days > 0) {
          return days + 'd ' + hms;
        }
        // Unbounded hours for remaining live (may exceed 24h)
        const totalHours = Math.floor(s / 3600);
        return (
          String(totalHours) + ':' +
          String(mins).padStart(2, '0') + ':' +
          String(secs).padStart(2, '0')
        );
      }

      function render() {
        if (remainingSeconds == null) {
          valueEl.textContent = '--:--:--';
          return;
        }
        if (mode === 'untilStart') {
          labelEl.textContent = 'Subathon começa em';
        } else {
          labelEl.textContent = 'Horas de live restantes';
        }
        if (remainingSeconds <= 0) {
          if (mode === 'remainingLive') {
            valueEl.textContent = '0:00:00';
            labelEl.textContent = 'Subathon encerrada';
            wrapEl.classList.add('ended');
          } else {
            // untilStart hit zero — wait for next sync to flip mode
            valueEl.textContent = '0d 00:00:00';
          }
          return;
        }
        wrapEl.classList.remove('ended');
        valueEl.textContent = formatCountdown(remainingSeconds);
      }

      function tick() {
        if (remainingSeconds == null) return;
        if (remainingSeconds > 0) remainingSeconds -= 1;
        render();
      }

      async function syncFromApi() {
        try {
          const res = await fetch(API_BASE + '/subathon/timer');
          if (!res.ok) throw new Error('timer http ' + res.status);
          const data = await res.json();
          mode = data.mode || 'untilStart';
          remainingSeconds = Math.max(0, Number(data.remaining_seconds) || 0);
          render();
        } catch (err) {
          console.error('Subathon timer sync failed', err);
        }
      }

      syncFromApi();
      tickTimer = setInterval(tick, 1000);
      syncTimer = setInterval(syncFromApi, 30000);
    })();

    // Initial load from URL (home or deep-linked user)
    initFromURL();
    startAutoRefresh();

    // Username history
    const usernameHistoryBtn = document.getElementById('username-history-btn');
    const usernameHistoryPopup = document.getElementById('username-history-popup');
    const usernameHistoryList = document.getElementById('username-history-list');

    usernameHistoryBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      usernameHistoryPopup.classList.toggle('open');
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.name-wrapper')) {
        usernameHistoryPopup.classList.remove('open');
      }
    });

    async function fetchUsernameHistory(username, platform = null) {
      usernameHistoryBtn.classList.remove('visible');
      usernameHistoryPopup.classList.remove('open');
      usernameHistoryList.textContent = '';

      try {
        const response = await fetch(apiUrl(
          `/stats/user/${encodeURIComponent(username)}/username-history`,
          { platform: platform || getUserPlatformParam() }
        ));
        if (!response.ok) return;

        const data = await response.json();
        if (data.past_usernames && data.past_usernames.length > 0) {
          usernameHistoryBtn.classList.add('visible');
          data.past_usernames.forEach(entry => {
            const item = document.createElement('div');
            item.className = 'past-name-item';

            const name = document.createElement('div');
            name.className = 'past-name';
            name.textContent = entry.display_name;

            const dates = document.createElement('div');
            dates.className = 'past-name-dates';
            const firstDate = new Date(entry.first_seen).toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' });
            const lastDate = new Date(entry.last_seen).toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' });
            dates.textContent = firstDate + ' — ' + lastDate;

            item.appendChild(name);
            item.appendChild(dates);
            usernameHistoryList.appendChild(item);
          });
        }
      } catch (error) {
        console.error('Error fetching username history:', error);
      }
    }

    function renderFirstToday(first) {
      const wrap = document.getElementById('first-today-wrap');
      const el = document.getElementById('hl-first-today');
      if (!wrap || !el) return;
      if (!first || !first.username) {
        wrap.style.display = 'none';
        return;
      }
      wrap.style.display = '';
      el.textContent = '';
      const name = document.createElement('span');
      name.style.cursor = 'pointer';
      name.textContent = first.display_name || first.username;
      name.addEventListener('click', () => selectUser(first.username, first.platform || null));
      el.appendChild(name);
    }

    function renderRodaCalendar(data) {
      const cal = document.getElementById('roda-calendar');
      if (!cal) return;
      cal.textContent = '';
      let series = data.last_30_days || [];
      if (!series.length && data.last_5_days) {
        series = data.last_5_days.map((d) => ({ date: d.date, count: d.participants || d.unique_users || d.count || 0 }));
      }
      series = series.map((d) => ({ date: d.date, count: d.participants != null ? d.participants : (d.count || 0) }));
      if (!series.length) {
        cal.innerHTML = '<div class="empty-state">Sem dados de calendário</div>';
        return;
      }
      const max = Math.max(1, ...series.map((d) => d.count || 0));
      series.forEach((d) => {
        const cell = document.createElement('div');
        cell.className = 'roda-cal-cell';
        const c = d.count || 0;
        cell.style.background = 'rgba(46, 204, 113, ' + (0.08 + 0.7 * (c / max)).toFixed(2) + ')';
        cell.title = (d.date || '') + ': ' + c + ' tragadores';
        cell.textContent = (d.date || '').slice(8) || '·';
        cal.appendChild(cell);
      });
    }

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

    function loadCompararSection(force = false) {
      if (compararSectionLoaded && !force) return;
      compararSectionLoaded = true;
    }

    async function runCompare() {
      const input1 = document.getElementById('compare-user1');
      const input2 = document.getElementById('compare-user2');
      let u1 = (input1?.value || '').trim();
      let u2 = (input2?.value || '').trim();
      const err = document.getElementById('compare-error');
      const out = document.getElementById('compare-results');
      if (err) { err.classList.remove('visible'); err.textContent = ''; }
      if (!u1 || !u2) {
        if (err) { err.textContent = 'Informe os dois usuários'; err.classList.add('visible'); }
        return;
      }
      if (out) out.innerHTML = '<div class="empty-state loading">Comparando...</div>';
      try {
        u1 = await resolveCompareUsername(u1);
        u2 = await resolveCompareUsername(u2);
        if (input1) input1.value = u1;
        if (input2) input2.value = u2;
        const response = await fetch(apiUrl('/stats/compare/' + encodeURIComponent(u1) + '/' + encodeURIComponent(u2)));
        if (!response.ok) {
          let detail = 'Não encontrado';
          try {
            const body = await response.json();
            if (body && body.detail) {
              detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
            } else if (response.status === 422) {
              detail = 'Nome inválido — use o login (a-z, 0-9, _), sem espaços)';
            } else if (response.status === 404) {
              detail = 'Usuário não encontrado neste período/plataforma';
            }
          } catch (_) {
            if (response.status === 422) detail = 'Nome inválido — use o login (a-z, 0-9, _)';
            else if (response.status === 404) detail = 'Usuário não encontrado neste período/plataforma';
          }
          throw new Error(detail);
        }
        const data = await response.json();
        renderCompare(data);
      } catch (e) {
        if (out) out.innerHTML = '';
        if (err) { err.textContent = e.message || 'Erro ao comparar'; err.classList.add('visible'); }
      }
    }

    const USERNAME_RE = /^[a-zA-Z0-9_]{2,25}$/;

    async function resolveCompareUsername(raw) {
      const trimmed = (raw || '').trim();
      if (!trimmed) return trimmed;
      if (USERNAME_RE.test(trimmed)) return trimmed.toLowerCase();
      try {
        const response = await fetch(apiUrl('/stats/search', { q: trimmed }));
        if (!response.ok) return trimmed.toLowerCase().replace(/\s+/g, '');
        const results = await response.json();
        if (!Array.isArray(results) || !results.length) return trimmed;
        const lower = trimmed.toLowerCase();
        const exactLogin = results.find((u) => (u.username || '').toLowerCase() === lower);
        if (exactLogin) return exactLogin.username;
        const exactDisplay = results.filter(
          (u) => (u.display_name || '').toLowerCase() === lower
        );
        if (exactDisplay.length === 1) return exactDisplay[0].username;
        if (results.length === 1) return results[0].username;
      } catch (_) { /* fall through */ }
      return trimmed.toLowerCase();
    }

    function wireCompareAutocomplete(inputId, dropdownId) {
      const input = document.getElementById(inputId);
      const dropdown = document.getElementById(dropdownId);
      if (!input || !dropdown) return;
      let timer = null;
      let selectedIdx = -1;

      async function fetchAndRender(query) {
        if (query.length < 2) {
          dropdown.classList.remove('visible');
          dropdown.textContent = '';
          return;
        }
        const matches = await searchUsersForAutocomplete(query);
        const sections = [
          ['Online agora', matches.online, true],
          ['Todos os usuarios', matches.all, false],
        ];
        dropdown.textContent = '';
        selectedIdx = -1;
        if (!matches.online.length && !matches.all.length) {
          dropdown.classList.remove('visible');
          return;
        }
        sections.forEach(([label, users, isOnline]) => {
          if (!users.length) return;
          const section = document.createElement('div');
          section.className = 'autocomplete-section';
          const header = document.createElement('div');
          header.className = 'autocomplete-header';
          header.textContent = label;
          section.appendChild(header);
          users.forEach((user) => {
            const item = document.createElement('div');
            item.className = 'autocomplete-item';
            item.addEventListener('mousedown', (e) => {
              e.preventDefault();
              input.value = user.username;
              dropdown.classList.remove('visible');
            });
            const nameSpan = document.createElement('span');
            nameSpan.className = 'autocomplete-name';
            nameSpan.textContent = user.display_name || user.username;
            if (user.display_name && user.display_name.toLowerCase() !== user.username) {
              const login = document.createElement('span');
              login.style.opacity = '0.55';
              login.style.marginLeft = '0.35rem';
              login.style.fontSize = '0.85em';
              login.textContent = '(' + user.username + ')';
              nameSpan.appendChild(login);
            }
            appendPlatformBadge(nameSpan, user.platform);
            const badge = document.createElement('span');
            badge.className = 'autocomplete-badge ' + (isOnline ? 'online' : 'msgs');
            badge.textContent = isOnline ? 'online' : ((user.total_messages || 0) + ' msgs');
            item.appendChild(nameSpan);
            item.appendChild(badge);
            section.appendChild(item);
          });
          dropdown.appendChild(section);
        });
        dropdown.classList.add('visible');
      }

      input.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => fetchAndRender(input.value.trim()), 150);
      });
      input.addEventListener('keydown', (e) => {
        const items = dropdown.querySelectorAll('.autocomplete-item');
        if (!items.length || !dropdown.classList.contains('visible')) return;
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          selectedIdx = Math.min(selectedIdx + 1, items.length - 1);
          items.forEach((el, i) => el.classList.toggle('selected', i === selectedIdx));
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          selectedIdx = Math.max(selectedIdx - 1, 0);
          items.forEach((el, i) => el.classList.toggle('selected', i === selectedIdx));
        } else if (e.key === 'Enter' && selectedIdx >= 0) {
          e.preventDefault();
          items[selectedIdx].dispatchEvent(new Event('mousedown'));
        } else if (e.key === 'Escape') {
          dropdown.classList.remove('visible');
        }
      });
      input.addEventListener('blur', () => {
        setTimeout(() => dropdown.classList.remove('visible'), 150);
      });
    }

    wireCompareAutocomplete('compare-user1', 'compare-ac1');
    wireCompareAutocomplete('compare-user2', 'compare-ac2');

    function renderCompare(data) {
      const out = document.getElementById('compare-results');
      if (!out) return;
      out.textContent = '';
      const u1 = data.user1;
      const u2 = data.user2;
      if (!u1 || !u2) {
        out.innerHTML = '<div class="empty-state">Sem dados para comparar</div>';
        return;
      }

      function fmtNumber(value, digits = 0) {
        if (value == null || Number.isNaN(Number(value))) return '—';
        return Number(value).toLocaleString('pt-BR', {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        });
      }

      function fmtRank(rank) {
        return rank != null ? '#' + rank : '—';
      }

      function metricCell(rank, value, suffix = '') {
        const rankText = fmtRank(rank);
        const valueText = value == null ? '—' : String(value) + suffix;
        if (rankText === '—' && valueText === '—') return '—';
        if (rankText === '—') return valueText;
        if (valueText === '—') return rankText;
        return rankText + ' · ' + valueText;
      }

      function renderCompareEmotes(user) {
        const wrap = document.createElement('div');
        wrap.className = 'compare-emotes';
        const emotes = (user.top_emotes || []).slice(0, 5);
        if (!emotes.length) {
          wrap.textContent = '—';
          return wrap;
        }
        emotes.forEach((emote) => {
          const item = document.createElement('button');
          item.type = 'button';
          item.className = 'compare-emote';
          item.title = emote.emote_name;
          item.addEventListener('click', () => navigateToEmote(emote.emote_name));

          const img = document.createElement('img');
          img.src = `https://cdn.7tv.app/emote/${emote.emote_id}/2x.webp`;
          img.alt = emote.emote_name;
          img.loading = 'lazy';

          const count = document.createElement('div');
          count.className = 'emote-count';
          count.textContent = fmtNumber(emote.count);

          item.appendChild(img);
          item.appendChild(count);
          wrap.appendChild(item);
        });
        return wrap;
      }

      function betterSide(v1, v2, lowerIsBetter = false) {
        if (v1 == null || v2 == null || Number(v1) === Number(v2)) return null;
        if (lowerIsBetter) return Number(v1) < Number(v2) ? 1 : 2;
        return Number(v1) > Number(v2) ? 1 : 2;
      }

      const r1 = u1.rankings || {};
      const r2 = u2.rankings || {};
      const rows = [
        {
          label: 'Mensagens',
          hint: 'Total de mensagens no período · posição no ranking geral (Perereco Rank)',
          a: metricCell(r1.top_rank, fmtNumber(u1.total_messages)),
          b: metricCell(r2.top_rank, fmtNumber(u2.total_messages)),
          better: betterSide(u1.total_messages, u2.total_messages),
          numA: u1.total_messages,
          numB: u2.total_messages,
        },
        {
          label: 'Percentil',
          hint: 'Conversa mais que X% dos pererecos no período',
          a: u1.percentile != null ? fmtNumber(u1.percentile, 1) + '%' : '—',
          b: u2.percentile != null ? fmtNumber(u2.percentile, 1) + '%' : '—',
          better: betterSide(u1.percentile, u2.percentile),
          numA: u1.percentile,
          numB: u2.percentile,
          digits: 1,
        },
        {
          label: 'Girinos',
          hint: 'Maior crescimento de mensagens vs janela anterior igual (top 10)',
          a: metricCell(r1.rising_rank, r1.rising_count != null ? fmtNumber(r1.rising_count) : null),
          b: metricCell(r2.rising_rank, r2.rising_count != null ? fmtNumber(r2.rising_count) : null),
          better: betterSide(r1.rising_rank, r2.rising_rank, true),
          noteA: r1.rising_growth != null ? fmtNumber(r1.rising_growth, 1) + '% crescimento' : '',
          noteB: r2.rising_growth != null ? fmtNumber(r2.rising_growth, 1) + '% crescimento' : '',
          numA: r1.rising_count,
          numB: r2.rising_count,
        },
        {
          label: 'Textões',
          hint: 'Mensagens longas: média de caracteres ÷ quantidade de mensagens (top 10)',
          a: metricCell(r1.writers_rank, r1.writers_score != null ? fmtNumber(r1.writers_score, 4) : null),
          b: metricCell(r2.writers_rank, r2.writers_score != null ? fmtNumber(r2.writers_score, 4) : null),
          better: betterSide(r1.writers_rank, r2.writers_rank, true),
          noteA: r1.writers_avg_length != null ? fmtNumber(r1.writers_avg_length, 1) + ' chars médios' : '',
          noteB: r2.writers_avg_length != null ? fmtNumber(r2.writers_avg_length, 1) + ' chars médios' : '',
          numA: r1.writers_score,
          numB: r2.writers_score,
          digits: 2,
        },
        {
          label: 'Famosinhos',
          hint: 'Quem mais recebeu respostas e interações do chat',
          a: metricCell(r1.famosinhos_rank, r1.famosinhos_count != null ? fmtNumber(r1.famosinhos_count) : null),
          b: metricCell(r2.famosinhos_rank, r2.famosinhos_count != null ? fmtNumber(r2.famosinhos_count) : null),
          better: betterSide(r1.famosinhos_rank, r2.famosinhos_rank, true),
          numA: r1.famosinhos_count,
          numB: r2.famosinhos_count,
        },
        {
          label: 'Folhinha',
          hint: 'Comandos ? da Folhinha usados no período',
          a: metricCell(r1.folhinha_rank, r1.folhinha_count != null ? fmtNumber(r1.folhinha_count) : null),
          b: metricCell(r2.folhinha_rank, r2.folhinha_count != null ? fmtNumber(r2.folhinha_count) : null),
          better: betterSide(r1.folhinha_rank, r2.folhinha_rank, true),
          numA: r1.folhinha_count,
          numB: r2.folhinha_count,
        },
        {
          label: 'Maria vai com as outras',
          hint: 'Mensagens copiadas de outros (até 10 pra trás)',
          a: metricCell(
            r1.maria_vai_com_as_outras_rank,
            r1.maria_vai_com_as_outras_count != null ? fmtNumber(r1.maria_vai_com_as_outras_count) : null
          ),
          b: metricCell(
            r2.maria_vai_com_as_outras_rank,
            r2.maria_vai_com_as_outras_count != null ? fmtNumber(r2.maria_vai_com_as_outras_count) : null
          ),
          better: betterSide(r1.maria_vai_com_as_outras_rank, r2.maria_vai_com_as_outras_rank, true),
          numA: r1.maria_vai_com_as_outras_count,
          numB: r2.maria_vai_com_as_outras_count,
        },
        {
          label: 'Escritor roubado',
          hint: 'Vezes que suas mensagens foram copiadas',
          a: metricCell(
            r1.escritor_roubado_rank,
            r1.escritor_roubado_count != null ? fmtNumber(r1.escritor_roubado_count) : null
          ),
          b: metricCell(
            r2.escritor_roubado_rank,
            r2.escritor_roubado_count != null ? fmtNumber(r2.escritor_roubado_count) : null
          ),
          better: betterSide(r1.escritor_roubado_rank, r2.escritor_roubado_rank, true),
          numA: r1.escritor_roubado_count,
          numB: r2.escritor_roubado_count,
        },
        {
          label: 'Diversidade',
          hint: 'Quantidade de emotes únicos usados no período',
          a: metricCell(r1.diversidade_rank, r1.diversidade_count != null ? fmtNumber(r1.diversidade_count) : null),
          b: metricCell(r2.diversidade_rank, r2.diversidade_count != null ? fmtNumber(r2.diversidade_count) : null),
          better: betterSide(r1.diversidade_rank, r2.diversidade_rank, true),
          numA: r1.diversidade_count,
          numB: r2.diversidade_count,
        },
        {
          label: 'Roda',
          hint: 'Participações no SmokeTime das 16:20',
          a: metricCell(r1.smoke_rank, r1.smoke_count != null ? fmtNumber(r1.smoke_count) : null),
          b: metricCell(r2.smoke_rank, r2.smoke_count != null ? fmtNumber(r2.smoke_count) : null),
          better: betterSide(r1.smoke_rank, r2.smoke_rank, true),
          numA: r1.smoke_count,
          numB: r2.smoke_count,
        },
        {
          label: 'Pererecães',
          hint: 'Meta-ranking: pontos somados por posição em todas as outras boards',
          a: metricCell(r1.pererecoes_rank, r1.pererecoes_points != null ? fmtNumber(r1.pererecoes_points) + ' pts' : null),
          b: metricCell(r2.pererecoes_rank, r2.pererecoes_points != null ? fmtNumber(r2.pererecoes_points) + ' pts' : null),
          better: betterSide(r1.pererecoes_rank, r2.pererecoes_rank, true),
          numA: r1.pererecoes_points,
          numB: r2.pererecoes_points,
        },
        {
          label: 'Criadores',
          hint: 'Emotes do catálogo 7TV criados pelo usuário',
          a: metricCell(r1.creators_rank, r1.creators_count != null ? fmtNumber(r1.creators_count) : null),
          b: metricCell(r2.creators_rank, r2.creators_count != null ? fmtNumber(r2.creators_count) : null),
          better: betterSide(r1.creators_rank, r2.creators_rank, true),
          numA: r1.creators_count,
          numB: r2.creators_count,
        },
        {
          label: 'Duas Caras',
          hint: 'Quantidade de logins distintos usados (trocas de username)',
          a: metricCell(
            r1.duas_caras_rank,
            r1.duas_caras_count != null ? fmtNumber(r1.duas_caras_count) + ' nomes' : null
          ),
          b: metricCell(
            r2.duas_caras_rank,
            r2.duas_caras_count != null ? fmtNumber(r2.duas_caras_count) + ' nomes' : null
          ),
          better: (r1.duas_caras_rank != null || r2.duas_caras_rank != null)
            ? betterSide(r1.duas_caras_rank, r2.duas_caras_rank, true)
            : betterSide(r1.duas_caras_count, r2.duas_caras_count),
          numA: r1.duas_caras_count,
          numB: r2.duas_caras_count,
        },
        {
          label: 'Top emotes',
          hint: 'Emotes mais usados no período — clique para abrir o emote',
          isEmotes: true,
          a: (u1.top_emotes || []).length > 0,
          b: (u2.top_emotes || []).length > 0,
          better: null,
        },
      ];

      const viz = window.PererecosViz;
      if (viz && typeof viz.renderCompareDuel === 'function') {
        const duelMetrics = rows
          .filter((row) => !row.isEmotes && (row.numA != null || row.numB != null))
          .map((row) => ({
            label: row.label,
            a: row.numA,
            b: row.numB,
            digits: row.digits || 0,
          }));
        out.appendChild(
          viz.renderCompareDuel(duelMetrics, {
            nameA: u1.display_name || u1.username,
            nameB: u2.display_name || u2.username,
          })
        );
      }

      const table = document.createElement('table');
      table.className = 'compare-table';
      table.setAttribute('aria-label', 'Comparação detalhada');
      const thead = document.createElement('thead');
      const headRow = document.createElement('tr');
      ['', u1, u2].forEach((item) => {
        const th = document.createElement('th');
        if (item) {
          th.className = 'compare-user-head';
          th.textContent = item.display_name || item.username;
          appendPlatformBadge(th, item.platform);
          th.addEventListener('click', () => selectUser(item.username, item.platform || null));
        } else {
          th.textContent = 'Métrica';
        }
        headRow.appendChild(th);
      });
      thead.appendChild(headRow);
      table.appendChild(thead);

      const tbody = document.createElement('tbody');
      rows
        .filter((row) => row.isEmotes ? (row.a || row.b) : (row.a !== '—' || row.b !== '—'))
        .forEach((row) => {
        const tr = document.createElement('tr');
        if (row.hint) tr.title = row.hint;
        const label = document.createElement('td');
        label.textContent = row.label;
        if (row.hint) label.title = row.hint;
        tr.appendChild(label);
        [1, 2].forEach((side) => {
          const td = document.createElement('td');
          if (row.isEmotes) {
            td.appendChild(renderCompareEmotes(side === 1 ? u1 : u2));
          } else {
            const value = document.createElement('div');
            value.className = 'compare-value' + (row.better === side ? ' compare-better' : '');
            value.textContent = side === 1 ? row.a : row.b;
            td.appendChild(value);
            const noteText = side === 1 ? row.noteA : row.noteB;
            if (noteText) {
              const note = document.createElement('div');
              note.className = 'compare-muted';
              note.textContent = noteText;
              td.appendChild(note);
            }
          }
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      out.appendChild(table);
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