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

interface InterruptCard {
  type: string
  data: Record<string, unknown>
  interruptKey?: string
  question?: string
}

interface CardData {
  tool_call_id: string
  detail_type: string
  data: { success: boolean; data: Record<string, unknown> }
}

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  tools: ToolCall[]
  interrupts: InterruptCard[]
  cards: Record<string, CardData>
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

const STORAGE_KEY_SID = 'chat_session_id'
const STORAGE_KEY_MSG = 'chat_messages'

function loadSessionId(): string {
  return sessionStorage.getItem(STORAGE_KEY_SID) || 'sess-' + Math.random().toString(36).slice(2, 10)
}

function loadMessages(): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY_MSG)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

export default function ChatPage() {
  const [sessionId, setSessionId] = useState(loadSessionId)
  const [messages, setMessages] = useState<ChatMessage[]>(loadMessages)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const taskIdRef = useRef<string | null>(null)
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

  // 持久化 sessionId 和 messages 到 sessionStorage
  useEffect(() => { sessionStorage.setItem(STORAGE_KEY_SID, sessionId) }, [sessionId])
  useEffect(() => { sessionStorage.setItem(STORAGE_KEY_MSG, JSON.stringify(messages)) }, [messages])

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
    const userMsg: ChatMessage = { role: 'user', text, tools: [], interrupts: [], cards: {} }
    const asstMsg: ChatMessage = { role: 'assistant', text: '', tools: [], interrupts: [], cards: {} }
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

      let streamEnded = false
      while (!streamEnded) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const idx = buffer.lastIndexOf('\n\n')
        if (idx === -1) continue
        const toProcess = buffer.slice(0, idx + 2)
        buffer = buffer.slice(idx + 2)

        for (const { type, data } of parseSseChunk(toProcess)) {
          if (type === 'chat_request_end') {
            streamEnded = true
            break
          }
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
        case 'chat_request_start': {
          taskIdRef.current = (d.task_id as string) ?? null
          return copy
        }
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
          const rawResult = d.result
          const result = typeof rawResult === 'object' ? JSON.stringify(rawResult, null, 2) : String(rawResult ?? '')
          const tools = last.tools.map(t => t.id === id ? { ...t, result, status: 'done' as const } : t)
          copy[copy.length - 1] = { ...last, tools }
          break
        }
        case 'tool_result_detail': {
          const toolCallId = (d.tool_call_id as string) ?? ''
          if (toolCallId) {
            const cardData: CardData = {
              tool_call_id: toolCallId,
              detail_type: (d.detail_type as string) ?? 'unknown',
              data: (d.data as CardData['data']) ?? { success: false, data: {} },
            }
            const cards = { ...last.cards, [toolCallId]: cardData }
            copy[copy.length - 1] = { ...last, cards }
          }
          break
        }
        case 'interrupt': {
          const cardType = (d.type as string) ?? 'unknown'
          const card: InterruptCard = {
            type: cardType,
            data: d,
            interruptKey: (d.interrupt_key as string) ?? undefined,
            question: (d.question as string) ?? undefined,
          }
          const interrupts = [...last.interrupts, card]
          copy[copy.length - 1] = { ...last, interrupts }
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

  const stopTask = async () => {
    const taskId = taskIdRef.current
    if (!taskId) return
    try {
      await fetch(`${BASE}/chat/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId }),
      })
    } catch { /* ignore */ }
  }

  const replyToInterrupt = async (interruptKey: string | undefined, reply: string) => {
    if (!interruptKey) {
      // Fallback: 无 interrupt_key（fire-and-forget 模式），用旧方式发消息
      if (streaming) return
      setInput(reply)
      setTimeout(() => {
        const btn = document.querySelector('.btn-send') as HTMLButtonElement | null
        if (btn && !btn.disabled) btn.click()
      }, 50)
      return
    }

    // 通过 API 回复 interrupt
    try {
      const resp = await fetch(`${BASE}/chat/interrupt-reply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interrupt_key: interruptKey, reply }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }))
        alert(`回复失败: ${err.error ?? resp.statusText}`)
      }
    } catch (err) {
      alert(`回复失败: ${(err as Error).message}`)
    }
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
                  {msg.interrupts.map((card, j) => (
                    <InterruptBlock key={`int-${j}`} card={card} onReply={(reply) => replyToInterrupt(card.interruptKey, reply)} disabled={card.interruptKey ? false : streaming} />
                  ))}
                  {msg.text ? (
                    <div className="text-segment">
                      <RichText text={msg.text} cards={msg.cards} />
                    </div>
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
          id="input-box"
          ref={inputRef}
          className="chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息（Enter 发送，Shift+Enter 换行）..."
          rows={1}
          disabled={streaming}
        />
        {streaming ? (
          <button className="btn-stop" onClick={stopTask}>停止 ■</button>
        ) : (
          <button id="send-btn" className="btn-send" onClick={sendMessage} disabled={!input.trim()}>
            发送 ↑
          </button>
        )}
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------
// RichText: splits text on {{card:xxx}} and renders card components inline
// --------------------------------------------------------------------------

function RichText({ text, cards }: { text: string; cards: Record<string, CardData> }) {
  // Split by {{card:toolCallId}} pattern
  const parts = text.split(/\{\{card:([^}]+)\}\}/)
  // parts: [text, toolCallId, text, toolCallId, ...]

  if (parts.length === 1) return <>{text}</>

  // 按 tool_call_id 精确查找，找不到时按 detail_type fallback
  const findCard = (ref: string): CardData | undefined => {
    if (cards[ref]) return cards[ref]
    return Object.values(cards).find(c => c.detail_type === ref)
  }

  return (
    <>
      {parts.map((part, i) => {
        if (i % 2 === 0) {
          // Text segment
          return part ? <span key={i}>{part}</span> : null
        }
        // Card reference — part is toolCallId or detail_type
        const card = findCard(part)
        if (!card) return <span key={i}>{`{{card:${part}}}`}</span>
        return <CardComponent key={i} card={card} />
      })}
    </>
  )
}

// --------------------------------------------------------------------------
// CardComponent: renders a card block based on detail_type
// --------------------------------------------------------------------------

function CardComponent({ card }: { card: CardData }) {
  const data = card.data?.data ?? {}

  return (
    <div className="card-block" data-card-type={card.detail_type}>
      <div className="card-header">
        <span className="card-icon">📊</span>
        <span className="card-type">{card.detail_type}</span>
      </div>
      <div className="card-body">
        {Object.entries(data).map(([k, v]) => (
          <div key={k} className="card-field">
            <span className="card-label">{k}:</span>
            <span className="card-value">
              {typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------
// InterruptBlock sub-component
// --------------------------------------------------------------------------

function InterruptBlock({ card, onReply, disabled }: {
  card: InterruptCard
  onReply: (reply: string) => void
  disabled: boolean
}) {
  const [replyText, setReplyText] = useState('')
  const [replied, setReplied] = useState(false)

  const handleReply = (text: string) => {
    onReply(text)
    setReplied(true)
  }

  const renderData = () => {
    const skipKeys = new Set(['type', 'question', 'interrupt_id', 'interrupt_key'])
    const entries = Object.entries(card.data).filter(([k]) => !skipKeys.has(k))
    if (entries.length === 0) return null
    return (
      <div className="interrupt-data">
        {entries.map(([k, v]) => (
          <div key={k} className="interrupt-field">
            <span className="interrupt-label">{k}:</span>
            <span className="interrupt-value">{typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)}</span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="interrupt-block" data-interrupt-type={card.type} data-interrupt-key={card.interruptKey}>
      <div className="interrupt-header">
        <span className="interrupt-icon">{card.interruptKey ? '⏸️' : '📋'}</span>
        <span className="interrupt-type">{card.type}</span>
        {replied && <span className="interrupt-replied">已回复</span>}
      </div>
      {card.question && <div className="interrupt-question">{card.question}</div>}
      {renderData()}
      {!replied && (
        <div className="interrupt-actions">
          {card.type === 'confirm' ? (
            <>
              <button className="btn-confirm" onClick={() => handleReply('确认')} disabled={disabled}>确认</button>
              <button className="btn-cancel" onClick={() => handleReply('取消')} disabled={disabled}>取消</button>
            </>
          ) : (
            <>
              <input
                className="interrupt-input"
                placeholder="输入回复..."
                value={replyText}
                onChange={e => setReplyText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && replyText.trim()) handleReply(replyText.trim()) }}
                disabled={disabled}
              />
              <button className="btn-confirm" onClick={() => handleReply(replyText.trim() || '确认')} disabled={disabled}>发送</button>
            </>
          )}
        </div>
      )}
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
