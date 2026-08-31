/**
 * ES module entry — loads the Ranqueada board registry (side effect on window)
 * and exposes the data-driven board loader for app.js.
 */
import './boards/registry.js';
import './boards/folhinha.js';
import './viz.js';
import { loadRanqueadaBoards } from './ranqueada.js';
import { loadFolhinhaBoards } from './folhinha_tab.js';

window.PererecosModules = {
  loadRanqueadaBoards,
  loadFolhinhaBoards,
};
