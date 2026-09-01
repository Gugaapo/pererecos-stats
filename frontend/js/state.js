/** Shared mutable app state for ES modules. Classic app.js still owns the live UI loop. */
export const state = {
  currentUsername: '',
  currentPeriod: 'all',
  currentPlatform: 'all',
  currentUserPlatform: null,
  currentSection: 'home',
  currentEmoteName: '',
  ranqueadaSectionLoaded: false,
  customStartDate: null,
  customEndDate: null,
};

export const API_BASE = '/pererecos-stats-subathon/api/v1';
export const BASE_PATH = '/pererecos-stats-subathon';
