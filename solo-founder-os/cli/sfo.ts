#!/usr/bin/env tsx

import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export type Command =
  | 'validate'
  | 'generate'
  | 'write-local'
  | 'merge-local'
  | 'dry-run'
  | 'status'
  | 'list'
  | 'snapshot'
  | 'history'
  | 'help'

export type ProjectProfile = {
  project?: string
  repo?: string
  status?: string
  inherits?: {
    core?: string[]
    stacks?: string[]
    domains?: string[]
    skills?: string[]
  }
  outputs?: string[]
  overrides?: {
    protected_files?: string[]
    forbidden?: string[]
    checks?: string[]
  }
}

type GeneratedFile = {
  path: string
  content: string
}

type RuleMeta = {
  id: string
  version: string
}

export type SnapshotFileRecord = {
  path: string
  bytes: number
}

export type SnapshotManifest = {
  batchId: string
  project: string
  repo: string
  profileStatus: string
  timestamp: string
  command: 'snapshot'
  generatedFiles: SnapshotFileRecord[]
  ruleVersions: string[]
}

const ROOT = resolve(process.cwd(), 'solo-founder-os')
const GENERATED_ROOT = resolve(process.cwd(), '.sfo-generated')
const MERGED_ROOT = resolve(process.cwd(), '.sfo-merged')
const HISTORY_ROOT = resolve(process.cwd(), '.sfo-history')

export function runCli(argv: string[] = process.argv.slice(2)): void {
  const command = normalizeCommand(argv[0])
  const target = argv[1]

  ensureRootExists()

  switch (command) {
    case 'list':
      listProfiles()
      return
    case 'status':
      status(target)
      return
    case 'validate':
      validate(target)
      return
    case 'generate':
      generate(target)
      return
    case 'write-local':
      writeLocal(target)
      return
    case 'merge-local':
      mergeLocal(target)
      return
    case 'dry-run':
      dryRun(target)
      return
    case 'snapshot':
      snapshot(target)
      return
    case 'history':
      history(target)
      return
    case 'help':
    default:
      printHelp()
  }
}

function normalizeCommand(value?: string): Command {
  switch (value) {
    case 'list':
    case 'status':
    case 'validate':
    case 'generate':
    case 'write-local':
    case 'merge-local':
    case 'dry-run':
    case 'snapshot':
    case 'history':
    case 'help':
      return value
    default:
      return 'help'
  }
}

function ensureRootExists(): void {
  if (!existsSync(ROOT)) {
    fail(`solo-founder-os directory was not found at ${ROOT}`)
  }
}

function listProfiles() {
  const profiles = loadProfiles()
  for (const profile of profiles) {
    console.log(`${profile.project ?? 'unknown'} -> ${profile.repo ?? 'no repo'}`)
  }
}

function status(target?: string) {
  const profiles = resolveProfiles(loadProfiles(), target)

  for (const profile of profiles) {
    console.log(`\n${profile.project ?? 'unknown-project'}`)
    console.log(`repo: ${profile.repo ?? 'unknown-repo'}`)
    console.log(`profile status: ${profile.status ?? 'unknown'}`)

    printMetaGroup('core', profile.inherits?.core ?? [], 'core', 'md')
    printMetaGroup('stacks', profile.inherits?.stacks ?? [], 'stacks', 'md')
    printMetaGroup('domains', profile.inherits?.domains ?? [], 'domains', 'md')
    printMetaGroup('skills', profile.inherits?.skills ?? [], 'skills', 'yml')
  }
}

function printMetaGroup(label: string, names: string[], folder: string, ext: string) {
  console.log(`${label}:`)
  if (!names.length) {
    console.log('  - none')
    return
  }

  for (const name of names) {
    const meta = readRuleMeta(folder, name, ext)
    console.log(`  - ${meta.id}@${meta.version}`)
  }
}

