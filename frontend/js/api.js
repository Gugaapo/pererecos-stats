import { state, API_BASE } from './state.js';

export function periodQueryParams(extra = {}) {
  const params = { ...extra };
  const period =
    state.currentPeriod && state.currentPeriod !== 'undefined' && state.currentPeriod !== 'null'
      ? state.currentPeriod
      : 'all';
  params.period = period;
  if (period === 'custom' && state.customStartDate && state.customEndDate) {
    params.start_date = state.customStartDate;
    params.end_date = state.customEndDate;
  } else {
    delete params.start_date;
    delete params.end_date;
  }
  return params;
}

export function apiUrl(path, params = {}) {
  const merged = { platform: state.currentPlatform || 'all', ...periodQueryParams(params) };
  const search = new URLSearchParams();
  Object.entries(merged).forEach(([key, value]) => {
    if (value == null || value === '' || value === 'undefined' || value === 'null') return;
    search.set(key, String(value));
  });
  const qs = search.toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ''}`;
}

export function setLeaderboardError(el, message = 'Erro ao carregar') {
  if (!el) return;
  el.textContent = '';
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.textContent = message;
  el.appendChild(empty);
}
