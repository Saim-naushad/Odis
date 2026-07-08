export type SseClientOptions<TEvent = unknown> = {
  url: string
  withCredentials?: boolean
  onOpen?: () => void
  onError?: (error: Event) => void
  onMessage?: (data: string) => void
  onEvent?: (event: MessageEvent<string>) => void
  parse?: (raw: string) => TEvent
}

export type SseClient<TEvent = unknown> = {
  source: EventSource
  parse: (raw: string) => TEvent
  close: () => void
  addEventListener: (
    type: string,
    listener: (event: MessageEvent<string>) => void,
  ) => void
}

export function createSseClient<TEvent = unknown>(
  options: SseClientOptions<TEvent>,
): SseClient<TEvent> {
  const source = new EventSource(options.url, {
    withCredentials: options.withCredentials,
  })

  const parse: (raw: string) => TEvent =
    options.parse ??
    ((raw) => {
      try {
        return JSON.parse(raw) as TEvent
      } catch {
        return raw as unknown as TEvent
      }
    })

  if (options.onOpen) {
    source.addEventListener('open', () => {
      options.onOpen?.()
    })
  }

  source.addEventListener('error', (event) => {
    options.onError?.(event)
  })

  source.addEventListener('message', (event) => {
    options.onMessage?.(event.data)
    options.onEvent?.(event)
  })

  return {
    source,
    parse,
    close: () => source.close(),
    addEventListener: (type, listener) => {
      source.addEventListener(type, listener as EventListener)
    },
  }
}

