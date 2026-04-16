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
  // Subagent nested content (populated via parent_tool_call_id)
  subText: string
  subTools: ToolCall[]
  subInterrupts: InterruptCard[]
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
        body: JSON.stringify({ session_id: sessionId, message: text, user_id: '307' }),
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
    const parentToolCallId = (data.parent_tool_call_id as string) ?? null

    setMessages(prev => {
      const copy = [...prev]
      const last = copy[copy.length - 1]
      if (!last || last.role !== 'assistant') return copy

      // Helper: update a tool's sub-content by parent_tool_call_id
      const updateToolSub = (
        tools: ToolCall[],
        parentId: string,
        updater: (tool: ToolCall) => ToolCall,
      ): ToolCall[] => tools.map(t => t.id === parentId ? updater(t) : t)

      // If event has parent_tool_call_id, route to the parent tool's nested content
      if (parentToolCallId) {
        switch (type) {
          case 'text': {
            const content = (d.content as string) ?? ''
            if (content) {
              const tools = updateToolSub(last.tools, parentToolCallId, t => ({
                ...t, subText: t.subText + content,
              }))
              copy[copy.length - 1] = { ...last, tools }
            }
            break
          }
          case 'tool_call_start': {
            const id = (d.tool_call_id as string) ?? ''
            const name = (d.tool_name as string) ?? 'unknown'
            const tools = updateToolSub(last.tools, parentToolCallId, t => ({
              ...t,
              subTools: [...t.subTools, { id, name, args: '', status: 'pending' as const, subText: '', subTools: [], subInterrupts: [] }],
            }))
            copy[copy.length - 1] = { ...last, tools }
            break
          }
          case 'tool_result': {
            const id = (d.tool_call_id as string) ?? ''
            const rawResult = d.result
            const result = typeof rawResult === 'object' ? JSON.stringify(rawResult, null, 2) : String(rawResult ?? '')
            const tools = updateToolSub(last.tools, parentToolCallId, t => ({
              ...t,
              subTools: t.subTools.map(st => st.id === id ? { ...st, result, status: 'done' as const } : st),
            }))
            copy[copy.length - 1] = { ...last, tools }
            break
          }
          case 'tool_call_args': {
            const id = (d.tool_call_id as string) ?? ''
            const chunk = (d.args_chunk as string) ?? ''
            const tools = updateToolSub(last.tools, parentToolCallId, t => ({
              ...t,
              subTools: t.subTools.map(st => st.id === id ? { ...st, args: st.args + chunk } : st),
            }))
            copy[copy.length - 1] = { ...last, tools }
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
            const tools = updateToolSub(last.tools, parentToolCallId, t => ({
              ...t, subInterrupts: [...t.subInterrupts, card],
            }))
            copy[copy.length - 1] = { ...last, tools }
            break
          }
          default:
            // Other event types with parent — ignore for now
            break
        }
        return copy
      }

      // Top-level events (no parent_tool_call_id)
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
          const tools = [...last.tools, { id, name, args: '', status: 'pending' as const, subText: '', subTools: [], subInterrupts: [] }]
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
          const msg = (d.message as string) ?? 'Unknown error'
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
        // 410 Gone = 服务重启，对话已失效，重置状态让用户重新输入
        if (resp.status === 410) {
          setStreaming(false)
        }
        alert(`回复失败: ${err.error ?? resp.statusText}`)
      }
    } catch (err) {
      // 网络错误（如服务不可达）也重置状态
      setStreaming(false)
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
                    <ToolBlock key={tool.id || j} tool={tool} onReplyInterrupt={replyToInterrupt} streaming={streaming} />
                  ))}
                  {msg.interrupts.map((card, j) => (
                    <InterruptBlock key={`int-${j}`} card={card} onReply={(reply) => replyToInterrupt(card.interruptKey, reply)} disabled={card.interruptKey ? false : streaming} />
                  ))}
                  {msg.text ? (
                    <div className="text-segment">
                      <RichText text={msg.text} />
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
// Spec Fence Parser: splits text into text/card parts
// --------------------------------------------------------------------------

interface TextPart { kind: 'text'; content: string }
interface SpecCardPart { kind: 'card'; type: string; props: Record<string, unknown> }
type RichPart = TextPart | SpecCardPart

function parseSpecFences(text: string): RichPart[] {
  const parts: RichPart[] = []
  const lines = text.split('\n')
  let inFence = false
  let textBuffer: string[] = []

  for (const line of lines) {
    const trimmed = line.trim()

    if (!inFence && trimmed === '```spec') {
      // Flush text buffer
      if (textBuffer.length > 0) {
        const content = textBuffer.join('\n').trim()
        if (content) parts.push({ kind: 'text', content })
        textBuffer = []
      }
      inFence = true
      continue
    }

    if (inFence && trimmed === '```') {
      inFence = false
      continue
    }

    if (inFence) {
      // Try parse as JSON card
      if (trimmed.startsWith('{')) {
        try {
          const obj = JSON.parse(trimmed)
          if (obj.type && obj.props) {
            parts.push({ kind: 'card', type: obj.type, props: obj.props })
            continue
          }
        } catch { /* not valid JSON, fall through */ }
      }
      // Non-JSON line inside fence — treat as text
      if (trimmed) textBuffer.push(line)
    } else {
      textBuffer.push(line)
    }
  }

  // Flush remaining text
  if (textBuffer.length > 0) {
    const content = textBuffer.join('\n').trim()
    if (content) parts.push({ kind: 'text', content })
  }

  return parts
}

// --------------------------------------------------------------------------
// RichText: renders text with embedded spec-fence cards
// --------------------------------------------------------------------------

function RichText({ text }: { text: string; cards?: Record<string, CardData> }) {
  const parts = parseSpecFences(text)

  // No spec fences — render as plain text
  if (parts.length === 1 && parts[0].kind === 'text') {
    return <>{text}</>
  }

  return (
    <>
      {parts.map((part, i) => {
        if (part.kind === 'text') {
          return <span key={i}>{part.content}</span>
        }
        return <SpecCard key={i} type={part.type} props={part.props} />
      })}
    </>
  )
}

// --------------------------------------------------------------------------
// SpecCard: renders a card based on type from ```spec fence
// --------------------------------------------------------------------------

function SpecCard({ type, props }: { type: string; props: Record<string, unknown> }) {
  switch (type) {
    case 'ShopCard':
      return <ShopCard {...props as any} />
    case 'ProjectCard':
      return <ProjectCard {...props as any} />
    case 'AppointmentCard':
      return <AppointmentCard {...props as any} />
    case 'CouponCard':
      return <CouponCard {...props as any} />
    default:
      return <GenericCard type={type} props={props} />
  }
}

function ShopCard({ name, price, rating, distance, address }: {
  name: string; price: number; rating: number; distance?: string; address?: string
}) {
  return (
    <div className="spec-card shop-card" data-card-type="ShopCard">
      <div className="spec-card-header">
        <span className="spec-card-icon">🏪</span>
        <span className="spec-card-title">{name}</span>
        {rating && <span className="spec-card-badge">⭐ {rating}</span>}
      </div>
      <div className="spec-card-body">
        <div className="spec-card-price">¥{price}</div>
        {distance && <div className="spec-card-meta">📍 {distance}</div>}
        {address && <div className="spec-card-meta">{address}</div>}
      </div>
    </div>
  )
}

function ProjectCard({ name, laborFee, partsFee, totalPrice, duration }: {
  name: string; laborFee: number; partsFee: number; totalPrice: number; duration?: string
}) {
  return (
    <div className="spec-card project-card" data-card-type="ProjectCard">
      <div className="spec-card-header">
        <span className="spec-card-icon">🔧</span>
        <span className="spec-card-title">{name}</span>
      </div>
      <div className="spec-card-body">
        <div className="spec-card-row"><span>工时费</span><span>¥{laborFee}</span></div>
        <div className="spec-card-row"><span>配件费</span><span>¥{partsFee}</span></div>
        <div className="spec-card-divider" />
        <div className="spec-card-row total"><span>合计</span><span>¥{totalPrice}</span></div>
        {duration && <div className="spec-card-meta">⏱ 预计 {duration}</div>}
      </div>
    </div>
  )
}

function AppointmentCard({ shopName, projectName, time, price, status }: {
  shopName: string; projectName: string; time: string; price: number; status: string
}) {
  const statusMap: Record<string, string> = {
    confirmed: '✅ 已确认', pending: '⏳ 待确认', cancelled: '❌ 已取消',
  }
  return (
    <div className="spec-card appointment-card" data-card-type="AppointmentCard">
      <div className="spec-card-header">
        <span className="spec-card-icon">📅</span>
        <span className="spec-card-title">预约 · {projectName}</span>
        <span className="spec-card-badge">{statusMap[status] ?? status}</span>
      </div>
      <div className="spec-card-body">
        <div className="spec-card-row"><span>门店</span><span>{shopName}</span></div>
        <div className="spec-card-row"><span>时间</span><span>{time}</span></div>
        <div className="spec-card-row"><span>价格</span><span>¥{price}</span></div>
      </div>
    </div>
  )
}

function CouponCard({ title, discount, minSpend, expireDate }: {
  title: string; discount: string; minSpend?: number; expireDate?: string
}) {
  return (
    <div className="spec-card coupon-card" data-card-type="CouponCard">
      <div className="spec-card-header">
        <span className="spec-card-icon">🎫</span>
        <span className="spec-card-title">{title}</span>
      </div>
      <div className="spec-card-body">
        <div className="spec-card-discount">{discount}</div>
        {minSpend && <div className="spec-card-meta">满 ¥{minSpend} 可用</div>}
        {expireDate && <div className="spec-card-meta">有效期至 {expireDate}</div>}
      </div>
    </div>
  )
}

function GenericCard({ type, props }: { type: string; props: Record<string, unknown> }) {
  return (
    <div className="spec-card generic-card" data-card-type={type}>
      <div className="spec-card-header">
        <span className="spec-card-icon">📊</span>
        <span className="spec-card-title">{type}</span>
      </div>
      <div className="spec-card-body">
        {Object.entries(props).map(([k, v]) => (
          <div key={k} className="spec-card-row">
            <span>{k}</span>
            <span>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
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
  // select_car fields
  const [carModelId, setCarModelId] = useState('')
  const [carModelName, setCarModelName] = useState('')
  // select_location fields
  const [address, setAddress] = useState('')
  const [lat, setLat] = useState('')
  const [lng, setLng] = useState('')

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

  const renderActions = () => {
    if (card.type === 'confirm') {
      return (
        <>
          <button className="btn-confirm" onClick={() => handleReply('确认')} disabled={disabled}>确认</button>
          <button className="btn-cancel" onClick={() => handleReply('取消')} disabled={disabled}>取消</button>
        </>
      )
    }

    if (card.type === 'select_car') {
      const canSubmit = carModelId.trim() && carModelName.trim()
      const handleSubmit = () => {
        if (!canSubmit) return
        handleReply(JSON.stringify({ car_model_id: carModelId.trim(), car_model_name: carModelName.trim() }))
      }
      return (
        <div className="interrupt-form">
          <div className="interrupt-form-field">
            <label>车型编码 (car_model_id)</label>
            <input placeholder="如 bmw-325li-2024" value={carModelId} onChange={e => setCarModelId(e.target.value)} disabled={disabled} />
          </div>
          <div className="interrupt-form-field">
            <label>车型名称 (car_model_name)</label>
            <input placeholder="如 2024款 宝马 325Li" value={carModelName} onChange={e => setCarModelName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && canSubmit) handleSubmit() }} disabled={disabled} />
          </div>
          <div className="interrupt-form-buttons">
            <button className="btn-confirm" onClick={handleSubmit} disabled={disabled || !canSubmit}>确认车型</button>
            <button className="btn-cancel" onClick={() => handleReply('取消')} disabled={disabled}>取消</button>
          </div>
        </div>
      )
    }

    if (card.type === 'select_location') {
      const canSubmit = address.trim() && lat.trim() && lng.trim()
      const handleSubmit = () => {
        if (!canSubmit) return
        handleReply(JSON.stringify({ address: address.trim(), lat: parseFloat(lat), lng: parseFloat(lng) }))
      }
      return (
        <div className="interrupt-form">
          <div className="interrupt-form-field">
            <label>地址</label>
            <input placeholder="如 上海市浦东新区张江高科" value={address} onChange={e => setAddress(e.target.value)} disabled={disabled} />
          </div>
          <div className="interrupt-form-field">
            <label>纬度 (lat)</label>
            <input type="number" step="any" placeholder="如 31.2304" value={lat} onChange={e => setLat(e.target.value)} disabled={disabled} />
          </div>
          <div className="interrupt-form-field">
            <label>经度 (lng)</label>
            <input type="number" step="any" placeholder="如 121.4737" value={lng} onChange={e => setLng(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && canSubmit) handleSubmit() }} disabled={disabled} />
          </div>
          <div className="interrupt-form-buttons">
            <button className="btn-confirm" onClick={handleSubmit} disabled={disabled || !canSubmit}>确认位置</button>
            <button className="btn-cancel" onClick={() => handleReply('取消')} disabled={disabled}>取消</button>
          </div>
        </div>
      )
    }

    // 默认：通用文本输入
    return (
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
          {renderActions()}
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------
// ToolBlock sub-component
// --------------------------------------------------------------------------

function ToolBlock({ tool, onReplyInterrupt, streaming }: {
  tool: ToolCall
  onReplyInterrupt?: (interruptKey: string | undefined, reply: string) => void
  streaming?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const hasSubContent = tool.subText || tool.subTools.length > 0 || tool.subInterrupts.length > 0

  let argsPreview = ''
  try {
    const parsed = JSON.parse(tool.args)
    argsPreview = Object.entries(parsed).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ').slice(0, 60)
  } catch {
    argsPreview = tool.args.slice(0, 60)
  }

  return (
    <div className={`tool-block ${expanded || hasSubContent ? 'expanded' : ''}`}>
      <div className="tool-header" onClick={() => setExpanded(!expanded)}>
        <span className="tool-icon">{hasSubContent ? '🤖' : '🔧'}</span>
        <span className="tool-name">{tool.name}</span>
        <span className="tool-args-preview">{argsPreview}</span>
        <span className={`tool-status ${tool.status}`}>
          {tool.status === 'pending' ? '⏳ 运行中' : tool.status === 'done' ? '✓ 完成' : '✗ 错误'}
        </span>
      </div>
      {/* Subagent nested content — always visible when present */}
      {hasSubContent && (
        <div className="tool-sub-content">
          {tool.subTools.map((st, j) => (
            <ToolBlock key={st.id || j} tool={st} onReplyInterrupt={onReplyInterrupt} streaming={streaming} />
          ))}
          {tool.subInterrupts.map((card, j) => (
            <InterruptBlock
              key={`sub-int-${j}`}
              card={card}
              onReply={(reply) => onReplyInterrupt?.(card.interruptKey, reply)}
              disabled={card.interruptKey ? false : !!streaming}
            />
          ))}
          {tool.subText && (
            <div className="tool-sub-text">{tool.subText}</div>
          )}
        </div>
      )}
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
