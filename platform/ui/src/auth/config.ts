type PortalAuthConfig = {
  issuer: string
  clientId: string
  redirectUri: string
}

type PortalAuthConfigResponse = {
  issuer?: unknown
  client_id?: unknown
  redirect_uri?: unknown
}

function isHttpUrl(value: string) {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

function parsePortalAuthConfig(value: PortalAuthConfigResponse): PortalAuthConfig {
  if (
    typeof value.issuer !== 'string' ||
    typeof value.client_id !== 'string' ||
    typeof value.redirect_uri !== 'string' ||
    !isHttpUrl(value.issuer) ||
    !isHttpUrl(value.redirect_uri)
  ) {
    throw new Error('The portal returned an invalid public OIDC configuration.')
  }

  return {
    issuer: value.issuer,
    clientId: value.client_id,
    redirectUri: value.redirect_uri,
  }
}

async function loadPortalAuthConfig() {
  const response = await fetch('/portal/config', {
    credentials: 'same-origin',
    cache: 'no-store',
  })

  if (!response.ok) {
    throw new Error('The portal OIDC configuration is unavailable.')
  }

  const payload: unknown = await response.json()
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
    throw new Error('The portal returned an invalid public OIDC configuration.')
  }

  return parsePortalAuthConfig(payload)
}

export { loadPortalAuthConfig, parsePortalAuthConfig }
export type { PortalAuthConfig }
