export interface CommandSource {
  key?: string | number
  label?: unknown
  name?: string
  type?: string
  disabled?: boolean
  children?: CommandSource[]
}

export interface NavigationCommand {
  path: string
  label: string
  category: string
  searchText: string
}

const MAX_QUERY_LENGTH = 80
const MAX_RESULTS = 25

const COMMAND_ALIASES: Record<string, string> = {
  '/integrations': 'baglanti kopru servis durum health jira doors teamcenter docproof',
  '/jobs': 'islem kuyruk gorev gecmis retry tekrar iptal artifact',
  '/outlook': 'mail eposta msg ecr task gorev',
  '/dcc': 'ecr change degisiklik jira master watcher',
  '/doors/poclinker': 'gereksinim requirement link baglanti poc',
  '/doors/agent': 'gereksinim requirement nesne object',
  '/doors/scripter': 'dxl script kod generator',
  '/teamcenter/agent': 'plm urun product lifecycle',
  '/compare/excel': 'xlsx karsilastir fark spreadsheet',
  '/compare/word': 'docx karsilastir fark belge',
  '/compare/pdf': 'karsilastir fark dokuman belge',
  '/pdf/split': 'bol ayir parca dokuman',
  '/media-converter': 'video resim donustur convert image',
  '/translator': 'ceviri tercume translate word yapay zeka ai',
  '/ddfAssistant': 'ddf asistan excel jira',
  '/pptxGallery': 'powerpoint sunum slayt galeri',
  '/organization': 'organizasyon kisi panel proje sorumlu',
  '/users': 'kullanici uye davet invitation yetki rol grup',
  '/settings': 'ayar tercih sifre password tema'
}

/** Convert nested menu options into safe, navigable leaf commands. */
export function buildNavigationCommands(options: CommandSource[]): NavigationCommand[] {
  return options.flatMap((option) => commandFromOption(option, []))
}

/** Rank navigation commands using normalized labels, categories, paths, and aliases. */
export function searchNavigationCommands(
  commands: NavigationCommand[],
  query: string,
  limit = 10
): NavigationCommand[] {
  const normalizedQuery = normalizeSearchText(query).slice(0, MAX_QUERY_LENGTH)
  const boundedLimit = Math.max(0, Math.min(limit, MAX_RESULTS))
  if (!normalizedQuery) return commands.slice(0, boundedLimit)
  return commands
    .map((command) => ({ command, score: commandScore(command, normalizedQuery) }))
    .filter((candidate) => candidate.score > 0)
    .sort(compareCandidates)
    .slice(0, boundedLimit)
    .map((candidate) => candidate.command)
}

/** Put valid recent commands first without duplicating or inventing routes. */
export function prioritizeRecentCommands(
  commands: NavigationCommand[],
  recentPaths: string[]
): NavigationCommand[] {
  const recentOrder = new Map(recentPaths.map((path, index) => [path, index]))
  return commands
    .map((command, index) => ({ command, index }))
    .sort((left, right) => compareRecent(left, right, recentOrder))
    .map(({ command }) => command)
}

/** Add a route to bounded most-recent-first command history. */
export function mergeRecentCommand(recentPaths: string[], path: string, limit = 6): string[] {
  return [path, ...recentPaths.filter((recentPath) => recentPath !== path)].slice(0, limit)
}

/** Normalize user-entered text for accent and punctuation independent matching. */
export function normalizeSearchText(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('tr-TR')
    .replace(/ı/g, 'i')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function commandFromOption(option: CommandSource, parents: string[]): NavigationCommand[] {
  if (option.type === 'divider' || option.disabled) return []
  const label = typeof option.label === 'string' ? option.label : ''
  if (option.children?.length) {
    const categories = label ? [...parents, label] : parents
    return option.children.flatMap((child) => commandFromOption(child, categories))
  }
  if (!label || typeof option.key !== 'string' || !option.key.startsWith('/')) return []
  return [createCommand(option.key, label, parents.join(' › '), option.name)]
}

function createCommand(
  path: string,
  label: string,
  category: string,
  name = ''
): NavigationCommand {
  const searchable = [label, category, path, name, COMMAND_ALIASES[path] || ''].join(' ')
  return { path, label, category, searchText: normalizeSearchText(searchable) }
}

function commandScore(command: NavigationCommand, query: string): number {
  const label = normalizeSearchText(command.label)
  if (label === query) return 500
  if (label.startsWith(query)) return 400
  if (command.searchText.includes(query)) return 300
  if (queryTokensMatch(command.searchText, query)) return 200
  return fuzzyScore(command.searchText, query)
}

function queryTokensMatch(searchText: string, query: string): boolean {
  return query.split(' ').every((token) => searchText.includes(token))
}

function fuzzyScore(searchText: string, query: string): number {
  if (query.length < 4) return 0
  const threshold = Math.max(1, Math.floor(query.length / 4))
  const distances = searchText.split(' ').map((word) => editDistance(word, query))
  const distance = Math.min(...distances)
  return distance <= threshold ? 100 - distance : 0
}

function editDistance(left: string, right: string): number {
  let previous = Array.from({ length: right.length + 1 }, (_, index) => index)
  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    const current = [leftIndex]
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      const substitution =
        previous[rightIndex - 1] + Number(left[leftIndex - 1] !== right[rightIndex - 1])
      current[rightIndex] = Math.min(
        previous[rightIndex] + 1,
        current[rightIndex - 1] + 1,
        substitution
      )
    }
    previous = current
  }
  return previous[right.length]
}

function compareCandidates(
  left: { command: NavigationCommand; score: number },
  right: { command: NavigationCommand; score: number }
): number {
  return right.score - left.score || left.command.label.localeCompare(right.command.label)
}

function compareRecent(
  left: { command: NavigationCommand; index: number },
  right: { command: NavigationCommand; index: number },
  recentOrder: Map<string, number>
): number {
  const leftOrder = recentOrder.get(left.command.path) ?? Number.MAX_SAFE_INTEGER
  const rightOrder = recentOrder.get(right.command.path) ?? Number.MAX_SAFE_INTEGER
  return leftOrder - rightOrder || left.index - right.index
}
