import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// dev 서버는 API(8000)와 Chat(8001)을 같은 오리진으로 proxy한다.
// 이렇게 해야 세션 쿠키가 브라우저에서 한 오리진으로 묶여 CORS·SameSite 문제를 피한다.
const API_TARGET = process.env.VITE_DEV_API_TARGET ?? 'http://127.0.0.1:8000'
const CHAT_TARGET = process.env.VITE_DEV_CHAT_TARGET ?? 'http://127.0.0.1:8001'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': new URL('./src', import.meta.url).pathname },
  },
  server: {
    port: 5173,
    proxy: {
      // SSE 응답이 끊기지 않도록 두 proxy 모두 버퍼링 없이 통과시킨다.
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (requestPath) => requestPath.replace(/^\/api/, ''),
      },
      '/chat': {
        target: CHAT_TARGET,
        changeOrigin: true,
      },
    },
  },
})
