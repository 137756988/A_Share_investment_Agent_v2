import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // 代理API请求到本地FastAPI后端
      '/api': 'http://localhost:8000',
    },
  },
  base: '/',
}); 