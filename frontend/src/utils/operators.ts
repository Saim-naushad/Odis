import { useState } from 'react'

export interface Operator {
  id: string
  displayName: string
  role: string
}

/**
 * Fixed roster for the demo/portfolio deployment. A named on-call roster
 * (vs. free-text operator identity) matches how real incident tools
 * (PagerDuty, Datadog) attribute actions, and keeps investigation
 * transitions attributable without standing up real authentication.
 */
export const OPERATORS: readonly Operator[] = [
  { id: 'j-rivera', displayName: 'J. Rivera', role: 'Shift Lead' },
  { id: 'm-chen', displayName: 'M. Chen', role: 'Operations Engineer' },
  { id: 'a-osei', displayName: 'A. Osei', role: 'Reliability Engineer' },
]

const STORAGE_KEY = 'odis.selectedOperatorId'

function readStoredOperatorId(): string | undefined {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? undefined
  } catch {
    return undefined
  }
}

function writeStoredOperatorId(operatorId: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, operatorId)
  } catch {
    // Storage unavailable (private browsing, etc.) — selection just won't persist.
  }
}

/** Currently selected operator persona, persisted across sessions. */
export function useSelectedOperator(): [Operator, (operatorId: string) => void] {
  const [operatorId, setOperatorId] = useState<string>(
    () => readStoredOperatorId() ?? OPERATORS[0].id,
  )

  function selectOperator(nextId: string): void {
    setOperatorId(nextId)
    writeStoredOperatorId(nextId)
  }

  const operator = OPERATORS.find((candidate) => candidate.id === operatorId) ?? OPERATORS[0]
  return [operator, selectOperator]
}
