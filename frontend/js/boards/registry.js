/**
 * Ranqueada board registry — add a new leaderboard by appending here
 * and adding a matching HTML card with listId.
 *
 * Shape:
 *   id, slug, title, description, listId, endpoint, params?,
 *   detailLimit?, pageSize?, paginateDetail?,
 *   responseKey?: string | null  — JSON key for the list (default: auto)
 *   render: 'simple' | 'duas-caras' | 'pererecoes' | 'rising' | 'hours' | 'writers' | 'commands' | 'weather-rising' | 'weather-falling' | 'custom'
 *   countKey?: string            — for render:'simple'
 *   mapEntries?: (data, { detail }) => array — optional transform
 *   skipSidebarLeaderboard?: bool — if true, not loaded here (sidebar only)
 */

const DETAIL_LIMIT = 50;
const PAGE_SIZE = 20;

export const RANQUEADA_BOARDS = [
  {
    id: 'pererecoes',
    slug: 'pererecoes',
    title: 'Pererecães',
    description:
      'O ranking dos rankings. A gente pega o top 10 de vários leaderboards e dá pontos pela posição: 1º = 100, 2º = 80, e vai descendo até o 10º = 5. Quem acumula mais pontos vira Pererecão. Botar o mouse encima dos pontos mostra de onde veio cada pontinho.',
    listId: 'pererecoes-list',
    endpoint: '/stats/pererecoes',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'pererecoes',
    responseKey: 'leaderboard',
  },
  {
    id: 'rising',
    slug: 'rising',
    title: 'Top Girinos',
    description:
      'Quem tá crescendo de verdade. Compara o período que você escolheu com a janela anterior do mesmo tamanho (tipo 7 dias vs 7 dias de antes). Se o chat do cara explodiu de uma janela pra outra, ele sobe aqui. Se botar desde o começo, usa as últimas 2 semanas como referência.',
    listId: 'rising-list',
    endpoint: '/stats/rising-stars',
    params: { limit: 10 },
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'rising',
    responseKey: 'entries',
  },
  {
    id: 'writers',
    slug: 'writers',
    title: 'Top Textões',
    description:
      'Os poetas do chat. Ranking pela média de caracteres por mensagem, só entra quem mandou pelo menos 20 msgs no período, senão um textão solitário virava campeão. Os pontos são uma mistura do tamanho médio com o volume pra não premiar só quem escreve pouco mas longo.',
    listId: 'writers-list',
    endpoint: '/stats/top-writers',
    params: { limit: 10 },
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'writers',
    responseKey: 'entries',
  },
  {
    id: 'famosinhos',
    slug: 'famosinhos',
    title: 'Famosinhos',
    description:
      'Quem mais recebe resposta. Toda vez que alguém responde você no chat, conta um ponto. Não é quem fala mais, é quem os outros ficam respondendo.',
    listId: 'famosinhos-list',
    endpoint: '/stats/famosinhos',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'simple',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'folhinha',
    slug: 'folhinha',
    title: 'Abusadores do Folhinha',
    description:
      'Quem mais manda comando começando com ? pro Folhinha. Cada ?<coisa> conta (sim, dá pra abusar, mas eu n quero lidar com isso). Se você vive perguntando pro bot, seu nome vai aparecer aqui.',
    listId: 'folhinha-list',
    endpoint: '/stats/folhinha',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'simple',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'folhinha-commands',
    slug: 'folhinha-commands',
    title: 'Comandos do Folhinha',
    description:
      'Não é quem manda, é o quê. Ranking dos tokens ?<coisa> mais digitados no período.',
    listId: 'folhinha-commands-list',
    endpoint: '/stats/folhinha/commands',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'commands',
    responseKey: 'commands',
  },
  {
    id: 'emotes-rising',
    slug: 'emotes-rising',
    title: 'Emotes em Alta',
    description:
      'Emotes que bombaram agora vs a janela anterior do mesmo tamanho. Se um emote novo (ou reviveu um velho) estiver sendo usado, ele sobe aqui. Clique no emote pra ver o detalhe.',
    listId: 'emote-weather-rising',
    endpoint: '/stats/emotes/weather',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'weather-rising',
    responseKey: null,
  },
  {
    id: 'emotes-falling',
    slug: 'emotes-falling',
    title: 'Emotes em Baixa',
    description:
      'Emotes que caíram de uso comparado à janela anterior. Às vezes o hype passa, às vezes o chat só cansou. Mesma lógica da Alta, só que pra baixo.',
    listId: 'emote-weather-falling',
    endpoint: '/stats/emotes/weather',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'weather-falling',
    responseKey: null,
  },
  {
    id: 'diversidade',
    slug: 'diversidade',
    title: 'Diversidade',
    description:
      'Quem usa mais emotes diferentes no período. Conta quantos emotes únicos você enfiou no chat.',
    listId: 'ranqueada-diversidade-list',
    endpoint: '/stats/emotes/diversidade',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'simple',
    countKey: 'unique_emotes',
    responseKey: 'leaderboard',
  },
  {
    id: 'creators',
    slug: 'creators',
    title: 'Criadores',
    description:
      'Pererecos com mais emotes criados e aceitos no emoteset do canal. Tem que ter falado no chat também também (no período, se você filtrou). Ou seja: criou, entrou no emoteset, e ainda aparece no chat.',
    listId: 'ranqueada-creators-list',
    endpoint: '/stats/emotes/creators',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'simple',
    countKey: 'emote_count',
    responseKey: 'creators',
  },
  {
    id: 'duas-caras',
    slug: 'duas-caras',
    title: 'Duas Caras',
    description:
      'Quem mais trocou de login. Conta quantos usernames distintos a gente já viu no mesmo user_id, sem filtro de período. Mínimo 2 nomes pra entrar.',
    listId: 'duas-caras-list',
    endpoint: '/stats/duas-caras',
    params: { limit: 10 },
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'duas-caras',
    responseKey: 'leaderboard',
  },
  {
    id: 'maria-vai-com-as-outras',
    slug: 'maria-vai-com-as-outras',
    title: 'Maria vai com as outras',
    description:
      'Quem mais copia as mensagens de outros pererecos no chat. Aqui contamos até 10 mensagens atrás. Sim, contamos emotes quando todo mundo manda o mesmo, é só ser o mais rápido',
    listId: 'maria-list',
    endpoint: '/stats/maria-vai-com-as-outras',
    params: { limit: 10 },
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'simple',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'escritor-roubado',
    slug: 'escritor-roubado',
    title: 'Escritor roubado',
    description:
      'Quem mais é plagiado no chat. Cada vez que alguém copia sua mensagem (olhando até 10 mensagens de outras pessoas pra trás), você ganha um ponto. O original (ou o último que falou a mesma coisa) é o escritor roubado.',
    listId: 'escritor-roubado-list',
    endpoint: '/stats/escritor-roubado',
    params: { limit: 10 },
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'simple',
    countKey: 'count',
    responseKey: 'leaderboard',
  },
  {
    id: 'tragadores',
    slug: 'tragadores',
    title: 'Maiores Tragadores',
    description:
      'A Roda das 16:20. Quem mandou o emote SmokeTime nesse minuto mágico entra na sessão do dia. Ranking por quantas rodas você pegou no período.',
    listId: 'ranqueada-tragadores-list',
    endpoint: '/stats/smoke-time',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    render: 'simple',
    countKey: 'count',
    responseKey: 'leaderboard',
    mapEntries: (data, opts = {}) => {
      const limit = opts.detail ? (opts.detailLimit || DETAIL_LIMIT) : 10;
      return (data.leaderboard || []).slice(0, limit).map((e, i) => ({
        rank: i + 1,
        username: e.username,
        display_name: e.display_name,
        platform: e.platform,
        count: e.count,
      }));
    },
  },
  {
    id: 'hour-leaders',
    slug: 'hour-leaders',
    title: 'Top Horários',
    description:
      'Quem domina cada hora do dia (0h–23h, Brasília) no período. Pra cada horário, o perereco com mais mensagens naquela faixa.',
    listId: 'hours-list',
    endpoint: '/stats/hour-leaders',
    detailLimit: DETAIL_LIMIT,
    pageSize: PAGE_SIZE,
    paginateDetail: false,
    render: 'hours',
    responseKey: 'entries',
  },
];

export function getRanqueadaBoard(idOrSlug) {
  const key = String(idOrSlug || '').toLowerCase();
  return RANQUEADA_BOARDS.find((b) => b.id === key || b.slug === key) || null;
}

/** Expose for classic app.js during the modular migration. */
if (typeof window !== 'undefined') {
  window.RANQUEADA_BOARDS = RANQUEADA_BOARDS;
  window.getRanqueadaBoard = getRanqueadaBoard;
}
