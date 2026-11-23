import { execFileSync, spawnSync } from 'node:child_process'
import {
  mkdtempSync,
  readFileSync,
  writeFileSync,
  chmodSync,
  rmSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it } from 'vite-plus/test'

/**
 * Executes the REAL frontend container entrypoint (`docker-entrypoint.sh`) with
 * stub `envsubst`/`nginx` binaries on PATH and a temp output directory, then
 * asserts the generated Nginx HSTS include. This tests the shell logic that
 * ships in the image rather than a reimplementation.
 */

const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(here, '..', '..')
const entrypoint = join(repoRoot, 'docker-entrypoint.sh')
const template = join(repoRoot, 'nginx.conf.template')

let work: string
let binDir: string
let confDir: string

beforeEach(() => {
  work = mkdtempSync(join(tmpdir(), 'hd-entrypoint-'))
  binDir = join(work, 'bin')
  confDir = join(work, 'conf.d')
  execFileSync('mkdir', ['-p', binDir, confDir])
  // `nginx` just exits 0; `envsubst` is a passthrough for the template.
  writeFileSync(join(binDir, 'nginx'), '#!/bin/sh\nexit 0\n')
  chmodSync(join(binDir, 'nginx'), 0o755)
  writeFileSync(join(binDir, 'envsubst'), '#!/bin/sh\ncat\n')
  chmodSync(join(binDir, 'envsubst'), 0o755)
})

afterEach(() => {
  rmSync(work, { recursive: true, force: true })
})

function runEntrypoint(env: Record<string, string>) {
  return spawnSync('sh', [entrypoint], {
    cwd: repoRoot,
    env: {
      PATH: `${binDir}:/usr/bin:/bin`,
      NGINX_CONF_DIR: confDir,
      NGINX_TEMPLATE: template,
      API_ORIGIN: 'https://api.example.test',
      ...env,
    },
    encoding: 'utf8',
  })
}

function hsts(): string {
  return readFileSync(join(confDir, 'hsts.inc'), 'utf8')
}

describe('frontend entrypoint HSTS policy', () => {
  it('omits includeSubDomains by default', () => {
    const result = runEntrypoint({ HSTS_ENABLED: 'true', HSTS_MAX_AGE_SECONDS: '31536000' })
    expect(result.status).toBe(0)
    const out = hsts()
    expect(out).toContain('Strict-Transport-Security')
    expect(out).toContain('max-age=31536000')
    expect(out).not.toContain('includeSubDomains')
  })

  it('adds includeSubDomains only when explicitly enabled', () => {
    const result = runEntrypoint({
      HSTS_ENABLED: 'true',
      HSTS_MAX_AGE_SECONDS: '31536000',
      HSTS_INCLUDE_SUBDOMAINS: 'true',
    })
    expect(result.status).toBe(0)
    expect(hsts()).toContain('includeSubDomains')
  })

  it('writes an empty include when HSTS is disabled', () => {
    const result = runEntrypoint({ HSTS_ENABLED: 'false' })
    expect(result.status).toBe(0)
    expect(hsts().trim()).toBe('')
  })

  it('renders a default.conf from the real template', () => {
    const result = runEntrypoint({ HSTS_ENABLED: 'false' })
    expect(result.status).toBe(0)
    const rendered = readFileSync(join(confDir, 'default.conf'), 'utf8')
    expect(rendered).toContain('listen 8080')
    expect(rendered).toContain('Content-Security-Policy')
  })

  it('rejects a non-boolean HSTS_INCLUDE_SUBDOMAINS', () => {
    const result = runEntrypoint({ HSTS_ENABLED: 'true', HSTS_INCLUDE_SUBDOMAINS: 'yes' })
    expect(result.status).not.toBe(0)
    expect(result.stderr).toContain('HSTS_INCLUDE_SUBDOMAINS')
  })

  it('rejects a non-numeric HSTS_MAX_AGE_SECONDS', () => {
    expect(runEntrypoint({ HSTS_ENABLED: 'true', HSTS_MAX_AGE_SECONDS: 'abc' }).status).not.toBe(0)
  })

  it('rejects a non-HTTPS API_ORIGIN', () => {
    const result = runEntrypoint({ API_ORIGIN: 'http://api.example.test' })
    expect(result.status).not.toBe(0)
    expect(result.stderr).toContain('API_ORIGIN')
  })

  it('refuses to run without API_ORIGIN', () => {
    const result = spawnSync('sh', [entrypoint], {
      cwd: repoRoot,
      env: { PATH: `${binDir}:/usr/bin:/bin`, NGINX_CONF_DIR: confDir, NGINX_TEMPLATE: template },
      encoding: 'utf8',
    })
    expect(result.status).not.toBe(0)
  })
})
