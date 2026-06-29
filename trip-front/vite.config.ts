import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

const API_TARGET = process.env.VITE_API_TARGET || 'http://localhost:3000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
})
