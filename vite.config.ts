import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxy = {
  '/close': 'http://127.0.0.1:8000',
  '/ingest': 'http://127.0.0.1:8000',
  '/matches': 'http://127.0.0.1:8000',
  '/exceptions': 'http://127.0.0.1:8000',
  '/policies': 'http://127.0.0.1:8000',
  '/review': 'http://127.0.0.1:8000',
  '/eval': 'http://127.0.0.1:8000',
  '/commentary': 'http://127.0.0.1:8000',
  '/transactions': 'http://127.0.0.1:8000',
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy,
  },
  preview: {
    host: true,
    port: 5173,
    proxy,
  },
})
