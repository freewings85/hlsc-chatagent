import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Chat 后端地址：VITE_PROXY_TARGET=http://127.0.0.1:7100 npx vite
const chatProxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8100'
// 其它 API 默认仍回到 MainAgent(8100)
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8100'

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.VITE_PORT ?? 3100),
    watch: {
      usePolling: true,
    },
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      '/chat': {
        target: chatProxyTarget,
        changeOrigin: true,
      },
    },
  },
})
