import { backendConfig } from './config'
import type {
  AlertsResponse,
  BackendErrorResponse,
  ExplainRequest,
  ExplainResponse,
  HealthResponse,
  PredictRandomResponse,
  PredictRequest,
  PredictResponse,
  SimulateRequest,
  SimulateResponse,
  SimulationsResponse,
  ThresholdMetricsResponse,
} from './types'

type QueryValue = string | number | boolean | null | undefined

type ApiRequestOptions = {
  method?: 'GET' | 'POST'
  body?: unknown
  query?: Record<string, QueryValue>
}

export class ApiError extends Error {
  readonly status: number
  readonly statusText: string
  readonly detail: BackendErrorResponse['detail']

  constructor(response: Response, detail: BackendErrorResponse['detail']) {
    super(formatApiErrorMessage(response, detail))
    this.name = 'ApiError'
    this.status = response.status
    this.statusText = response.statusText
    this.detail = detail
  }
}

function formatApiErrorMessage(
  response: Response,
  detail: BackendErrorResponse['detail'],
) {
  if (typeof detail === 'string' && detail.length > 0) {
    return detail
  }

  return `Request failed with ${response.status} ${response.statusText}`.trim()
}

function buildUrl(path: string, query?: Record<string, QueryValue>) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const url = new URL(`${backendConfig.baseUrl}${normalizedPath}`)

  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined) {
      url.searchParams.set(key, String(value))
    }
  })

  return url
}

async function readErrorDetail(response: Response) {
  const contentType = response.headers.get('content-type') ?? ''

  if (contentType.includes('application/json')) {
    const payload = (await response.json().catch(() => null)) as
      | BackendErrorResponse
      | null
    return payload?.detail ?? null
  }

  const text = await response.text().catch(() => '')
  return text.length > 0 ? text : null
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? 'GET',
    headers:
      options.body === undefined
        ? undefined
        : {
            'Content-Type': 'application/json',
          },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })

  if (!response.ok) {
    throw new ApiError(response, await readErrorDetail(response))
  }

  return (await response.json()) as T
}

export const apiClient = {
  health: () => apiRequest<HealthResponse>('/health'),

  getAlerts: () => apiRequest<AlertsResponse>('/alerts'),

  getSimulations: () => apiRequest<SimulationsResponse>('/simulations'),

  predict: (request: PredictRequest) =>
    apiRequest<PredictResponse>('/predict', {
      method: 'POST',
      body: request,
    }),

  predictRandom: () =>
    apiRequest<PredictRandomResponse>('/predict/random', {
      method: 'POST',
    }),

  explain: (request: ExplainRequest) =>
    apiRequest<ExplainResponse>('/explain', {
      method: 'POST',
      body: request,
    }),

  simulate: (request: SimulateRequest) =>
    apiRequest<SimulateResponse>('/simulate', {
      method: 'POST',
      body: request,
    }),

  getThresholdMetrics: (threshold: number) =>
    apiRequest<ThresholdMetricsResponse>('/model/threshold', {
      query: { threshold },
    }),
}