function validate(target?: string) {
  const profiles = resolveProfiles(loadProfiles(), target)
  let errors = 0

  for (const profile of profiles) {
    const result = validateProfile(profile)
    if (result.length > 0) {
      errors += result.filter((item) => item.startsWith('error:')).length || result.length
      console.log(`\n${profile.project ?? 'unknown'}: invalid`)
      for (const item of result) console.log(`- ${item}`)
    } else {
      console.log(`${profile.project}: ok`)
    }
  }

  if (errors > 0) process.exitCode = 1
}

function generate(target?: string) {
  const profiles = resolveProfiles(loadProfiles(), target)
  for (const profile of profiles) {
    const errors = validationErrors(profile)
    if (errors.length > 0) {
      reportSkippedProfile(profile, errors)
      continue
    }

    const files = buildGeneratedFiles(profile)
    for (const file of files) {
      console.log(`\n--- ${profile.project}: ${file.path} ---\n`)
      console.log(file.content)
    }
  }
}

function writeLocal(target?: string) {
  const profiles = resolveProfiles(loadProfiles(), target)
  for (const profile of profiles) {
    const errors = validationErrors(profile)
    if (errors.length > 0) {
      reportSkippedProfile(profile, errors)
      continue
    }

    const projectDir = join(GENERATED_ROOT, profile.project ?? 'unknown-project')
    for (const file of buildGeneratedFiles(profile)) {
      const path = join(projectDir, file.path)
      mkdirSync(dirname(path), { recursive: true })
      writeFileSync(path, file.content, 'utf8')
      console.log(`wrote ${path}`)
    }
  }
}

function mergeLocal(target?: string) {
  const profiles = resolveProfiles(loadProfiles(), target)
  for (const profile of profiles) {
    const errors = validationErrors(profile)
    if (errors.length > 0) {
      reportSkippedProfile(profile, errors)
      continue
    }

    const projectDir = join(MERGED_ROOT, profile.project ?? 'unknown-project')
    for (const file of buildGeneratedFiles(profile)) {
      const existingPath = join(GENERATED_ROOT, profile.project ?? 'unknown-project', file.path)
      const existing = existsSync(existingPath) ? readFileSync(existingPath, 'utf8') : ''
      const merged = mergeControlledBlocks(existing, file.content)
      const outputPath = join(projectDir, file.path)
      mkdirSync(dirname(outputPath), { recursive: true })
      writeFileSync(outputPath, merged, 'utf8')
      console.log(`merged ${outputPath}`)
    }
  }
}

function dryRun(target?: string) {
  const profiles = resolveProfiles(loadProfiles(), target)
  for (const profile of profiles) {
    const validation = validateProfile(profile)
    const errors = validation.filter((item) => item.startsWith('error:'))
    const warnings = validation.filter((item) => item.startsWith('warning:'))
    const files = errors.length ? [] : buildGeneratedFiles(profile)
    console.log(`\n${profile.project ?? 'unknown-project'}`)
    console.log(`repo: ${profile.repo ?? 'unknown-repo'}`)
    console.log(`status: ${errors.length ? 'invalid' : warnings.length ? 'valid with warnings' : 'valid'}`)
    console.log(`outputs: ${(profile.outputs ?? []).join(', ') || 'none'}`)
    console.log(`generated files: ${files.map((file) => file.path).join(', ') || 'none'}`)
    console.log(`checks: ${(profile.overrides?.checks ?? []).join(', ') || 'none'}`)
    if (validation.length) {
      console.log('validation:')
      for (const item of validation) console.log(`- ${item}`)
    }
  }
}

function snapshot(target?: string) {
  const profiles = resolveProfiles(loadProfiles(), target)
  let created = 0
  let blocked = 0

  for (const profile of profiles) {
    const errors = validationErrors(profile)
    if (errors.length > 0) {
      blocked += 1
      reportSkippedProfile(profile, errors)
      continue
    }

    const manifest = createSnapshotManifest(profile, buildGeneratedFiles(profile))
    const manifestPath = writeSnapshotManifest(manifest)
    created += 1
    console.log(`snapshotted ${manifest.project} -> ${manifestPath}`)
  }

  if (created === 0 && blocked > 0) process.exitCode = 1
}

