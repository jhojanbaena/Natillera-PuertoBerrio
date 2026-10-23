import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  let apiOrigin = ''
  if (command === 'build') {
    const api = new URL(env.VITE_API_URL || 'https://invalid.local')
    if (!env.VITE_API_URL || api.protocol !== 'https:' || api.username || api.password || api.pathname !== '/api/v1' || api.search || api.hash) {
      throw new Error('Configura VITE_API_URL=https://TU-BACKEND.vercel.app/api/v1 antes de compilar')
    }
    apiOrigin = api.origin
  }
  return {
    plugins: [react(), {
      name: 'security-headers',
      writeBundle(options) {
        const headers = readFileSync(resolve('public/_headers'), 'utf8')
        writeFileSync(resolve(options.dir, '_headers'), headers.replace("connect-src 'self' https:", `connect-src 'self' ${apiOrigin}`))
      },
    }],
    server: {
      port: 5173,
      proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
    },
  }
})
