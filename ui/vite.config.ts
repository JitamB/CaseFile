import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

// `fixtures/` lives at the repository root, not under ui/. §31 makes those
// golden objects the thing both tracks build against, so the screen reads the
// same file the Python tests do rather than a copy that could drift.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@fixtures': resolve(__dirname, '../fixtures') } },
  server: { fs: { allow: ['..'] } },
  test: {
    environment: 'jsdom',
    setupFiles: './src/__tests__/setup.ts',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
