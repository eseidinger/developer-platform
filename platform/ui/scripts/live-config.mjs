// Live helpers must use the operator-selected deployment, never a baked-in host.
export function deploymentOrigin(value) {
  const url = new URL(value)
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    (url.protocol === 'http:' && !loopback) ||
    url.username ||
    url.password ||
    url.pathname !== '/' ||
    url.search ||
    url.hash
  ) {
    throw new Error(
      'A confirmed HTTPS or loopback deployment origin is required',
    )
  }
  return url.origin
}

export function unitVector(size) {
  if (!Number.isInteger(size) || size < 1 || size > 65536) {
    throw new Error('Invalid deployed vector dimension')
  }
  const vector = Array(size).fill(0)
  vector[0] = 1
  return vector
}
