import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy API + WebSocket traffic to the FastAPI backend on :8000 during dev.
// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