function history(target?: string) {
  const historyTarget = target ? resolveProfiles(loadProfiles(), target)[0]?.project ?? target : undefined
  const entries = readSnapshotHistory({ target: historyTarget })

  if (!entries.length) {
    console.log(historyTarget ? `No snapshot history found for ${historyTarget}.` : 'No snapshot history found.')
    return
  }

  let currentProject: string | null = null

  for (const entry of entries) {
    if (entry.project !== currentProject) {
      if (currentProject) console.log('')
      console.log(entry.project)
      currentProject = entry.project
    }

    console.log(
      `- ${entry.timestamp} | batch=${entry.batchId} | files=${entry.generatedFiles.length} | repo=${entry.repo}`,
    )
  }
}

function reportSkippedProfile(profile: ProjectProfile, errors: string[]) {
  console.log(`${profile.project ?? 'unknown-project'}: skipped, invalid profile`)
  for (const error of errors) console.log(`- ${error}`)
}

export function loadProfiles(root: string = ROOT): ProjectProfile[] {
  const dir = join(root, 'project-profiles')
  if (!existsSync(dir)) fail(`project-profiles directory was not found at ${dir}`)

  return readdirSync(dir)
    .filter((file) => file.endsWith('.yml') || file.endsWith('.yaml'))
    .sort()
    .map((file) => parseProfile(readFileSync(join(dir, file), 'utf8')))
}

export function resolveProfiles(profiles: ProjectProfile[], target?: string): ProjectProfile[] {
  if (!target) return profiles

  const matches = filterProfiles(profiles, target)
  if (matches.length > 0) return matches

  throw new Error(`project profile not found: ${target}`)
}

export function filterProfiles(profiles: ProjectProfile[], target?: string): ProjectProfile[] {
  if (!target) return profiles
  return profiles.filter((profile) => profile.project === target || profile.repo === target)
}

export function validateProfile(profile: ProjectProfile): string[] {
  const errors: string[] = []

  if (!profile.project) errors.push('error: missing project')
  if (!profile.repo) errors.push('error: missing repo')

  for (const core of profile.inherits?.core ?? []) {
    if (!existsSync(join(ROOT, 'core', `${core}.md`))) errors.push(`error: missing core rule: ${core}`)
  }

  for (const stack of profile.inherits?.stacks ?? []) {
    if (!existsSync(join(ROOT, 'stacks', `${stack}.md`))) errors.push(`error: missing stack rule: ${stack}`)
  }

  for (const domain of profile.inherits?.domains ?? []) {
    if (!existsSync(join(ROOT, 'domains', `${domain}.md`))) errors.push(`error: missing domain rule: ${domain}`)
  }

  for (const skill of profile.inherits?.skills ?? []) {
    if (!existsSync(join(ROOT, 'skills', `${skill}.yml`))) errors.push(`error: missing skill: ${skill}`)
  }

  errors.push(...detectConflicts(profile))

  return errors
}

function validationErrors(profile: ProjectProfile): string[] {
  return validateProfile(profile).filter((item) => item.startsWith('error:'))
}

