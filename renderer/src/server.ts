import express from 'express';
import fs from 'fs';
import { renderRecap } from './render';
import type { RenderSpec } from './types';

const app = express();
app.use(express.json({ limit: '10mb' }));

app.get('/health', (_req, res) => {
  res.json({ ok: true, service: 'renderer', engine: 'remotion' });
});

app.post('/render', async (req, res) => {
  const spec = req.body as RenderSpec;
  if (!spec || !Array.isArray(spec.photos)) {
    res.status(400).json({ error: 'invalid spec: missing photos array' });
    return;
  }
  if (!spec.voiceoverUrl) {
    res.status(400).json({ error: 'invalid spec: missing voiceoverUrl' });
    return;
  }

  let outPath: string | undefined;
  try {
    outPath = await renderRecap(spec);
    res.setHeader('Content-Type', 'video/mp4');
    res.setHeader('Content-Disposition', `attachment; filename="recap-${spec.videoRenderId}.mp4"`);
    fs.createReadStream(outPath)
      .on('error', (e) => {
        console.error('[server] stream error:', e);
        if (!res.headersSent) res.status(500).json({ error: String(e) });
      })
      .on('close', () => {
        if (outPath) {
          fs.unlink(outPath, () => {});
        }
      })
      .pipe(res);
  } catch (e: any) {
    console.error('[server] render error:', e);
    if (outPath && fs.existsSync(outPath)) {
      try { fs.unlinkSync(outPath); } catch {}
    }
    if (!res.headersSent) {
      res.status(500).json({ error: e?.message ?? String(e) });
    }
  }
});

process.on('uncaughtException', (e) => {
  console.error('[server] uncaughtException:', e);
});
process.on('unhandledRejection', (e) => {
  console.error('[server] unhandledRejection:', e);
});

const port = Number(process.env.PORT) || 3001;
app.listen(port, () => {
  console.log(`[server] Renderer listening on http://localhost:${port}`);
  console.log(`[server] Endpoints: GET /health, POST /render`);
});
