import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite-plus'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@clerk/react': '/tmp/opencode/hd-harness/clerk.tsx',
    },
  },
  server: { port: 5183, strictPort: true },
})
