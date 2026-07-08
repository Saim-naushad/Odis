const API_BASE_URL = '/api'

async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    signal,
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    const message = await safeReadErrorMessage(response)
    throw new Error(
      `Request to ${path} failed with ${response.status}: ${message}`,
    )
  }

  return (await response.json()) as T
}

async function safeReadErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data === 'string') return data
    if (data && typeof data.detail === 'string') return data.detail
    return JSON.stringify(data)
  } catch {
    return response.statusText || 'Unknown error'
  }
}

export const apiClient = {
  get: apiGet,
}