function detectConflicts(profile: ProjectProfile): string[] {
  const messages: string[] = []
  const stacks = profile.inherits?.stacks ?? []
  const skills = profile.inherits?.skills ?? []
  const forbidden = profile.overrides?.forbidden ?? []

  if (hasAll(stacks, ['next15', 'next16'])) {
    messages.push('error: Project cannot inherit both next15 and next16.')
  }

  if (stacks.includes('next15') && !forbidden.includes('src/proxy.ts')) {
    messages.push('error: Next15 projects must explicitly forbid src/proxy.ts unless upgraded.')
  }

  if (stacks.includes('next16') && !forbidden.includes('middleware.ts')) {
    messages.push('warning: Next16 projects should forbid old middleware.ts patterns.')
  }

  if (stacks.includes('flutter') && hasAny(stacks, ['next15', 'next16'])) {
    messages.push('error: Flutter project cannot inherit Next.js stack rules.')
  }

  if (stacks.includes('static-site') && hasAny(stacks, ['next15', 'next16', 'hono-mcp'])) {
    messages.push('warning: Static sites should not inherit app-framework/backend stack rules.')
  }

  if (stacks.includes('hono-mcp') && hasAny(stacks, ['next15', 'next16'])) {
    messages.push('error: Hono/MCP backend should not inherit Next.js frontend rules.')
  }

  if (stacks.includes('static-site') && skills.includes('database-migration')) {
    messages.push('warning: Static sites usually should not use database-migration skill.')
  }

  return messages
}

function hasAll(source: string[], values: string[]): boolean {
  return values.every((value) => source.includes(value))
}

function hasAny(source: string[], values: string[]): boolean {
  return values.some((value) => source.includes(value))
}

export function buildGeneratedFiles(profile: ProjectProfile): GeneratedFile[] {
  const rulesBundle = buildRuleBundle(profile)
  const replacements = buildReplacements(profile, rulesBundle)

  return (profile.outputs ?? []).map((output) => {
    const template = templateForOutput(output)
    return {
      path: output,
      content: renderTemplate(template, replacements),
    }
  })
}

function templateForOutput(output: string): string {
  const map: Record<string, string> = {
    'AGENTS.md': 'AGENTS.md.tpl',
    'CLAUDE.md': 'CLAUDE.md.tpl',
    '.cursor/rules/agent-workflow.mdc': 'cursor-agent-workflow.mdc.tpl',
    '.claude/commands/check.md': 'claude-check.md.tpl',
    '.claude/commands/save-work.md': 'claude-save-work.md.tpl',
    '.claude/commands/release-work.md': 'claude-release-work.md.tpl',
    '.claude/commands/review-work.md': 'claude-review-work.md.tpl',
  }

  const templateName = map[output]
  if (!templateName) return fallbackTemplate(output)

  const path = join(ROOT, 'templates', templateName)
  if (!existsSync(path)) return fallbackTemplate(output)
  return readFileSync(path, 'utf8')
}

function fallbackTemplate(output: string): string {
  return `# {{project}}\n\nGenerated output path: ${output}\n\n{{rules_bundle}}\n\nProtected files:\n{{protected_files}}\n\nForbidden patterns:\n{{forbidden}}\n\nChecks:\n{{checks}}\n`
}

function buildRuleBundle(profile: ProjectProfile): string {
  const sections: string[] = []

  for (const core of profile.inherits?.core ?? []) sections.push(readSection('core', core, 'md'))
  for (const stack of profile.inherits?.stacks ?? []) sections.push(readSection('stacks', stack, 'md'))
  for (const domain of profile.inherits?.domains ?? []) sections.push(readSection('domains', domain, 'md'))

  return sections.join('\n\n')
}

function buildReplacements(profile: ProjectProfile, rulesBundle: string): Record<string, string> {
  return {
    project: profile.project ?? 'unknown-project',
    repo: profile.repo ?? 'unknown-repo',
    rules_bundle: rulesBundle,
    protected_files: listOrNone(profile.overrides?.protected_files),
    forbidden: listOrNone(profile.overrides?.forbidden),
    checks: listOrNone(profile.overrides?.checks),
  }
}

function listOrNone(items?: string[]): string {
  if (!items?.length) return '- none'
  return items.map((item) => `- ${item}`).join('\n')
}

function renderTemplate(template: string, replacements: Record<string, string>): string {
  return Object.entries(replacements).reduce(
    (result, [key, value]) => result.replaceAll(`{{${key}}}`, value),
    template,
  )
}

