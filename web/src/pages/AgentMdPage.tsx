import { useCallback, useEffect, useRef, useState } from 'react'
import { getAgentMd, updateAgentMd } from '../api'
import './AgentMdPage.css'

type MessageState = { type: 'success' | 'error'; text: string } | null

export default function AgentMdPage() {
  const [content, setContent] = useState('')
  const [original, setOriginal] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<MessageState>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const fetchContent = useCallback(async () => {
    try {
      setLoading(true)
      const md = await getAgentMd()
      setContent(md)
      setOriginal(md)
    } catch (e) {
      setMessage({ type: 'error', text: `加载失败: ${(e as Error).message}` })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchContent() }, [fetchContent])

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const res = await updateAgentMd(content)
      setMessage({ type: 'success', text: res.message })
      setOriginal(content)
    } catch (err) {
      setMessage({ type: 'error', text: (err as Error).message })
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => {
    setContent(original)
    setMessage(null)
  }

  const hasChanges = content !== original

  return (
    <>
      <div className="agent-md-header">
        <h2>Agent.md</h2>
        <p className="agent-md-desc">
          系统级提示词配置，所有会话共享。修改后立即生效。
        </p>
      </div>

      {loading ? (
        <div className="loading"><div className="spinner" /><p>加载中...</p></div>
      ) : (
        <>
          <div className="editor-section">
            <textarea
              ref={textareaRef}
              className="md-editor"
              value={content}
              onChange={e => setContent(e.target.value)}
              spellCheck={false}
            />
          </div>

          <div className="editor-actions">
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={saving || !hasChanges}
            >
              {saving ? '保存中...' : '保存'}
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleReset}
              disabled={!hasChanges}
            >
              撤销修改
            </button>
            {message && <span className={`msg ${message.type}`}>{message.text}</span>}
          </div>
        </>
      )}
    </>
  )
}
