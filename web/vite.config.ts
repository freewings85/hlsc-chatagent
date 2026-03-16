import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 后端地址：VITE_PROXY_TARGET=http://127.0.0.1:8101 npx vite
const proxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8100'

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.VITE_PORT ?? 3100),
    watch: {
      usePolling: true,
    },
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/chat': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
})
