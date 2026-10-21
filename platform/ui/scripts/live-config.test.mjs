import assert from 'node:assert/strict'
import test from 'node:test'
import { deploymentOrigin, unitVector } from './live-config.mjs'

test('live helpers require an explicit deployment origin', () => {
  assert.equal(
    deploymentOrigin('https://platform.localhost/'),
    'https://platform.localhost',
  )
  assert.equal(
    deploymentOrigin('http://127.0.0.1:8000'),
    'http://127.0.0.1:8000',
  )
  for (const value of [
    undefined,
    'http://remote.example',
    'https://user:secret@example.com',
    'https://example.com/path',
    'https://example.com/?secret=value',
  ]) {
    assert.throws(() => deploymentOrigin(value))
  }
})

test('native vector checks match the deployed collection dimension', () => {
  assert.deepEqual(unitVector(3), [1, 0, 0])
  const vector = unitVector(384)
  assert.equal(vector.length, 384)
  assert.equal(
    vector.reduce((sum, value) => sum + value, 0),
    1,
  )
  for (const size of [undefined, 0, -1, 1.5, 65537]) {
    assert.throws(() => unitVector(size))
  }
})
