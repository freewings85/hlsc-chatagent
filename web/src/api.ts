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

export async function uploadSkill(file: File): Promise<InstallResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/api/skills/upload`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(data.detail || `上传失败: ${res.status}`)
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
// Prompts API
// --------------------------------------------------------------------------- //

export interface PromptFileInfo {
  name: string
  path: string
  size: number
}

export async function listPrompts(): Promise<PromptFileInfo[]> {
  const res = await fetch(`${BASE}/api/prompts`)
  if (!res.ok) throw new Error(`加载提示词列表失败: ${res.status}`)
  const data = await res.json()
  return data.files
}

export async function getPrompt(path: string): Promise<string> {
  const res = await fetch(`${BASE}/api/prompts/${encodeURIComponent(path)}`)
  if (!res.ok) throw new Error(`读取失败: ${res.status}`)
  const data = await res.json()
  return data.content
}

export async function updatePrompt(path: string, content: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/api/prompts/${encodeURIComponent(path)}`, {
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

// --------------------------------------------------------------------------- //
// MCP API
// --------------------------------------------------------------------------- //

export interface McpServerInfo {
  name: string
  url: string
  headers: Record<string, string>
}

export interface McpToolInfo {
  name: string
  description: string | null
}

export interface ProbeResponse {
  success: boolean
  tools: McpToolInfo[]
  error: string
}

export interface McpResponse {
  success: boolean
  message: string
}

export async function listMcpServers(): Promise<McpServerInfo[]> {
  const res = await fetch(`${BASE}/api/mcp/servers`)
  if (!res.ok) throw new Error(`加载 MCP 服务器列表失败: ${res.status}`)
  return res.json()
}

export async function addMcpServer(name: string, url: string, headers: Record<string, string> = {}): Promise<McpResponse> {
  const res = await fetch(`${BASE}/api/mcp/servers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, url, headers }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(data.detail || `添加失败: ${res.status}`)
  }
  return res.json()
}

export async function removeMcpServer(name: string): Promise<McpResponse> {
  const res = await fetch(`${BASE}/api/mcp/servers/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(data.detail || `移除失败: ${res.status}`)
  }
  return res.json()
}

export async function probeMcpServer(name: string): Promise<ProbeResponse> {
  const res = await fetch(`${BASE}/api/mcp/servers/${encodeURIComponent(name)}/probe`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`探测失败: ${res.status}`)
  return res.json()
}

export async function probeMcpUrl(url: string): Promise<ProbeResponse> {
  const res = await fetch(`${BASE}/api/mcp/probe-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: '', url }),
  })
  if (!res.ok) throw new Error(`探测失败: ${res.status}`)
  return res.json()
}

// --------------------------------------------------------------------------- //
// Agent.md API
// --------------------------------------------------------------------------- //

export async function getAgentMd(): Promise<string> {
  const res = await fetch(`${BASE}/api/agent-md`)
  if (!res.ok) throw new Error(`加载 agent.md 失败: ${res.status}`)
  const data: { content: string } = await res.json()
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
