import { describe, expect, it } from 'vitest'

import { parseProjectList } from '@/features/projects/projects-api'

describe('parseProjectList', () => {
  it('retains the safe project summary fields', () => {
    expect(
      parseProjectList([
        { name: 'catalog', status: 'applied', spec: { image: 'ignored' } },
      ]),
    ).toEqual([{ name: 'catalog', status: 'applied' }])
  })

  it('rejects malformed platform responses', () => {
    expect(() => parseProjectList({ projects: [] })).toThrow('invalid project list')
  })
})
