import { defineConfig } from 'vite';
import { resolve } from 'path';

const BACKEND = 'https://localhost:443';

export default defineConfig({
  envDir: resolve(__dirname, '../setting'),

  root: resolve(__dirname, 'src'),

  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api':      { target: BACKEND, secure: false, changeOrigin: true },
      '/uploads':  { target: BACKEND, secure: false, changeOrigin: true },
      '/resource': { target: BACKEND, secure: false, changeOrigin: true },
    },
  },

  build: {
    outDir: resolve(__dirname, 'dist'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'src/html/index.html'),
        map:  resolve(__dirname, 'src/html/map.html'),
      },
    },
  },
});