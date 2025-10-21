import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import puppeteer from 'puppeteer-core';
import { fileURLToPath } from 'url';
import { loginToGoogle, trySiteGoogleLogin } from './siteAutomation.js';
import {
  ensureDir,
  parseAccounts,
  sanitizeFilename,
  detectBrowserExecutable,
  waitForPageIdle
} from './utils.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default class SandboxManager {
  constructor() {
    this.sandboxes = new Map();
    this.sequence = 1;
    this.baseDir = path.resolve(__dirname, '../data');
    this.sessionsDir = path.join(this.baseDir, 'sessions');
    this.cookiesDir = path.join(this.baseDir, 'cookies');
    this.executablePath = null;
    ensureDir(this.baseDir);
    ensureDir(this.sessionsDir);
    ensureDir(this.cookiesDir);
  }

  resolveExecutablePath() {
    if (!this.executablePath) {
      this.executablePath = detectBrowserExecutable();
    }
    return this.executablePath;
  }

  listSandboxes() {
    return Array.from(this.sandboxes.values()).map((sandbox) => this.serializeSandbox(sandbox));
  }

  serializeSandbox(sandbox) {
    return {
      id: sandbox.id,
      status: sandbox.status,
      defaultUrl: sandbox.defaultUrl,
      currentUrl: sandbox.currentUrl,
      account: sandbox.account ? { email: sandbox.account.email } : null,
      cookieFile: sandbox.cookieFile,
      error: sandbox.error ?? null
    };
  }

  async createSandboxes(options) {
    const { count = 1, defaultUrl, useGoogleLogin = false, enableSiteAutomation = false } = options ?? {};
    const accounts = parseAccounts(options?.accounts, options?.rawAccounts);
    if (!defaultUrl || typeof defaultUrl !== 'string') {
      throw new Error('必须提供默认打开的链接');
    }
    const created = [];
    for (let i = 0; i < Number(count || 1); i += 1) {
      const id = this.sequence++;
      const account = accounts.length > 0 ? accounts[i % accounts.length] : null;
      const sandbox = {
        id,
        status: 'initializing',
        defaultUrl,
        account,
        useGoogleLogin,
        enableSiteAutomation,
        userDataDir: null,
        browser: null,
        page: null,
        currentUrl: null,
        cookieFile: null,
        error: null
      };
      this.sandboxes.set(id, sandbox);
      this.launchSandbox(sandbox).catch((error) => {
        sandbox.status = 'error';
        sandbox.error = error.message ?? String(error);
        console.error(`[sandbox ${sandbox.id}]`, error);
      });
      created.push(this.serializeSandbox(sandbox));
    }
    return created;
  }

  async launchSandbox(sandbox) {
    const userDataDir = await fs.mkdtemp(path.join(this.sessionsDir, `sandbox-${sandbox.id}-`));
    sandbox.userDataDir = userDataDir;

    const executablePath = this.resolveExecutablePath();
    const browser = await puppeteer.launch({
      headless: false,
      executablePath,
      userDataDir,
      defaultViewport: { width: 1280, height: 720 },
      args: ['--no-first-run', '--no-default-browser-check']
    });
    sandbox.browser = browser;

    const pages = await browser.pages();
    const page = pages[0] ?? (await browser.newPage());
    sandbox.page = page;
    page.setDefaultTimeout?.(120000);

    try {
      if (sandbox.useGoogleLogin && sandbox.account) {
        await loginToGoogle(page, sandbox.account);
      }

      await page.goto(sandbox.defaultUrl, { waitUntil: 'domcontentloaded', timeout: 120000 });
      await waitForPageIdle(page, 120000);
      sandbox.currentUrl = page.url();

      if (sandbox.useGoogleLogin && sandbox.enableSiteAutomation && sandbox.account) {
        await trySiteGoogleLogin(browser, page);
      }

      const activePage = (await browser.pages()).slice(-1)[0] ?? page;
      sandbox.currentUrl = activePage.url();

      await this.saveCookies(browser, sandbox, activePage);
      sandbox.status = 'running';
    } catch (error) {
      sandbox.status = 'error';
      sandbox.error = error.message ?? String(error);
      await browser.close().catch(() => {});
      throw error;
    }
  }

  async saveCookies(browser, sandbox, activePage) {
    const page = activePage ?? sandbox.page;
    if (!page) return;

    const client = await page.target().createCDPSession();
    const { cookies } = await client.send('Network.getAllCookies');
    await client.detach().catch(() => {});

    if (!cookies || cookies.length === 0) {
      return;
    }

    let domain = 'unknown-domain';
    try {
      await waitForPageIdle(page, 10000);
      const url = new URL(page.url());
      domain = url.hostname.replace(/^www\./, '');
      sandbox.currentUrl = page.url();
    } catch (error) {
      console.warn(`[sandbox ${sandbox.id}] 无法获取最终网址`, error);
    }

    const emailPart = sandbox.account ? sanitizeFilename(sandbox.account.email) : `sandbox-${sandbox.id}`;
    const fileName = `${emailPart}-${sanitizeFilename(domain)}.txt`;
    const filePath = path.join(this.cookiesDir, fileName);
    const cookieLines = cookies.map((cookie) => {
      const parts = [`${cookie.name}=${cookie.value}`, `Domain=${cookie.domain}`, `Path=${cookie.path}`];
      if (cookie.expires && cookie.expires > 0) {
        parts.push(`Expires=${new Date(cookie.expires * 1000).toISOString()}`);
      }
      return parts.join('; ');
    });
    await fs.writeFile(filePath, cookieLines.join(os.EOL), 'utf-8');
    sandbox.cookieFile = fileName;
  }

  async deleteSandbox(id) {
    const sandbox = this.sandboxes.get(id);
    if (!sandbox) {
      throw new Error('找不到指定的沙箱');
    }
    sandbox.status = 'stopped';
    if (sandbox.browser) {
      await sandbox.browser.close().catch(() => {});
    }
    sandbox.browser = null;
    sandbox.page = null;
    if (sandbox.userDataDir) {
      await fs.rm(sandbox.userDataDir, { recursive: true, force: true }).catch(() => {});
    }
    this.sandboxes.delete(id);
  }
}
