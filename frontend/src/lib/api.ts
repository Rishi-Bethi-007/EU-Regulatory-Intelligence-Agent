const API_BASE = '/api'

export async function startResearch(goal: string, userId: string): Promise<{ run_id: string }> {
  const res = await fetch(`${API_BASE}/research`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ goal, user_id: userId }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getRunStatus(runId: string) {
  const res = await fetch(`${API_BASE}/research/${runId}/status`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getAgentTasks(runId: string) {
  const res = await fetch(`${API_BASE}/research/${runId}/agents`)
  if (res.status === 404) return { agents: [] }
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function verifyAuditChain() {
  const res = await fetch(`${API_BASE}/audit/verify`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getUserData(userId: string) {
  const res = await fetch(`${API_BASE}/users/${userId}/data`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function eraseUserData(userId: string) {
  const res = await fetch(`${API_BASE}/users/${userId}/data`, { method: 'DELETE' })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
