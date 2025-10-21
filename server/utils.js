import fs from 'fs';
import path from 'path';

export function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

export function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function sanitizeFilename(value) {
  return value.replace(/[^a-zA-Z0-9._-]/g, '_');
}

export function parseAccounts(accounts = [], rawAccounts = '') {
  const parsed = [];
  if (Array.isArray(accounts)) {
    for (const account of accounts) {
      if (account && account.email && account.password) {
        parsed.push({
          email: account.email,
          password: account.password,
          recoveryEmail: account.recoveryEmail || ''
        });
      }
    }
  }
  const raw = typeof rawAccounts === 'string' ? rawAccounts : '';
  if (raw.trim().length > 0) {
    const lines = raw.split(/\r?\n/);
    for (const line of lines) {
      const clean = line.trim();
      if (!clean) continue;
      const separators = [';', ',', '\t', '|'];
      let parts = [];
      for (const separator of separators) {
        if (clean.includes(separator)) {
          parts = clean.split(separator).map((chunk) => chunk.trim());
          if (parts.length >= 3) break;
        }
      }
      if (parts.length < 3 && clean.includes('-')) {
        parts = clean.split('-').map((chunk) => chunk.trim());
      }
      if (parts.length >= 3) {
        parsed.push({
          email: parts[0],
          password: parts[1],
          recoveryEmail: parts[2]
        });
      }
    }
  }
  return parsed;
}

export function detectBrowserExecutable() {
  const envCandidates = [
    process.env.CHROME_EXECUTABLE,
    process.env.CHROME_PATH,
    process.env.PUPPETEER_EXECUTABLE_PATH
  ].filter(Boolean);

  for (const candidate of envCandidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  const candidates = [];
  const platform = process.platform;
  if (platform === 'win32') {
    const programFiles = process.env['PROGRAMFILES'];
    const programFilesX86 = process.env['PROGRAMFILES(X86)'];
    const localAppData = process.env.LOCALAPPDATA;
    const possibleRoots = [programFiles, programFilesX86, localAppData].filter(Boolean);
    for (const root of possibleRoots) {
      candidates.push(path.join(root, 'Google', 'Chrome', 'Application', 'chrome.exe'));
      candidates.push(path.join(root, 'Google', 'Chrome Beta', 'Application', 'chrome.exe'));
      candidates.push(path.join(root, 'Microsoft', 'Edge', 'Application', 'msedge.exe'));
    }
  } else if (platform === 'darwin') {
    candidates.push('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
    candidates.push('/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta');
    candidates.push('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge');
  } else {
    candidates.push('/usr/bin/google-chrome');
    candidates.push('/usr/bin/chromium-browser');
    candidates.push('/usr/bin/chromium');
    candidates.push('/snap/bin/chromium');
  }

  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }

  throw new Error('未找到可用的 Chrome/Edge 浏览器，请在环境变量 CHROME_EXECUTABLE 中指定浏览器路径');
}

export async function isElementVisible(handle) {
  if (!handle) return false;
  try {
    return await handle.evaluate((element) => {
      if (!element || typeof element !== 'object') return false;
      const style = window.getComputedStyle(element);
      if (!style || style.visibility === 'hidden' || style.display === 'none') {
        return false;
      }
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    });
  } catch {
    return false;
  }
}

export async function findClickableByText(page, keywords, tagNames = ['button', 'a', 'div', 'span']) {
  if (!page || !Array.isArray(keywords) || keywords.length === 0) {
    return null;
  }
  const lowerKeywords = keywords
    .map((keyword) => keyword)
    .filter((keyword) => typeof keyword === 'string' && keyword.trim().length > 0)
    .map((keyword) => keyword.trim().toLowerCase());
  if (lowerKeywords.length === 0) {
    return null;
  }
  const tagFilter = tagNames.map((tag) => `self::${tag}`).join(' or ');
  const alphabetUpper = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  const alphabetLower = alphabetUpper.toLowerCase();

  for (const keyword of lowerKeywords) {
    const escaped = keyword.replace(/'/g, "\\'");
    const xpath = `//*[(${tagFilter}) and contains(translate(normalize-space(string(.)), '${alphabetUpper}', '${alphabetLower}'), '${escaped}')]`;
    const handles = await page.$x(xpath);
    for (const handle of handles) {
      const visible = await isElementVisible(handle);
      if (visible) {
        return handle;
      }
      await handle.dispose();
    }
  }
  return null;
}

export async function waitForPageIdle(page, timeout = 60000) {
  if (!page) return;
  const observers = [];
  observers.push(page.waitForNavigation({ waitUntil: 'networkidle0', timeout }).catch(() => null));
  if (typeof page.waitForNetworkIdle === 'function') {
    observers.push(page.waitForNetworkIdle({ timeout }).catch(() => null));
  }
  observers.push(delay(Math.min(timeout, 10000)));
  await Promise.race(observers);
  await delay(300);
}
