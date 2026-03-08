export interface SkillInfo {
  name: string
  description: string
  source: string // "bundled" | "project"
  when_to_use: string | null
  user_invocable: boolean
}

export interface InstallResponse {
  success: boolean
  skill: SkillInfo | null
  message: string
}

const BASE = import.meta.env.VITE_API_BASE ?? ''

export async function listSkills(): Promise<SkillInfo[]> {
  const res = await fetch(`${BASE}/api/skills`)
  if (!res.ok) throw new Error(`列表请求失败: ${res.status}`)
  return res.json()
}

export async function installSkill(source: string): Promise<InstallResponse> {
  const res = await fetch(`${BASE}/api/skills/install`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(data.detail || `安装失败: ${res.status}`)
  }
  return res.json()
}

export async function uninstallSkill(name: string): Promise<InstallResponse> {
  const res = await fetch(`${BASE}/api/skills/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(data.detail || `卸载失败: ${res.status}`)
  }
  return res.json()
}

// --------------------------------------------------------------------------- //
// Agent.md API
// --------------------------------------------------------------------------- //

export async function getAgentMd(): Promise<string> {
  const res = await fetch(`${BASE}/api/agent-md`)
  if (!res.ok) throw new Error(`读取 agent.md 失败: ${res.status}`)
  const data = await res.json()
  return data.content
}

export async function updateAgentMd(content: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/api/agent-md`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(data.detail || `更新失败: ${res.status}`)
  }
  return res.json()
}
