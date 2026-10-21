// Platform modification to RustFS Console v0.1.37 (Apache-2.0).
// Preserve initial authorization and route checks while avoiding the cycle:
// page mount -> forced permission refresh -> guard unmount -> page remount.
const { readFileSync, writeFileSync } = require('node:fs')
const file = 'components/dashboard-auth-guard.tsx'
const source = readFileSync(file, 'utf8').replaceAll('\r\n', '\n')
const before =
  '  if (!isAdmin && (isLoading || !hasFetchedPolicy)) {\n    return null\n  }'
// Fail before writing if the reviewed upstream guard no longer matches exactly.
if (source.split(before).length !== 2) {
  throw Error('Reviewed RustFS guard has changed')
}
writeFileSync(
  file,
  source.replace(
    before,
    '  if (!isAdmin && !hasFetchedPolicy) {\n    return null\n  }',
  ),
)
