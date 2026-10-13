import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import {
  createSnapshotManifest,
  mergeControlledBlocks,
  parseProfile,
  readSnapshotHistory,
  resolveProfiles,
  writeSnapshotManifest,
} from './sfo'

const tempDirs: string[] = []

function makeTempDir(): string {
  const dir = mkdtempSync(join(tmpdir(), 'sfo-cli-test-'))
  tempDirs.push(dir)
  return dir
}

afterEach(() => {
  while (tempDirs.length > 0) {
    const dir = tempDirs.pop()
    if (dir) rmSync(dir, { recursive: true, force: true })
  }
})

describe('parseProfile()', () => {
  it('keeps nested inherits, outputs and overrides', () => {
    const profile = parseProfile(`
project: demo
repo: kulikman/demo
status: draft

inherits:
  core:
    - git-protocol
  stacks:
    - next16

outputs:
  - AGENTS.md

overrides:
  forbidden:
    - middleware.ts
`)

    expect(profile.project).toBe('demo')
    expect(profile.inherits?.core).toEqual(['git-protocol'])
    expect(profile.inherits?.stacks).toEqual(['next16'])
    expect(profile.outputs).toEqual(['AGENTS.md'])
    expect(profile.overrides?.forbidden).toEqual(['middleware.ts'])
  })
})

describe('snapshot history', () => {
  it('creates a manifest with generated file metadata', () => {
    const manifest = createSnapshotManifest(
      {
        project: 'demo',
        repo: 'kulikman/demo',
        status: 'draft',
        inherits: { core: ['git-protocol'] },
      },
      [{ path: 'AGENTS.md', content: 'hello world' }],
      { timestamp: '2026-06-19T10:00:00.000Z', batchId: 'batch-1' },
    )

    expect(manifest).toMatchObject({
      batchId: 'batch-1',
      project: 'demo',
      repo: 'kulikman/demo',
      profileStatus: 'draft',
      command: 'snapshot',
    })
    expect(manifest.generatedFiles).toEqual([{ path: 'AGENTS.md', bytes: 11 }])
    expect(manifest.ruleVersions).toContain('core/git-protocol@1.0.0')
  })

  it('writes and reads manifests sorted by newest timestamp first', () => {
    const historyRoot = makeTempDir()

    writeSnapshotManifest(
      {
        batchId: 'batch-old',
        project: 'demo',
        repo: 'kulikman/demo',
        profileStatus: 'draft',
        timestamp: '2026-06-19T09:00:00.000Z',
        command: 'snapshot',
        generatedFiles: [{ path: 'AGENTS.md', bytes: 10 }],
        ruleVersions: ['core/git-protocol@1.0.0'],
      },
      historyRoot,
    )

    writeSnapshotManifest(
      {
        batchId: 'batch-new',
        project: 'demo',
        repo: 'kulikman/demo',
        profileStatus: 'draft',
        timestamp: '2026-06-19T10:00:00.000Z',
        command: 'snapshot',
        generatedFiles: [{ path: 'CLAUDE.md', bytes: 20 }],
        ruleVersions: ['core/git-protocol@1.0.0'],
      },
      historyRoot,
    )

    const entries = readSnapshotHistory({ historyRoot, target: 'demo' })

    expect(entries.map((entry) => entry.batchId)).toEqual(['batch-new', 'batch-old'])
  })
})

describe('resolveProfiles()', () => {
  it('throws on unknown target instead of silently returning empty output', () => {
    expect(() =>
      resolveProfiles([{ project: 'demo', repo: 'kulikman/demo' }], 'missing-project'),
    ).toThrow('project profile not found: missing-project')
  })

  it('normalizes repo targets to the underlying project name', () => {
    const [profile] = resolveProfiles([{ project: 'demo', repo: 'kulikman/demo' }], 'kulikman/demo')

    expect(profile?.project).toBe('demo')
  })
})

describe('mergeControlledBlocks()', () => {
  it('keeps manual sections while replacing an existing SFO block', () => {
    const existing = `# Project Rules

Manual intro stays.

<!-- SFO:BEGIN core/git-protocol@1.0.0 -->
old generated text
<!-- SFO:END core/git-protocol@1.0.0 -->

Manual outro stays.
`

    const generated = `<!-- SFO:BEGIN core/git-protocol@1.0.0 -->
new generated text
<!-- SFO:END core/git-protocol@1.0.0 -->`

    const merged = mergeControlledBlocks(existing, generated)

    expect(merged).toContain('Manual intro stays.')
    expect(merged).toContain('Manual outro stays.')
    expect(merged).toContain('new generated text')
    expect(merged).not.toContain('old generated text')
  })

  it('appends new SFO blocks without deleting manual content', () => {
    const existing = `# Project Rules

Manual only.
`

    const generated = `<!-- SFO:BEGIN stacks/next16@1.0.0 -->
Next.js 16 rules
<!-- SFO:END stacks/next16@1.0.0 -->`

    const merged = mergeControlledBlocks(existing, generated)

    expect(merged).toContain('Manual only.')
    expect(merged).toContain('<!-- SFO:BEGIN stacks/next16@1.0.0 -->')
    expect(merged).toContain('Next.js 16 rules')
  })

  it('returns generated content when no existing file content is present', () => {
    const generated = `<!-- SFO:BEGIN core/security@1.0.0 -->
Security rules
<!-- SFO:END core/security@1.0.0 -->`

    expect(mergeControlledBlocks('', generated)).toBe(generated)
  })
})