function readSection(folder: string, name: string, ext: string): string {
  const path = join(ROOT, folder, `${name}.${ext}`)
  const content = readFileSync(path, 'utf8')
  const meta = readRuleMeta(folder, name, ext)
  return `<!-- SFO:BEGIN ${folder}/${name}@${meta.version} -->\n${content.trim()}\n<!-- SFO:END ${folder}/${name}@${meta.version} -->`
}

function readRuleMeta(folder: string, name: string, ext: string): RuleMeta {
  const path = join(ROOT, folder, `${name}.${ext}`)
  if (!existsSync(path)) return { id: `${folder}/${name}`, version: 'missing' }

  const content = readFileSync(path, 'utf8')
  const id = findMetaValue(content, 'id') ?? `${folder}/${name}`
  const version = findMetaValue(content, 'version') ?? 'unknown'
  return { id, version }
}

function findMetaValue(content: string, key: string): string | undefined {
  const pattern = new RegExp(`^${key}:\\s*(.+)$`, 'm')
  const match = content.match(pattern)
  return match?.[1]?.trim()
}

export function mergeControlledBlocks(existing: string, generated: string): string {
  if (!existing.trim()) return generated

  let result = existing
  const blocks = extractControlledBlocks(generated)

  for (const block of blocks) {
    const pattern = new RegExp(
      `<!-- SFO:BEGIN ${escapeRegExp(block.id)} -->[\\s\\S]*?<!-- SFO:END ${escapeRegExp(block.id)} -->`,
      'g',
    )

    if (pattern.test(result)) {
      result = result.replace(pattern, block.content)
    } else {
      result = `${result.trim()}\n\n${block.content}\n`
    }
  }

  return result
}

