import { useCallback, useEffect, useRef, useState } from 'react'
import { listPrompts, getPrompt, updatePrompt, type PromptFileInfo } from '../api'
import './PromptsPage.css'

type MessageState = { type: 'success' | 'error'; text: string } | null

export default function PromptsPage() {
  const [files, setFiles] = useState<PromptFileInfo[]>([])
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [original, setOriginal] = useState('')
  const [loadingList, setLoadingList] = useState(true)
  const [loadingFile, setLoadingFile] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<MessageState>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const fetchList = useCallback(async () => {
    try {
      setLoadingList(true)
      const result = await listPrompts()
      // 过滤掉 README.md
      setFiles(result.filter(f => f.name !== 'README.md'))
    } catch (e) {
      setMessage({ type: 'error', text: `加载列表失败: ${(e as Error).message}` })
    } finally {
      setLoadingList(false)
    }
  }, [])

  useEffect(() => { fetchList() }, [fetchList])

  const handleSelect = async (path: string) => {
    if (path === selectedPath) return
    setSelectedPath(path)
    setMessage(null)
    setLoadingFile(true)
    try {
      const text = await getPrompt(path)
      setContent(text)
      setOriginal(text)
    } catch (e) {
      setMessage({ type: 'error', text: `读取失败: ${(e as Error).message}` })
      setContent('')
      setOriginal('')
    } finally {
      setLoadingFile(false)
    }
  }

  const handleSave = async () => {
    if (!selectedPath) return
    setSaving(true)
    setMessage(null)
    try {
      const res = await updatePrompt(selectedPath, content)
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
    <div className="prompts-page">
      <div className="prompts-file-list">
        <h3 className="file-list-title">提示词文件</h3>
        {loadingList ? (
          <div className="loading-small">加载中...</div>
        ) : files.length === 0 ? (
          <div className="empty-hint">暂无文件</div>
        ) : (
          <ul className="file-list">
            {files.map(f => (
              <li
                key={f.path}
                className={`file-item ${selectedPath === f.path ? 'active' : ''}`}
                onClick={() => handleSelect(f.path)}
              >
                <span className="file-icon">📄</span>
                <span className="file-name">{f.name}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="prompts-editor">
        {!selectedPath ? (
          <div className="editor-placeholder">
            <p>选择左侧文件进行编辑</p>
          </div>
        ) : loadingFile ? (
          <div className="loading"><div className="spinner" /><p>加载中...</p></div>
        ) : (
          <>
            <div className="editor-header">
              <h3>{selectedPath}</h3>
            </div>
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
      </div>
    </div>
  )
}
