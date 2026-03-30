import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api/volguard': { target: 'http://localhost:8001', changeOrigin: true, rewrite: p => p.replace(/^\/api\/volguard/, '/api') },
      '/api/mf':       { target: 'http://localhost:8002', changeOrigin: true, rewrite: p => p.replace(/^\/api\/mf/, '/api') },
      '/api/equity':   { target: 'http://localhost:8003', changeOrigin: true, rewrite: p => p.replace(/^\/api\/equity/, '/api') },
      '/api/tax':      { target: 'http://localhost:8004', changeOrigin: true, rewrite: p => p.replace(/^\/api\/tax/, '/api') },
    },
  },
})