export function extractControlledBlocks(content: string): Array<{ id: string; content: string }> {
  const blocks: Array<{ id: string; content: string }> = []
  const pattern = /<!-- SFO:BEGIN ([^>]+) -->[\s\S]*?<!-- SFO:END \1 -->/g
  let match: RegExpExecArray | null

  while ((match = pattern.exec(content))) {
    const id = match[1]
    const blockContent = match[0]

    if (!id || !blockContent) continue

    blocks.push({ id, content: blockContent })
  }

  return blocks
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function parseProfile(input: string): ProjectProfile {
  const profile: ProjectProfile = { inherits: {}, outputs: [], overrides: {} }
  let section: string | null = null
  let subsection: string | null = null

  for (const rawLine of input.split('\n')) {
    const line = rawLine.replace(/\s+$/g, '')
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue

    if (!line.startsWith(' ') && trimmed.endsWith(':')) {
      section = trimmed.slice(0, -1)
      subsection = null
      continue
    }

    if (!line.startsWith(' ') && trimmed.includes(':')) {
      const [key, ...rest] = trimmed.split(':')
      const value = rest.join(':').trim()
      if (!key) continue
      ;(profile as Record<string, unknown>)[key] = value
      continue
    }

    if (section === 'inherits' && line.startsWith('  ') && trimmed.endsWith(':')) {
      subsection = trimmed.slice(0, -1)
      continue
    }

    if (section === 'overrides' && line.startsWith('  ') && trimmed.endsWith(':')) {
      subsection = trimmed.slice(0, -1)
      continue
    }

    if (trimmed.startsWith('- ')) {
      const item = trimmed.slice(2)
      if (section === 'outputs') profile.outputs?.push(item)
      if (section === 'inherits' && subsection) {
        const list = (profile.inherits as Record<string, string[]>)[subsection] ?? []
        list.push(item)
        ;(profile.inherits as Record<string, string[]>)[subsection] = list
      }
      if (section === 'overrides' && subsection) {
        const list = (profile.overrides as Record<string, string[]>)[subsection] ?? []
        list.push(item)
        ;(profile.overrides as Record<string, string[]>)[subsection] = list
      }
    }
  }

  return profile
}

export function createSnapshotManifest(
  profile: ProjectProfile,
  generatedFiles: GeneratedFile[],
  options: { timestamp?: string; batchId?: string } = {},
): SnapshotManifest {
  const timestamp = options.timestamp ?? new Date().toISOString()

  return {
    batchId: options.batchId ?? createBatchId(timestamp),
    project: profile.project ?? 'unknown-project',
    repo: profile.repo ?? 'unknown-repo',
    profileStatus: profile.status ?? 'unknown',
    timestamp,
    command: 'snapshot',
    generatedFiles: generatedFiles.map((file) => ({
      path: file.path,
      bytes: Buffer.byteLength(file.content, 'utf8'),
    })),
    ruleVersions: collectRuleVersions(profile),
  }
}

function collectRuleVersions(profile: ProjectProfile): string[] {
  return [
    ...collectMetaRefs('core', profile.inherits?.core ?? [], 'md'),
    ...collectMetaRefs('stacks', profile.inherits?.stacks ?? [], 'md'),
    ...collectMetaRefs('domains', profile.inherits?.domains ?? [], 'md'),
    ...collectMetaRefs('skills', profile.inherits?.skills ?? [], 'yml'),
  ]
}

function collectMetaRefs(folder: string, names: string[], ext: string): string[] {
  return names.map((name) => {
    const meta = readRuleMeta(folder, name, ext)
    return `${meta.id}@${meta.version}`
  })
}

function createBatchId(timestamp: string): string {
  const safeTimestamp = timestamp.replace(/[:.]/g, '-')
  return `${safeTimestamp}-${randomUUID().slice(0, 8)}`
}

export function writeSnapshotManifest(
  manifest: SnapshotManifest,
  historyRoot: string = HISTORY_ROOT,
): string {
  const projectDir = join(historyRoot, manifest.project)
  mkdirSync(projectDir, { recursive: true })

  const manifestPath = join(projectDir, `${manifest.batchId}.json`)
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
  return manifestPath
}

export function readSnapshotHistory(options: {
  historyRoot?: string
  target?: string
} = {}): SnapshotManifest[] {
  const historyRoot = options.historyRoot ?? HISTORY_ROOT
  if (!existsSync(historyRoot)) return []

  const projectDirs = resolveHistoryProjects(historyRoot, options.target)
  const manifests: SnapshotManifest[] = []

  for (const project of projectDirs) {
    const projectDir = join(historyRoot, project)
    if (!existsSync(projectDir)) continue

    const files = readdirSync(projectDir)
      .filter((file) => file.endsWith('.json'))
      .sort()

    for (const file of files) {
      const path = join(projectDir, file)
      try {
        const manifest = JSON.parse(readFileSync(path, 'utf8')) as SnapshotManifest
        manifests.push(manifest)
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        console.warn(`warning: failed to read snapshot manifest ${path}: ${message}`)
      }
    }
  }

  return manifests.sort((left, right) => {
    if (left.project !== right.project) return left.project.localeCompare(right.project)
    return right.timestamp.localeCompare(left.timestamp)
  })
}

function resolveHistoryProjects(historyRoot: string, target?: string): string[] {
  if (!target) {
    return readdirSync(historyRoot)
      .filter((entry) => existsSync(join(historyRoot, entry)))
      .sort()
  }

  const profiles = loadProfiles()
  const matches = filterProfiles(profiles, target).map((profile) => profile.project).filter(Boolean)
  if (matches.length > 0) return matches as string[]

  return [target]
}

function printHelp() {
  console.log(
    `Solo Founder Agent OS CLI\n\nCommands:\n  sfo list\n  sfo status [project]\n  sfo validate [project]\n  sfo generate [project]\n  sfo write-local [project]\n  sfo merge-local [project]\n  sfo dry-run [project]\n  sfo snapshot [project]\n  sfo history [project]\n`,
  )
}

function fail(message: string): never {
  console.error(message)
  process.exit(1)
}

function main() {
  try {
    runCli()
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    fail(message)
  }
}

const isDirectExecution =
  process.argv[1] !== undefined && resolve(process.argv[1]) === fileURLToPath(import.meta.url)

if (isDirectExecution) {
  main()
}
