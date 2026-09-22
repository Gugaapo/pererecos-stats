import { state } from './state.js';
import { apiUrl } from './api.js';
import { appendPlatformBadge } from './shared.js';
import { hooks } from './hooks.js';

export function loadCompararSection(force = false) {
  if (state.compararSectionLoaded && !force) return;
  state.compararSectionLoaded = true;
}

export async function runCompare() {
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

export async function resolveCompareUsername(raw) {
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

export function wireCompareAutocomplete(inputId, dropdownId) {
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
    const matches = await hooks.searchUsersForAutocomplete(query);
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

export function renderCompare(data) {
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
      item.addEventListener('click', () => hooks.navigateToEmote(emote.emote_name));

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
      th.addEventListener('click', () => hooks.selectUser(item.username, item.platform || null));
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
