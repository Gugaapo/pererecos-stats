import { state } from './state.js';
import { apiUrl } from './api.js';
import { appendPlatformBadge } from './shared.js';
import { usernameInput, autocompleteDropdown } from './dom.js';
import { hooks } from './hooks.js';

export async function searchUsersForAutocomplete(query) {
  const lowerQuery = query.toLowerCase();

  // Filter online users that match
  const onlineMatches = [];
  state.seenOnlineUsers.forEach((data, key) => {
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

export async function fetchAutocomplete(query) {
  const matches = await searchUsersForAutocomplete(query);
  renderAutocomplete(matches.online, matches.all);
}

export function renderAutocomplete(onlineUsers, allUsers) {
  autocompleteDropdown.textContent = '';
  state.selectedAutocompleteIndex = -1;

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

export function createAutocompleteItem(user, isOnline) {
  const item = document.createElement('div');
  item.className = 'autocomplete-item';
  item.onclick = () => {
    usernameInput.value = user.username;
    hideAutocomplete();
    hooks.selectUser(user.username, user.platform);
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

export function updateAutocompleteSelection(items) {
  items.forEach((item, i) => {
    if (i === state.selectedAutocompleteIndex) {
      item.classList.add('selected');
    } else {
      item.classList.remove('selected');
    }
  });
}

export function hideAutocomplete() {
  autocompleteDropdown.classList.remove('visible');
  state.selectedAutocompleteIndex = -1;
}
