import { useCallback, useEffect, useRef, useState } from 'react'
import './ChatPage.css'

const BASE = import.meta.env.VITE_API_BASE ?? ''

// --------------------------------------------------------------------------
// Types
// --------------------------------------------------------------------------

interface ToolCall {
  id: string
  name: string
  args: string
  result?: string
  status: 'pending' | 'done' | 'error'
}

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  tools: ToolCall[]
}

// --------------------------------------------------------------------------
// SSE parser
// --------------------------------------------------------------------------

interface SseEvent {
  type: string
  data: Record<string, unknown>
}

function parseSseChunk(raw: string): SseEvent[] {
  const events: SseEvent[] = []
  for (const block of raw.split('\n\n')) {
    if (!block.trim()) continue
    let type = 'message'
    let data = ''
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) type = line.slice(7).trim()
      else if (line.startsWith('data: ')) data = line.slice(6).trim()
    }
    if (data) {
      try {
        events.push({ type, data: JSON.parse(data) })
      } catch { /* skip */ }
    }
  }
  return events
}

// --------------------------------------------------------------------------
// Component
// --------------------------------------------------------------------------

export default function ChatPage() {
  const [sessionId, setSessionId] = useState(() => 'sess-' + Math.random().toString(36).slice(2, 10))
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const chatAreaRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  // Refs for streaming updates (avoid stale closures)
  const messagesRef = useRef(messages)
  messagesRef.current = messages

  const scrollToBottom = useCallback(() => {
    const el = chatAreaRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  useEffect(scrollToBottom, [messages, scrollToBottom])

  const newSession = () => {
    if (streaming) return
    setSessionId('sess-' + Math.random().toString(36).slice(2, 10))
    setMessages([])
  }

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    setStreaming(true)

    // Add user message + empty assistant placeholder
    const userMsg: ChatMessage = { role: 'user', text, tools: [] }
    const asstMsg: ChatMessage = { role: 'assistant', text: '', tools: [] }
    setMessages(prev => [...prev, userMsg, asstMsg])

    let buffer = ''

    try {
      const resp = await fetch(`${BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text, user_id: 'test-user' }),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const idx = buffer.lastIndexOf('\n\n')
        if (idx === -1) continue
        const toProcess = buffer.slice(0, idx + 2)
        buffer = buffer.slice(idx + 2)

        for (const { type, data } of parseSseChunk(toProcess)) {
          handleEvent(type, data)
        }
      }
    } catch (err) {
      // Append error to assistant text
      setMessages(prev => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last?.role === 'assistant') {
          copy[copy.length - 1] = { ...last, text: last.text + `\n[Error: ${(err as Error).message}]` }
        }
        return copy
      })
    } finally {
      setStreaming(false)
    }
  }

  const handleEvent = (type: string, data: Record<string, unknown>) => {
    const d = (data.data ?? data) as Record<string, unknown>

    setMessages(prev => {
      const copy = [...prev]
      const last = copy[copy.length - 1]
      if (!last || last.role !== 'assistant') return copy

      switch (type) {
        case 'text': {
          const content = (d.content as string) ?? ''
          if (content) copy[copy.length - 1] = { ...last, text: last.text + content }
          break
        }
        case 'tool_call_start': {
          const id = (d.tool_call_id as string) ?? ''
          const name = (d.tool_name as string) ?? 'unknown'
          const tools = [...last.tools, { id, name, args: '', status: 'pending' as const }]
          copy[copy.length - 1] = { ...last, tools }
          break
        }
        case 'tool_call_args': {
          const id = (d.tool_call_id as string) ?? ''
          const chunk = (d.args_chunk as string) ?? ''
          const tools = last.tools.map(t => t.id === id ? { ...t, args: t.args + chunk } : t)
          copy[copy.length - 1] = { ...last, tools }
          break
        }
        case 'tool_result': {
          const id = (d.tool_call_id as string) ?? ''
          const result = (d.result as string) ?? ''
          const tools = last.tools.map(t => t.id === id ? { ...t, result, status: 'done' as const } : t)
          copy[copy.length - 1] = { ...last, tools }
          break
        }
        case 'error': {
          const msg = (d.error as string) ?? 'Unknown error'
          copy[copy.length - 1] = { ...last, text: last.text + `\n[Error: ${msg}]` }
          break
        }
      }
      return copy
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="chat-page">
      <div className="chat-header">
        <div className="session-bar">
          <div className={`status-dot ${streaming ? 'live' : ''}`} />
          <span className="session-label">session:</span>
          <span className="session-id">{sessionId}</span>
          <button className="btn-sm" onClick={newSession} disabled={streaming}>新会话</button>
        </div>
      </div>

      <div className="chat-area" ref={chatAreaRef}>
        {messages.length === 0 && (
          <div className="empty-hint">
            发送消息开始对话<br />
            可以让 Agent 使用工具：
            <code>read</code> <code>write</code> <code>edit</code> <code>glob</code> <code>grep</code> <code>bash</code>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="avatar">{msg.role === 'user' ? '👤' : '🤖'}</div>
            <div className="message-content">
              {msg.role === 'user' ? (
                <div className="user-bubble">{msg.text}</div>
              ) : (
                <>
                  {msg.tools.map((tool, j) => (
                    <ToolBlock key={tool.id || j} tool={tool} />
                  ))}
                  {msg.text ? (
                    <div className="text-segment">{msg.text}</div>
                  ) : (
                    streaming && i === messages.length - 1 && msg.tools.length === 0 && (
                      <div className="typing"><span /><span /><span /></div>
                    )
                  )}
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="chat-footer">
        <textarea
          ref={inputRef}
          className="chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息（Enter 发送，Shift+Enter 换行）..."
          rows={1}
          disabled={streaming}
        />
        <button className="btn-send" onClick={sendMessage} disabled={streaming || !input.trim()}>
          发送 ↑
        </button>
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------
// ToolBlock sub-component
// --------------------------------------------------------------------------

function ToolBlock({ tool }: { tool: ToolCall }) {
  const [expanded, setExpanded] = useState(false)

  let argsPreview = ''
  try {
    const parsed = JSON.parse(tool.args)
    argsPreview = Object.entries(parsed).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ').slice(0, 60)
  } catch {
    argsPreview = tool.args.slice(0, 60)
  }

  return (
    <div className={`tool-block ${expanded ? 'expanded' : ''}`}>
      <div className="tool-header" onClick={() => setExpanded(!expanded)}>
        <span className="tool-icon">🔧</span>
        <span className="tool-name">{tool.name}</span>
        <span className="tool-args-preview">{argsPreview}</span>
        <span className={`tool-status ${tool.status}`}>
          {tool.status === 'pending' ? '⏳ 运行中' : tool.status === 'done' ? '✓ 完成' : '✗ 错误'}
        </span>
      </div>
      {expanded && (
        <div className="tool-details">
          <div className="tool-section">
            <div className="tool-section-label">ARGS</div>
            <div className="tool-code">{tool.args}</div>
          </div>
          {tool.result != null && (
            <div className="tool-section tool-result-section">
              <div className="tool-section-label">RESULT</div>
              <div className="tool-code">{tool.result}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
