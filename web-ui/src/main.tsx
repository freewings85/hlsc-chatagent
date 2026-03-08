import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './index.css'
import App from './App'
import ChatPage from './pages/ChatPage'
import McpPage from './pages/McpPage'
import SettingsPage from './pages/SettingsPage'
import SkillsPage from './pages/SkillsPage'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<ChatPage />} />
          <Route path="settings" element={<SettingsPage />}>
            <Route index element={<Navigate to="skills" replace />} />
            <Route path="skills" element={<SkillsPage />} />
            <Route path="mcp" element={<McpPage />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
