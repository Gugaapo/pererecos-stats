import { state, API_BASE } from './state.js';
import { apiUrl } from './api.js';
import { setEntryName, refreshEmoteNotes, updatePeriodLabels } from './shared.js';
import { leaderboard, activeChattersList, onlineCountEl, chatActivityChart, totalTodayEl, peakInfoEl, overallActivityChart, overallTotalEl, overallPeakEl, averageActivityChart, averageDaysEl, averagePeakEl, uniqueChattersChart, uniqueTotalEl, uniquePeakEl } from './dom.js';
import { hooks } from './hooks.js';

export function loadCoreStats() {
  fetchLeaderboard();
  fetchActiveChatters();
}

export function loadChartStats() {
  fetchChatActivity();
  fetchUniqueChatters();
  fetchOverallActivity();
}

export function loadInitialData() {
  updatePeriodLabels();
  fetch7TVEmotes();
  loadCoreStats();
  setTimeout(loadChartStats, 500);
}
export async function fetchLeaderboard() {
  if (!leaderboard) return;
  if (state.sidebarContextMode !== 'messages') return;
  try {
    const response = await fetch(apiUrl('/stats/leaderboard', { limit: 10 }));
    if (!response.ok) throw new Error('API Error');

    const data = await response.json();
    if (state.sidebarContextMode !== 'messages') return;
    if (data.total_users != null) state.totalLeaderboardUsers = data.total_users;
    renderLeaderboard(data.leaderboard);
  } catch (error) {
    console.error('Error loading leaderboard:', error);
  }
}
export async function fetchActiveChatters() {
  try {
    const response = await fetch(apiUrl('/stats/active-chatters'));
    if (!response.ok) throw new Error('API Error');

    const data = await response.json();
    state.allActiveChatters = data.chatters;
    state.totalLeaderboardUsers = data.total_users;

    // Update online count
    onlineCountEl.textContent = data.count;

    // Track users seen online for autocomplete
    state.allActiveChatters.forEach(chatter => {
      state.seenOnlineUsers.set(`${chatter.platform || 'twitch'}:${chatter.username}`, {
        display_name: chatter.display_name,
        platform: chatter.platform || 'twitch',
        last_seen: Date.now()
      });
    });

    renderActiveChatters(state.allActiveChatters);
  } catch (error) {
    console.error('Error loading active chatters:', error);
    activeChattersList.textContent = '';
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'Erro ao carregar';
    activeChattersList.appendChild(empty);
  }
}

export async function fetchChatActivity() {
  try {
    const response = await fetch(apiUrl('/stats/chat-activity'));
    if (!response.ok) throw new Error('API Error');

    const data = await response.json();
    renderChatActivity(data);
  } catch (error) {
    console.error('Error loading chat activity:', error);
  }
}

export function renderChatActivity(data) {
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

export async function fetchUniqueChatters() {
  try {
    const response = await fetch(apiUrl('/stats/unique-chatters'));
    if (!response.ok) throw new Error('API Error');

    const data = await response.json();
    renderUniqueChatters(data);
  } catch (error) {
    console.error('Error loading unique chatters:', error);
  }
}

export function renderUniqueChatters(data) {
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

export async function fetchOverallActivity() {
  try {
    const response = await fetch(apiUrl('/stats/overall-activity'));
    if (!response.ok) throw new Error('API Error');

    const data = await response.json();
    renderOverallActivity(data);
  } catch (error) {
    console.error('Error loading overall activity:', error);
  }
}

export async function fetch7TVEmotes() {
  try {
    // Fetch global 7TV emotes
    const globalRes = await fetch('https://7tv.io/v3/emote-sets/global');
    if (globalRes.ok) {
      const globalData = await globalRes.json();
      if (globalData.emotes) {
        globalData.emotes.forEach(emote => {
          state.sevenTVEmotes.set(emote.name, `https://cdn.7tv.app/emote/${emote.id}/1x.webp`);
        });
      }
    }

    // Fetch channel emotes for omeiaum (specific emote set)
    const channelRes = await fetch('https://7tv.io/v3/emote-sets/01HR3ABJ800007QJQMTQH1J05C');
    if (channelRes.ok) {
      const channelData = await channelRes.json();
      if (channelData.emotes) {
        channelData.emotes.forEach(emote => {
          state.sevenTVEmotes.set(emote.name, `https://cdn.7tv.app/emote/${emote.id}/1x.webp`);
        });
      }
    }

    console.log('Loaded ' + state.sevenTVEmotes.size + ' 7TV emotes');
    refreshEmoteNotes();
    hooks.renderExportNerdEmote();
  } catch (error) {
    console.error('Error loading 7TV emotes:', error);
  }
}

export function renderOverallActivity(data) {
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
export function filterActiveChatters(query) {
  const filtered = query
    ? state.allActiveChatters.filter(c =>
      c.username.toLowerCase().includes(query.toLowerCase()) ||
      c.display_name.toLowerCase().includes(query.toLowerCase())
    )
    : state.allActiveChatters;
  renderActiveChatters(filtered);
}

export function renderLeaderboard(entries) {
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
    const isSelected = state.currentUsername
      && entry.username === state.currentUsername.toLowerCase()
      && (state.currentUserPlatform === entryPlatform || state.currentPlatform === entryPlatform);
    const div = document.createElement('div');
    div.dataset.username = entry.username;
    div.dataset.platform = entryPlatform;
    div.className = 'leaderboard-entry' + (isSelected ? ' selected' : '');
    div.onclick = () => hooks.selectUser(entry.username, entryPlatform);

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
export function renderActiveChatters(chatters) {
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
    div.onclick = () => hooks.selectUser(chatter.username, chatter.platform);

    const leftGroup = document.createElement('div');
    leftGroup.className = 'active-chatter-left';

    const rankSpan = document.createElement('span');
    rankSpan.className = 'active-chatter-rank';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'active-chatter-name';
    setEntryName(nameSpan, chatter.display_name, chatter.platform);

    let colorClass = null;
    if (chatter.rank && state.totalLeaderboardUsers > 0) {
      rankSpan.textContent = '#' + chatter.rank;
      const percentile = (chatter.rank / state.totalLeaderboardUsers) * 100;
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
