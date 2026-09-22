/** Shared mutable app state — single source of truth for the SPA. */
export const state = {
  currentUsername: '',
  currentPeriod: 'all',
  currentPlatform: 'all',
  currentUserPlatform: null,
  currentTab: 'top',
  currentSection: 'home',
  currentEmoteName: '',
  currentRanqueadaBoardId: '',
  currentBoardSource: 'ranqueada',
  customStartDate: null,
  customEndDate: null,
  refreshInterval: null,
  searchTimeout: null,
  selectedAutocompleteIndex: -1,
  userStatsAbort: null,
  emotesSectionLoaded: false,
  emotesCondensadasLoaded: false,
  smokeTimeLoaded: false,
  timerSectionLoaded: false,
  chatSyncLoaded: false,
  ranqueadaSectionLoaded: false,
  folhinhaSectionLoaded: false,
  compararSectionLoaded: false,
  sidebarContextMode: 'messages',
  emoteRankingCache: null,
  emoteRankingFilter: '',
  emoteRankingVisible: 50,
  emoteSearchTimeout: null,
  selectedEmoteAutocompleteIndex: -1,
  ranqueadaBoardEntries: [],
  ranqueadaBoardPage: 1,
  ranqueadaBoardMeta: null,
  allActiveChatters: [],
  totalLeaderboardUsers: 0,
  seenOnlineUsers: new Map(),
  sevenTVEmotes: new Map(),
  timerSectionRefreshTimer: null,
  emotePositionUsersCache: null,
};

export const API_BASE = '/pererecos-stats-subathon/api/v1';
export const BASE_PATH = '/pererecos-stats-subathon';
export const DEFAULT_TITLE = 'Pererecos Stats Subathon';
export const RESERVED_SECTIONS = new Set(['emotes', 'roda', 'ranqueada', 'comparar', 'folhinha', 'timer']);
export const SMOKE_TIME_EMOTE_ID = '01FEHRN6PR000AEZ0QNPT4F4MF';
export const MEIA_TIMER_EMOTE_ID = '01J0FKBS40000BMH9V93EWPYMQ';
export const EMOTE_RANKING_PAGE = 50;
export const COLLECTION_START = '2026-09-06';
