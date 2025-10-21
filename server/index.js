import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import SandboxManager from './sandboxManager.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const manager = new SandboxManager();

app.use(cors());
app.use(express.json({ limit: '1mb' }));

app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok' });
});

app.get('/api/sandboxes', (_req, res) => {
  res.json(manager.listSandboxes());
});

app.post('/api/sandboxes', async (req, res) => {
  try {
    const { count, defaultUrl, useGoogleLogin, enableSiteAutomation, accounts, rawAccounts } = req.body ?? {};
    const created = await manager.createSandboxes({
      count,
      defaultUrl,
      useGoogleLogin,
      enableSiteAutomation,
      accounts,
      rawAccounts
    });
    res.status(201).json(created);
  } catch (error) {
    console.error('[create sandbox]', error);
    res.status(400).send(error.message || '创建沙箱失败');
  }
});

app.delete('/api/sandboxes/:id', async (req, res) => {
  try {
    const id = Number(req.params.id);
    await manager.deleteSandbox(id);
    res.status(204).end();
  } catch (error) {
    console.error('[delete sandbox]', error);
    res.status(400).send(error.message || '删除沙箱失败');
  }
});

app.use('/downloads', express.static(manager.cookiesDir));

const distPath = path.resolve(__dirname, '../client/dist');
app.use(express.static(distPath));
app.get('*', (req, res, next) => {
  if (req.path.startsWith('/api') || req.path.startsWith('/downloads')) {
    return next();
  }
  res.sendFile(path.join(distPath, 'index.html'));
});

const port = process.env.PORT || 4000;
app.listen(port, () => {
  console.log(`Sandbox server running on http://localhost:${port}`);
  console.log(`前端控制台: http://localhost:${port}`);
});
