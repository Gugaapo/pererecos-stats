/**
 * Ranqueada section loader — data-driven via boards/registry.js
 * Wired into classic app.js through window.loadRanqueadaBoards.
 */
import { RANQUEADA_BOARDS } from './boards/registry.js';

/**
 * @param {object} ctx
 * @param {function} ctx.apiUrl
 * @param {function} ctx.setLeaderboardError
 * @param {function} ctx.renderBoard — (board, el, entries, rawData) => void
 */
export async function loadRanqueadaBoards(ctx) {
  const fetchCache = new Map();

  const fetchBoardData = (board) => {
    const key = board.endpoint + JSON.stringify(board.params || {});
    if (!fetchCache.has(key)) {
      fetchCache.set(
        key,
        fetch(ctx.apiUrl(board.endpoint, board.params || {})).then((r) => {
          if (!r.ok) throw new Error('API ' + board.endpoint);
          return r.json();
        })
      );
    }
    return fetchCache.get(key);
  };

  await Promise.all(
    RANQUEADA_BOARDS.map(async (board) => {
      const el = document.getElementById(board.listId);
      if (!el) return;
      try {
        const data = await fetchBoardData(board);
        let entries;
        if (typeof board.mapEntries === 'function') {
          entries = board.mapEntries(data);
        } else if (board.render === 'weather-rising') {
          entries = data.rising || [];
        } else if (board.render === 'weather-falling') {
          entries = data.falling || [];
        } else if (board.responseKey) {
          entries = data[board.responseKey];
        } else {
          entries = data;
        }
        ctx.renderBoard(board, el, entries, data);
      } catch (err) {
        console.error('Board', board.id, err);
        ctx.setLeaderboardError(el);
      }
    })
  );
}
