import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: 'happy-dom',
      include: ['src/**/*.{test,spec}.{ts,tsx,mts}'],
      coverage: {
        provider: 'v8',
        reporter: ['text', 'json', 'html'],
        include: ['src/**/*.{ts,tsx,vue}'],
        exclude: [
          'src/**/*.{test,spec}.{ts,tsx,mts}',
          'src/**/__tests__/**',
          'src/main.ts',
        ],
      },
    },
  }),
)
