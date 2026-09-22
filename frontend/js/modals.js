import { state, API_BASE, COLLECTION_START } from './state.js';
import { apiUrl } from './api.js';
import { todayBRTISO, appendPlatformBadge } from './shared.js';
import { exportBtn, exportModal, exportModalClose, exportStartInput, exportEndInput, exportDownloadBtn, exportNerdEmote, feedbackBtn, feedbackModal, modalClose, feedbackForm, feedbackType, feedbackMessage, feedbackSubmit, feedbackResult, charCount, ribbitsModal, ribbitsBody, ribbitsProfileBtn, ribbitsClose, ribbitsAgain } from './dom.js';
import { hooks } from './hooks.js';


export function syncExportDateInputs() {
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

export function renderExportNerdEmote() {
  if (!exportNerdEmote) return;
  const cached = state.sevenTVEmotes.get('NERD');
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
      state.sevenTVEmotes.set('NERD', url);
      exportNerdEmote.src = url;
      exportNerdEmote.style.display = '';
    })
    .catch(() => {});
}

export function openExportModal() {
  if (!exportModal) return;
  syncExportDateInputs();
  renderExportNerdEmote();
  exportModal.classList.add('visible');
}

export function closeExportModal() {
  if (exportModal) exportModal.classList.remove('visible');
}

export function startMessageExport() {
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
    platform: state.currentPlatform,
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

if (feedbackBtn && feedbackModal) {
  feedbackBtn.addEventListener('click', () => {
    feedbackModal.classList.add('visible');
    if (feedbackResult) feedbackResult.style.display = 'none';
    if (feedbackForm) feedbackForm.reset();
    if (charCount) charCount.textContent = '0';
  });
}

if (modalClose && feedbackModal) {
  modalClose.addEventListener('click', () => {
    feedbackModal.classList.remove('visible');
  });
}

if (feedbackModal) {
  feedbackModal.addEventListener('click', (e) => {
    if (e.target === feedbackModal) {
      feedbackModal.classList.remove('visible');
    }
  });
}

if (feedbackMessage && charCount) {
  feedbackMessage.addEventListener('input', () => {
    charCount.textContent = feedbackMessage.value.length;
  });
}

if (feedbackForm) feedbackForm.addEventListener('submit', async (e) => {
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

let ribbitsFocusUser = null;
export async function openRibbits() {
  if (!ribbitsModal) return;
  ribbitsModal.classList.add('visible');
  await loadRibbit();
}
export async function loadRibbit() {
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
      hooks.renderMessageWithEmotes(text, msg.message || '');
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
if (ribbitsClose) ribbitsClose.addEventListener('click', () => ribbitsModal.classList.remove('visible'));
if (ribbitsModal) {
  ribbitsModal.addEventListener('click', (e) => {
    if (e.target === ribbitsModal) ribbitsModal.classList.remove('visible');
  });
}
if (ribbitsAgain) ribbitsAgain.addEventListener('click', loadRibbit);
if (ribbitsProfileBtn) {
  ribbitsProfileBtn.addEventListener('click', () => {
    if (!ribbitsFocusUser) return;
    ribbitsModal.classList.remove('visible');
    hooks.selectUser(ribbitsFocusUser.username, ribbitsFocusUser.platform);
  });
}
