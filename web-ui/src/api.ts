export interface SkillInfo {
  name: string
  description: string
  source: string // "bundled" | "project" | "user"
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
