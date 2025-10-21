import { delay, findClickableByText, waitForPageIdle } from './utils.js';

const NEXT_KEYWORDS = ['next', '下一步', '继续', '继续下一步'];
const LOGIN_KEYWORDS = [
  'login',
  'log in',
  'sign in',
  'sign up',
  '注册',
  '登录',
  '登入',
  '會員登入',
  '會員登录',
  '會員登錄',
  '會員註冊',
  '會員注册',
  '會員登入'
];
const GOOGLE_KEYWORDS = [
  'google',
  'continue with google',
  '使用 google 登录',
  '使用 google 登入',
  '使用google登录',
  '使用google登入',
  '谷歌',
  '谷歌登录',
  '谷歌登入'
];

async function clickAndDispose(handle) {
  try {
    await handle.click({ delay: 50 });
  } catch {
    // ignore
  } finally {
    await handle.dispose().catch(() => {});
  }
}

export async function loginToGoogle(page, account) {
  await page.goto('https://accounts.google.com/signin/v2/identifier', {
    waitUntil: 'networkidle0',
    timeout: 120000
  });
  const emailInput = await page.waitForSelector('input[type="email"]', { timeout: 60000 });
  await emailInput.click({ clickCount: 3 }).catch(() => {});
  await emailInput.type(account.email, { delay: 30 });

  const emailNext = await findClickableByText(page, NEXT_KEYWORDS);
  if (emailNext) {
    await Promise.all([
      waitForPageIdle(page, 120000).catch(() => {}),
      clickAndDispose(emailNext)
    ]);
  } else {
    await page.keyboard.press('Enter');
    await delay(800);
  }

  const passwordInput = await page.waitForSelector('input[type="password"]', { timeout: 120000 });
  await passwordInput.click({ clickCount: 3 }).catch(() => {});
  await passwordInput.type(account.password, { delay: 30 });

  const passwordNext = await findClickableByText(page, NEXT_KEYWORDS);
  if (passwordNext) {
    await Promise.all([
      waitForPageIdle(page, 120000).catch(() => {}),
      clickAndDispose(passwordNext)
    ]);
  } else {
    await page.keyboard.press('Enter');
  }

  if (account.recoveryEmail) {
    const recoveryInput = await page.waitForSelector('input[type="email"]', { timeout: 5000 }).catch(() => null);
    if (recoveryInput) {
      try {
        await recoveryInput.click({ clickCount: 3 });
        await recoveryInput.type(account.recoveryEmail, { delay: 30 });
        const recoveryNext = await findClickableByText(page, NEXT_KEYWORDS);
        if (recoveryNext) {
          await Promise.all([
            waitForPageIdle(page, 120000).catch(() => {}),
            clickAndDispose(recoveryNext)
          ]);
        } else {
          await page.keyboard.press('Enter');
        }
      } catch {
        // ignore optional recovery step failures
      }
    }
  }

  await waitForPageIdle(page, 120000);
  await delay(1500);
}

export async function trySiteGoogleLogin(browser, page) {
  for (const keyword of LOGIN_KEYWORDS) {
    const trigger = await findClickableByText(page, [keyword]);
    if (trigger) {
      await clickAndDispose(trigger);
      await delay(1500);
      break;
    }
  }

  const googleButton = await findClickableByText(page, GOOGLE_KEYWORDS, ['button', 'a', 'div', 'span']);
  if (!googleButton) {
    return false;
  }

  const popupTargetPromise = browser
    .waitForTarget((target) => target.opener() === page.target() && target.type() === 'page', { timeout: 10000 })
    .catch(() => null);

  await clickAndDispose(googleButton);

  const popupTarget = await popupTargetPromise;
  if (popupTarget) {
    const popupPage = await popupTarget.page().catch(() => null);
    if (popupPage) {
      await waitForPageIdle(popupPage, 120000);
      await delay(2000);
      await popupPage.waitForClose({ timeout: 120000 }).catch(() => {});
    }
  } else {
    await waitForPageIdle(page, 120000);
    await delay(1500);
  }

  return true;
}
