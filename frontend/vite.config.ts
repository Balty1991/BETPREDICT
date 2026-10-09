import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import fs from 'fs';

/**
 * În dev/preview servim `../data` (fișierele vechi) și `../api` (sau API_DIR) direct din repo,
 * ca aplicația să meargă local exact ca pe GitHub Pages. În build nu se copiază nimic:
 * site-ul e asamblat de `betpredict/publish/site.py` (dist + data + api).
 */
function serveRepoJson(): Plugin {
  const roots: Record<string, string> = {
    '/data/': path.resolve(__dirname, '../data'),
    '/api/': process.env.API_DIR ? path.resolve(process.env.API_DIR) : path.resolve(__dirname, '../api'),
  };
  const handler = (req: { url?: string }, res: { setHeader: (k: string, v: string) => void; end: (b: Buffer) => void; statusCode: number }, next: () => void) => {
    const url = (req.url || '').split('?')[0];
    for (const [prefix, dir] of Object.entries(roots)) {
      if (!url.startsWith(prefix)) continue;
      const file = path.join(dir, decodeURIComponent(url.slice(prefix.length)));
      if (!file.startsWith(dir) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.statusCode = 404; res.end(Buffer.from('')); return; }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(fs.readFileSync(file));
      return;
    }
    next();
  };
  return {
    name: 'serve-repo-json',
    configureServer(server) { server.middlewares.use(handler as never); },
    configurePreviewServer(server) { server.middlewares.use(handler as never); },
  };
}

export default defineConfig({
  plugins: [react(), serveRepoJson()],
  base: './',
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    // Build-ul nu mai scrie în rădăcina repo-ului: GitHub Actions publică `frontend/dist` pe gh-pages.
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
        manualChunks(id: string) {
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react';
          return undefined;
        },
      },
    },
  },
});
