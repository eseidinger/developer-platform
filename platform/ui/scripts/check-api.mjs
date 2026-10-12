import { readFile } from 'node:fs/promises'
import openapiTS, { astToString, COMMENT_HEADER } from 'openapi-typescript'

// Compare against the working contract, including intentional uncommitted API changes.
// A check must not rewrite the generated file or require a clean Git index.
const schema = new URL('../../../docs/api/openapi.json', import.meta.url)
const output = new URL('../src/api/generated/schema.ts', import.meta.url)
const expected = COMMENT_HEADER + astToString(await openapiTS(schema))
if ((await readFile(output, 'utf8')).replaceAll('\r\n', '\n') !== expected) {
  console.error('Generated API types are stale. Run npm run api:generate.')
  process.exitCode = 1
} else {
  console.log('Generated API types match the working OpenAPI contract.')
}
