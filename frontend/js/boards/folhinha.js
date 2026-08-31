/**
 * Folhinha tab board registry.
 * Each board maps to GET /stats/folhinha/boards/{id}
 */

const DETAIL_LIMIT = 50;
const PAGE_SIZE = 20;

export const FOLHINHA_BOARDS = [
  {
    id: 'bonkadores',
    slug: 'bonkadores',
    title: 'Maiores Bonkadores',
    description:
      'Quem mais mandou ?bonk. Cada tapa conta — independente da % que o Folhinha sorteou.',
    listId: 'fh-bonkadores-list',
    endpoint: '/stats/folhinha/boards/bonkadores',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-count',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'sacos-de-pancada',
    slug: 'sacos-de-pancada',
    title: 'Maiores Sacos de Pancada',
    description:
      'Quem mais levou ?bonk. Se o chat vive te usando de saco de pancada, você aparece aqui.',
    listId: 'fh-sacos-list',
    endpoint: '/stats/folhinha/boards/sacos-de-pancada',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-count',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'mais-fortes',
    slug: 'mais-fortes',
    title: 'Mais Fortes',
    description:
      'Maior média de % nos ?bonk (mín. 3 bonks com porcentagem registrada). Força bruta segundo o Folhinha.',
    listId: 'fh-fortes-list',
    endpoint: '/stats/folhinha/boards/mais-fortes',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-pct',
    countKey: 'avg_percentage',
    responseKey: 'leaderboard',
  },
  {
    id: 'mais-fracos',
    slug: 'mais-fracos',
    title: 'Mais Fracos',
    description:
      'Menor média de % nos ?bonk (mín. 3 bonks com porcentagem). O Folhinha te deu butterhands.',
    listId: 'fh-fracos-list',
    endpoint: '/stats/folhinha/boards/mais-fracos',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-pct',
    countKey: 'avg_percentage',
    responseKey: 'leaderboard',
  },
  {
    id: 'mais-carinhos',
    slug: 'mais-carinhos',
    title: 'Mais Carinhos',
    description: 'Quem mais usou ?abraco / ?abraço. Distribuindo amor no chat.',
    listId: 'fh-carinhos-list',
    endpoint: '/stats/folhinha/boards/mais-carinhos',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-count',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'mais-fofos',
    slug: 'mais-fofos',
    title: 'Mais Fofos',
    description: 'Quem mais foi alvo de ?abraco. O chat te acha fofo (ou tá zoando).',
    listId: 'fh-fofos-list',
    endpoint: '/stats/folhinha/boards/mais-fofos',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-count',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'desvivedores',
    slug: 'desvivedores',
    title: 'Desvivedores',
    description:
      'Quem mais tomou timeout da roleta (?rr / ?roleta → BANG!). Unalived by Folhinha.',
    listId: 'fh-desvivedores-list',
    endpoint: '/stats/folhinha/boards/desvivedores',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-count',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'sobreviventes',
    slug: 'sobreviventes',
    title: 'Sobreviventes',
    description:
      'Quem mais ouviu “Click! Não foi dessa vez Saved” depois de ?rr / ?roleta.',
    listId: 'fh-sobreviventes-list',
    endpoint: '/stats/folhinha/boards/sobreviventes',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-count',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'cookie-cd',
    slug: 'cookie-cd',
    title: 'Clicadores de Cookies',
    description:
      'Quem mais usou ?cd (cookie diário). Cada tentativa conta, mesmo se já tinha resgatado.',
    listId: 'fh-cookie-cd-list',
    endpoint: '/stats/folhinha/boards/cookie-cd',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-count',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'mais-cookies',
    slug: 'mais-cookies',
    title: 'Mais Cookies',
    description:
      'Quem tem mais cookies segundo a última balança que o Folhinha anunciou (?cd, ?cookie slot ou status).',
    listId: 'fh-mais-cookies-list',
    endpoint: '/stats/folhinha/boards/mais-cookies',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-count',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'slot-ganhos',
    slug: 'slot-ganhos',
    title: 'Apostadores',
    description:
      'Soma de cookies ganhos no ?cookie slot (delta positivo nas respostas do Folhinha).',
    listId: 'fh-slot-ganhos-list',
    endpoint: '/stats/folhinha/boards/slot-ganhos',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-count',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'slot-perdas',
    slug: 'slot-perdas',
    title: 'Devedores',
    description:
      'Soma de cookies perdidos no ?cookie slot (delta negativo). Azar no tigrinho do Folhinha.',
    listId: 'fh-slot-perdas-list',
    endpoint: '/stats/folhinha/boards/slot-perdas',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'folhinha-count',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
];

export function getFolhinhaBoard(idOrSlug) {
  const key = String(idOrSlug || '').toLowerCase();
  return FOLHINHA_BOARDS.find((b) => b.id === key || b.slug === key) || null;
}

if (typeof window !== 'undefined') {
  window.getFolhinhaBoard = getFolhinhaBoard;
  window.FOLHINHA_BOARDS = FOLHINHA_BOARDS;
}
