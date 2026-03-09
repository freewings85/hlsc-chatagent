import { useCallback, useEffect, useState } from 'react'
import {
  type McpServerInfo,
  type McpToolInfo,
  addMcpServer,
  listMcpServers,
  probeMcpServer,
  removeMcpServer,
} from '../api'
import './McpPage.css'

type MessageState = { type: 'success' | 'error'; text: string } | null

export default function McpPage() {
  const [servers, setServers] = useState<McpServerInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [serverName, setServerName] = useState('')
  const [serverUrl, setServerUrl] = useState('')
  const [adding, setAdding] = useState(false)
  const [message, setMessage] = useState<MessageState>(null)
  // server name → tools (from probe)
  const [serverTools, setServerTools] = useState<Record<string, McpToolInfo[]>>({})
  const [probing, setProbing] = useState<string | null>(null)
  // 当前展开描述的工具: "serverName:toolName"
  const [activeTool, setActiveTool] = useState<string | null>(null)

  const fetchServers = useCallback(async () => {
    try {
      setLoading(true)
      const data = await listMcpServers()
      setServers(data)
    } catch (e) {
      setMessage({ type: 'error', text: `加载失败: ${(e as Error).message}` })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchServers() }, [fetchServers])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!serverName.trim() || !serverUrl.trim()) return
    setAdding(true)
    setMessage(null)
    try {
      const res = await addMcpServer(serverName.trim(), serverUrl.trim())
      setMessage({ type: 'success', text: res.message })
      setServerName('')
      setServerUrl('')
      await fetchServers()
    } catch (err) {
      setMessage({ type: 'error', text: (err as Error).message })
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (name: string) => {
    if (!confirm(`确定要移除 "${name}" 吗？`)) return
    setMessage(null)
    try {
      const res = await removeMcpServer(name)
      setMessage({ type: 'success', text: res.message })
      setServerTools(prev => { const n = { ...prev }; delete n[name]; return n })
      await fetchServers()
    } catch (err) {
      setMessage({ type: 'error', text: (err as Error).message })
    }
  }

  const handleProbe = async (name: string) => {
    setProbing(name)
    setMessage(null)
    try {
      const res = await probeMcpServer(name)
      if (res.success) {
        setServerTools(prev => ({ ...prev, [name]: res.tools }))
        setMessage({ type: 'success', text: `探测成功：${res.tools.length} 个工具` })
      } else {
        setMessage({ type: 'error', text: `探测失败: ${res.error}` })
      }
    } catch (err) {
      setMessage({ type: 'error', text: (err as Error).message })
    } finally {
      setProbing(null)
    }
  }

  return (
    <>
      <div className="install-section">
        <h2>添加 MCP 服务器</h2>
        <form className="mcp-add-form" onSubmit={handleAdd}>
          <input
            id="mcp-name"
            className="install-input"
            type="text"
            value={serverName}
            onChange={e => setServerName(e.target.value)}
            placeholder="服务器名称（如 weather）"
            disabled={adding}
          />
          <input
            id="mcp-url"
            className="install-input mcp-url-input"
            type="text"
            value={serverUrl}
            onChange={e => setServerUrl(e.target.value)}
            placeholder="Streamable HTTP URL（如 http://localhost:8199/mcp）"
            disabled={adding}
          />
          <button
            id="mcp-add-btn"
            className="btn btn-primary"
            type="submit"
            disabled={adding || !serverName.trim() || !serverUrl.trim()}
          >
            {adding ? '添加中...' : '添加'}
          </button>
        </form>
        {message && <div className={`msg ${message.type}`}>{message.text}</div>}
      </div>

      <div className="skill-list-section">
        <h2>已配置 MCP 服务器 <span className="skill-count">({servers.length})</span></h2>

        {loading ? (
          <div className="loading"><div className="spinner" /><p>加载中...</p></div>
        ) : servers.length === 0 ? (
          <div className="empty">暂无已配置的 MCP 服务器</div>
        ) : (
          <div className="skill-list">
            {servers.map(server => (
              <div key={server.name} className="skill-card" data-server-name={server.name}>
                <div className="skill-info">
                  <div className="skill-header-row">
                    <span className="skill-name">{server.name}</span>
                    <span className="skill-badge badge-project">HTTP</span>
                  </div>
                  <div className="skill-description mcp-url-display">{server.url}</div>
                  {serverTools[server.name] && (
                    <>
                      <div className="mcp-tools-list">
                        <span className="mcp-tools-label">工具：</span>
                        {serverTools[server.name].map(t => {
                          const key = `${server.name}:${t.name}`
                          return (
                            <span
                              key={t.name}
                              className={`mcp-tool-chip ${activeTool === key ? 'active' : ''}`}
                              onClick={() => setActiveTool(activeTool === key ? null : key)}
                            >
                              {t.name}
                            </span>
                          )
                        })}
                      </div>
                      {activeTool?.startsWith(`${server.name}:`) && (() => {
                        const toolName = activeTool.split(':').slice(1).join(':')
                        const tool = serverTools[server.name].find(t => t.name === toolName)
                        if (!tool) return null
                        return (
                          <div className="mcp-tool-detail">
                            <div className="mcp-tool-detail-name">{tool.name}</div>
                            <div className="mcp-tool-detail-desc">
                              {tool.description || '暂无描述'}
                            </div>
                          </div>
                        )
                      })()}
                    </>
                  )}
                </div>
                <div className="skill-actions">
                  <button
                    className="btn btn-secondary mcp-probe-btn"
                    onClick={() => handleProbe(server.name)}
                    disabled={probing === server.name}
                  >
                    {probing === server.name ? '探测中...' : '探测'}
                  </button>
                  <button className="btn btn-danger" onClick={() => handleRemove(server.name)}>移除</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="help-box">
        <h3>使用说明</h3>
        <ul>
          <li>添加 MCP 服务器后，<strong>下一次对话</strong>会自动加载该服务器的工具</li>
          <li>点击"探测"可查看服务器提供的工具列表</li>
          <li>仅支持 Streamable HTTP transport（URL 格式如 <code>http://host:port/mcp</code>）</li>
          <li>移除服务器后，下一次对话不再使用该服务器的工具</li>
        </ul>
      </div>
    </>
  )
}
