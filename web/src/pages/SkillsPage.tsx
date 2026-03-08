import { useCallback, useEffect, useState } from 'react'
import { type SkillInfo, installSkill, listSkills, uninstallSkill } from '../api'
import './SkillsPage.css'

type MessageState = { type: 'success' | 'error'; text: string } | null

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [installUrl, setInstallUrl] = useState('')
  const [installing, setInstalling] = useState(false)
  const [message, setMessage] = useState<MessageState>(null)

  const fetchSkills = useCallback(async () => {
    try {
      setLoading(true)
      const data = await listSkills()
      setSkills(data)
    } catch (e) {
      setMessage({ type: 'error', text: `加载失败: ${(e as Error).message}` })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchSkills() }, [fetchSkills])

  const handleInstall = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!installUrl.trim()) return
    setInstalling(true)
    setMessage(null)
    try {
      const res = await installSkill(installUrl.trim())
      setMessage({ type: 'success', text: res.message })
      setInstallUrl('')
      await fetchSkills()
    } catch (err) {
      setMessage({ type: 'error', text: (err as Error).message })
    } finally {
      setInstalling(false)
    }
  }

  const handleUninstall = async (name: string) => {
    if (!confirm(`确定要卸载 "${name}" 吗？`)) return
    setMessage(null)
    try {
      const res = await uninstallSkill(name)
      setMessage({ type: 'success', text: res.message })
      await fetchSkills()
    } catch (err) {
      setMessage({ type: 'error', text: (err as Error).message })
    }
  }

  const badgeClass = (source: string) => {
    if (source === 'bundled') return 'skill-badge badge-bundled'
    return 'skill-badge badge-project'
  }

  return (
    <>
      <div className="install-section">
        <h2>安装 Skill</h2>
        <form className="install-form" onSubmit={handleInstall}>
          <input
            className="install-input"
            type="text"
            value={installUrl}
            onChange={e => setInstallUrl(e.target.value)}
            placeholder="GitHub URL 或 SKILL.md 直链"
            disabled={installing}
          />
          <button className="btn btn-primary" type="submit" disabled={installing || !installUrl.trim()}>
            {installing ? '安装中...' : '安装'}
          </button>
        </form>
        {message && <div className={`msg ${message.type}`}>{message.text}</div>}
      </div>

      <div className="skill-list-section">
        <h2>已安装 Skills <span className="skill-count">({skills.length})</span></h2>

        {loading ? (
          <div className="loading"><div className="spinner" /><p>加载中...</p></div>
        ) : skills.length === 0 ? (
          <div className="empty">暂无已安装的 skill</div>
        ) : (
          <div className="skill-list">
            {skills.map(skill => (
              <div key={skill.name} className="skill-card">
                <div className="skill-info">
                  <div className="skill-header-row">
                    <span className="skill-name">{skill.name}</span>
                    <span className={badgeClass(skill.source)}>{skill.source}</span>
                  </div>
                  <div className="skill-description">{skill.description}</div>
                  {skill.when_to_use && <div className="skill-when">{skill.when_to_use}</div>}
                </div>
                <div className="skill-actions">
                  {skill.source === 'project' && (
                    <button className="btn btn-danger" onClick={() => handleUninstall(skill.name)}>卸载</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="help-box">
        <h3>支持的安装地址</h3>
        <ul>
          <li>GitHub 目录: <code>https://github.com/owner/repo/tree/branch/skills/name</code></li>
          <li>GitHub 文件: <code>https://github.com/owner/repo/blob/branch/.../SKILL.md</code></li>
          <li>Raw 直链: <code>https://raw.githubusercontent.com/.../SKILL.md</code></li>
        </ul>
      </div>
    </>
  )
}
