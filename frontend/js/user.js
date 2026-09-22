import { state } from './state.js';
import { apiUrl } from './api.js';
import { getUserPlatformParam, appendPlatformBadge, animateNumber, formatDate, showError } from './shared.js';
import { statsSection, userStatusEl, displayNameEl, totalMessagesEl, percentileText, lastMessageText, peakHoursText, favoriteHourText, rankingsGrid, hourlyChart, messagesList, rivalInfo, repliesList, userTopEmotes, usernameHistoryBtn, usernameHistoryPopup, usernameHistoryList } from './dom.js';
import { hooks } from './hooks.js';

export function showSectionLoading(el, text) {
  if (!el) return;
  el.innerHTML = '<div class="empty-state loading">' + (text || 'Carregando...') + '</div>';
}

export function showUserSectionPlaceholders() {
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

export async function fetchUserStats(silent = false) {
  if (!state.currentUsername) return;

  if (state.userStatsAbort) state.userStatsAbort.abort();
  state.userStatsAbort = new AbortController();
  const signal = state.userStatsAbort.signal;
  const requestedUser = state.currentUsername;

  if (!silent) {
    showUserSectionPlaceholders();
  }

  try {
    const coreResponse = await fetch(
      apiUrl(`/stats/user/${encodeURIComponent(state.currentUsername)}/core`, {
        period: state.currentPeriod,
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
    if (signal.aborted || state.currentUsername !== requestedUser) return;

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

export function renderUserCore(data, silent = false) {
  displayNameEl.textContent = '';
  displayNameEl.appendChild(document.createTextNode(data.display_name));
  state.currentUserPlatform = data.platform || state.currentUserPlatform;
  appendPlatformBadge(displayNameEl, data.platform);
  document.title = data.display_name + ' - Pererecos Stats';

  const isOnline = state.allActiveChatters.some(
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

export function renderPeakHours(peakHours) {
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

export function renderFavoriteHour(favoriteHour) {
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

export async function fetchAndRenderActivity(signal, requestedUser) {
  try {
    const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/activity`, {
      period: state.currentPeriod,
      platform: getUserPlatformParam(),
    }), { signal });
    if (!res.ok || state.currentUsername !== requestedUser) return;
    const data = await res.json();
    renderHourlyChart(data.hourly_activity || []);
    renderPeakHours(data.peak_hours);
    renderFavoriteHour(data.favorite_hour);
  } catch (e) {
    if (e.name !== 'AbortError') console.error('activity:', e);
  }
}

export async function fetchAndRenderRankings(signal, requestedUser) {
  try {
    const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/rankings`, {
      period: state.currentPeriod,
      platform: getUserPlatformParam(),
    }), { signal });
    if (!res.ok || state.currentUsername !== requestedUser) return;
    const data = await res.json();
    renderRankings(data.rankings);
  } catch (e) {
    if (e.name !== 'AbortError') console.error('rankings:', e);
  }
}

export async function fetchAndRenderSocial(signal, requestedUser) {
  try {
    const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/social`, {
      period: state.currentPeriod,
      platform: getUserPlatformParam(),
    }), { signal });
    if (!res.ok || state.currentUsername !== requestedUser) return;
    const data = await res.json();
    renderRival(data.rival);
    renderTopReplies(data.top_replies || []);
  } catch (e) {
    if (e.name !== 'AbortError') console.error('social:', e);
  }
}

export async function fetchAndRenderEmotes(signal, requestedUser) {
  try {
    const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/emotes`, {
      period: state.currentPeriod,
      platform: getUserPlatformParam(),
    }), { signal });
    if (!res.ok || state.currentUsername !== requestedUser) return;
    const data = await res.json();
    hooks.renderTopEmotes(userTopEmotes, data.top_emotes || []);
    const container = document.getElementById('user-emote-positions');
    if (data.emote_position) {
      hooks.renderEmotePositionBar(container, data.emote_position.positions, data.emote_position.label);
    } else if (container) {
      container.innerHTML = '<div class="empty-state">Nenhum dado de emotes</div>';
    }
  } catch (e) {
    if (e.name !== 'AbortError') console.error('emotes:', e);
  }
}

export async function fetchAndRenderRecentMessages(signal, requestedUser) {
  try {
    const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/recent`, {
      platform: getUserPlatformParam(),
    }), { signal });
    if (!res.ok || state.currentUsername !== requestedUser) return;
    const data = await res.json();
    renderRecentMessages(data.recent_messages || []);
  } catch (e) {
    if (e.name !== 'AbortError') console.error('recent:', e);
  }
}

export async function fetchAndRenderSmokeStats(signal, requestedUser) {
  try {
    const res = await fetch(apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/smoke`, {
      platform: getUserPlatformParam(),
    }), { signal });
    if (!res.ok || state.currentUsername !== requestedUser) return;
    const data = await res.json();
    renderUserSmokeStats(data.smoke_stats);
  } catch (e) {
    if (e.name !== 'AbortError') console.error('smoke:', e);
  }
}

export function renderRival(rival) {
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
  nameSpan.onclick = () => hooks.selectUser(rival.username, rival.platform);

  const scoreSpan = document.createElement('span');
  scoreSpan.className = 'rival-score';
  scoreSpan.textContent = rival.similarity_score + '% similar';

  rivalInfo.appendChild(nameSpan);
  rivalInfo.appendChild(scoreSpan);
}

export function renderTopReplies(replies) {
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
    nameSpan.onclick = () => hooks.selectUser(r.username, r.platform);

    const countSpan = document.createElement('span');
    countSpan.className = 'reply-count';
    countSpan.textContent = r.reply_count + 'x';

    item.appendChild(nameSpan);
    item.appendChild(countSpan);
    repliesList.appendChild(item);
  });
}

export function renderUserSmokeStats(smoke) {
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

export function renderFolhinhaPartnerList(el, partners, opts = {}) {
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
    nameSpan.onclick = () => hooks.selectUser(p.username, p.platform);

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

export function renderUserFolhinhaStats(fh) {
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

export async function fetchAndRenderFolhinhaStats(signal, requestedUser) {
  try {
    const res = await fetch(
      apiUrl(`/stats/user/${encodeURIComponent(requestedUser)}/folhinha`, {
        period: state.currentPeriod,
        platform: getUserPlatformParam(),
      }),
      { signal }
    );
    if (!res.ok || signal.aborted || state.currentUsername !== requestedUser) return;
    const data = await res.json();
    if (signal.aborted || state.currentUsername !== requestedUser) return;
    renderUserFolhinhaStats(data.folhinha_stats);
  } catch (e) {
    if (e.name !== 'AbortError') console.error('folhinha:', e);
  }
}

export function renderRankings(rankings) {
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

export function renderHourlyChart(hourlyData) {
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

export function renderMessageWithEmotes(container, text) {
  // Split by whitespace but keep the delimiters
  const parts = text.split(/(\s+)/);
  parts.forEach(part => {
    if (part.match(/^\s+$/)) {
      // Whitespace - preserve it
      container.appendChild(document.createTextNode(part));
    } else {
      const emoteUrl = state.sevenTVEmotes.get(part);
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

export function renderRecentMessages(messages) {
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
export async function fetchUsernameHistory(username, platform = null) {
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
