import { NavLink, Outlet } from 'react-router-dom'
import './SettingsPage.css'

export default function SettingsPage() {
  return (
    <div className="settings-page">
      <div className="settings-sidebar">
        <h2 className="settings-title">设置</h2>
        <nav className="settings-nav">
          <NavLink to="/settings/skills" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">⚡</span>
            Skills
          </NavLink>
          <NavLink to="/settings/mcp" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">🔌</span>
            MCP
          </NavLink>
        </nav>
      </div>
      <div className="settings-content">
        <Outlet />
      </div>
    </div>
  )
}
