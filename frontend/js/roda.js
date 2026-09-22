import { state } from './state.js';
import { apiUrl } from './api.js';
import { appendPlatformBadge, formatDate } from './shared.js';
import { leaderboard } from './dom.js';
import { hooks } from './hooks.js';

export function loadRodaSection(force = false) {
  if (state.smokeTimeLoaded && !force) return;
  state.smokeTimeLoaded = true;
  fetchSmokeTime();
}

export async function fetchSmokeTime() {
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

export function renderSmokeTime(data) {
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

export function renderTragadoresLeaderboard(leaderboard) {
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
    name.onclick = () => hooks.selectUser(entry.username, entry.platform);
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

export function renderTragadoresHighlights(data) {
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

export function renderTragadores5DayChart(last5Days) {
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

export function renderTragadoresLongestStreaks(streaks) {
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
    name.onclick = () => hooks.selectUser(entry.username, entry.platform);
    appendPlatformBadge(name, entry.platform);

    const days = document.createElement('span');
    days.className = 'tragador-streak-days';
    days.textContent = entry.streak + ' dias 🔥';

    row.appendChild(name);
    row.appendChild(days);
    container.appendChild(row);
  });
}

export function renderTragadoresToday(today) {
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
export function renderFirstToday(first) {
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
  name.addEventListener('click', () => hooks.selectUser(first.username, first.platform || null));
  el.appendChild(name);
}

export function renderRodaCalendar(data) {
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
