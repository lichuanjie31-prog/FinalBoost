/**
 * Verify that the committed generated.ts matches what openapi-typescript
 * would produce from the current contracts/openapi.json.
 */
import { readFileSync, unlinkSync, mkdtempSync, rmdirSync, existsSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const root = resolve(scriptDir, '..')
const contractsJson = resolve(root, 'contracts', 'openapi.json')
const savedPath = resolve(root, 'frontend', 'src', 'api', 'generated.ts')
const saved = readFileSync(savedPath, 'utf8')

const tmpDir = mkdtempSync(join(tmpdir(), 'fb-verify-'))
const tmpFile = join(tmpDir, 'generated.ts')
try {
  execSync(`npx openapi-typescript "${contractsJson}" -o "${tmpFile}"`, {
    cwd: resolve(root, 'frontend'),
    stdio: ['pipe', 'pipe', 'pipe'],
  })
  if (!existsSync(tmpFile)) throw new Error('openapi-typescript did not produce output file')
  const generated = readFileSync(tmpFile, 'utf8')
  if (generated !== saved) throw new Error('Generated TypeScript types differ; run npm run generate:api')
  console.log('GENERATED TYPES PASS: frontend types match OpenAPI')
} finally {
  if (existsSync(tmpFile)) unlinkSync(tmpFile)
  try { rmdirSync(tmpDir) } catch {}
}