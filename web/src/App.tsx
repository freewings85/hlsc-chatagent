import { Link, Outlet, useLocation } from 'react-router-dom'
import './App.css'

export default function App() {
  const location = useLocation()
  const isSettings = location.pathname.startsWith('/settings')

  return (
    <div className="app-layout">
      <header className="app-header">
        <Link to="/" className="app-logo">
          <span className="logo-icon">🤖</span>
          <span className="logo-text">ChatAgent</span>
        </Link>
        <nav className="app-nav">
          <Link to="/" className={`app-nav-item ${!isSettings ? 'active' : ''}`}>
            💬 会话
          </Link>
          <Link to="/settings/skills" className={`app-nav-item ${isSettings ? 'active' : ''}`}>
            ⚙️ 设置
          </Link>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
