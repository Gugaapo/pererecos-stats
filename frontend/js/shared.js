import { state } from './state.js';
import { errorMessage } from './dom.js';
import { hooks } from './hooks.js';

export function todayBRTISO() {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Sao_Paulo',
    year: 'numeric', month: '2-digit', day: '2-digit',
  });
  return fmt.format(new Date());
}

export function setEntryName(container, displayName, platform) {
  container.textContent = '';
  const nameText = document.createElement('span');
  nameText.className = 'name-text';
  nameText.textContent = displayName || '';
  container.appendChild(nameText);
  appendPlatformBadge(container, platform);
}

export function fillEmoteNote(el, names) {
  if (!el) return;
  el.textContent = '';
  names.forEach((name) => {
    const url = state.sevenTVEmotes.get(name);
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

export function refreshEmoteNotes() {
  fillEmoteNote(document.getElementById('tragadores-note'), ['peepoSuscetivel', 'SmokeTime']);
  fillEmoteNote(document.getElementById('roda-note'), ['peepoSuscetivel', 'SmokeTime']);
}

export function formatBRDate(iso) {
  if (!iso) return '';
  const parts = iso.split('-');
  if (parts.length !== 3) return iso;
  return parts[2] + '/' + parts[1] + '/' + parts[0];
}

export function getPeriodLabel() {
  if (state.currentPeriod === 'day') return 'ultimo dia';
  if (state.currentPeriod === 'week') return 'ultimos 7 dias';
  if (state.currentPeriod === 'month') return 'ultimos 30 dias';
  if (state.currentPeriod === 'custom' && state.customStartDate && state.customEndDate) {
    return formatBRDate(state.customStartDate) + ' – ' + formatBRDate(state.customEndDate);
  }
  return 'desde 06/09/2026';
}

export function updatePeriodLabels() {
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
  if (state.sidebarContextMode === 'bonks') {
    map['note-top'] = 'Quem mais usou ?bonk no período (' + label + ')';
  } else if (state.sidebarContextMode === 'emotes') {
    map['note-top'] = 'Emotes mais usados no período (' + label + ')';
  } else {
    map['note-top'] = 'Quem mais mandou mensagens no periodo (' + label + ')';
  }
  Object.keys(map).forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.textContent = map[id];
  });
}

export function getUserPlatformParam() {
  if (state.currentPlatform !== 'all') return state.currentPlatform;
  return state.currentUserPlatform || 'all';
}

export function shouldShowPlatformBadges() {
  return state.currentPlatform === 'all';
}

export function createPlatformBadge(platform) {
  const badge = document.createElement('span');
  badge.className = 'platform-badge ' + platform;
  badge.textContent = platform === 'kick' ? 'Kick' : 'Twitch';
  return badge;
}

export function appendPlatformBadge(parent, platform) {
  if (shouldShowPlatformBadges() && platform) {
    parent.appendChild(createPlatformBadge(platform));
  }
}

export function animateNumber(element, target) {
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

export function formatDate(dateStr) {
  if (!dateStr) return '—';
  const [y, m, d] = dateStr.split('-');
  return d + '/' + m + '/' + y;
}

export function showError(msg) {
  if (!errorMessage) return;
  errorMessage.textContent = msg;
  errorMessage.classList.add('visible');
}

export function hideError() {
  if (!errorMessage) return;
  errorMessage.classList.remove('visible');
}

export function renderSimpleRankList(container, entries, countKey) {
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
      if (entry.username && hooks.selectUser) {
        hooks.selectUser(entry.username, entry.platform || null);
      }
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
