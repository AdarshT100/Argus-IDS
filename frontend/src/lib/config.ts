const defaultBackendUrl = 'http://localhost:8000'

function normalizeBaseUrl(url: string) {
  return url.replace(/\/+$/, '')
}

export const backendConfig = {
  defaultBackendUrl,
  baseUrl: normalizeBaseUrl(
    import.meta.env.VITE_ARGUS_BACKEND_URL ?? defaultBackendUrl,
  ),
}

export const backendUrl = backendConfig.baseUrl
