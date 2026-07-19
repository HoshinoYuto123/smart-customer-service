const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const baseUrl = process.env.UI_BASE_URL || 'http://127.0.0.1:8000';
const outputDir = path.resolve('artifacts/ui');
fs.mkdirSync(outputDir, { recursive: true });

async function mockChat(page) {
  await page.route('**/api/v1/chat', async route => {
    const payload = JSON.parse(route.request().postData() || '{}');
    await new Promise(resolve => setTimeout(resolve, 350));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        response: {
          text: `已收到你的问题：“${payload.message}”。这是用于界面回归测试的答复。`,
          action: 'continue',
          quick_replies: ['继续查询', '暂时不用了']
        }
      })
    });
  });
}

async function run() {
  const executablePath = process.env.PLAYWRIGHT_CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const browser = await chromium.launch({ headless: true, executablePath });
  const errors = [];

  const desktop = await browser.newContext({ viewport: { width: 1440, height: 960 }, acceptDownloads: true });
  const page = await desktop.newPage();
  page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });
  page.on('pageerror', error => errors.push(`page: ${error.message}`));
  await mockChat(page);
  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: '你好，今天想解决什么问题？' }).waitFor();
  const desktopLayout = await page.evaluate(() => ({
    bodyWidth: document.body.scrollWidth,
    viewportWidth: window.innerWidth,
    composerBottom: document.querySelector('.composer').getBoundingClientRect().bottom,
    viewportHeight: window.innerHeight
  }));
  if (desktopLayout.bodyWidth > desktopLayout.viewportWidth || desktopLayout.composerBottom > desktopLayout.viewportHeight) {
    throw new Error(`Desktop layout overflow: ${JSON.stringify(desktopLayout)}`);
  }
  await page.getByRole('button', { name: /退款还没到账/ }).click();
  await page.getByText(/这是用于界面回归测试的答复/).waitFor();
  await page.getByRole('button', { name: '继续查询' }).waitFor();

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出当前会话' }).click();
  const download = await downloadPromise;
  if (!download.suggestedFilename().endsWith('.md')) throw new Error('Export did not create a Markdown file');
  await page.screenshot({ path: path.join(outputDir, 'chat-desktop.png'), fullPage: true });

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const mobilePage = await mobile.newPage();
  mobilePage.on('console', message => { if (message.type() === 'error') errors.push(`mobile console: ${message.text()}`); });
  mobilePage.on('pageerror', error => errors.push(`mobile page: ${error.message}`));
  await mockChat(mobilePage);
  await mobilePage.goto(baseUrl, { waitUntil: 'networkidle' });
  const mobileLayout = await mobilePage.evaluate(() => ({
    bodyWidth: document.body.scrollWidth,
    viewportWidth: window.innerWidth,
    composerBottom: document.querySelector('.composer').getBoundingClientRect().bottom,
    viewportHeight: window.innerHeight
  }));
  if (mobileLayout.bodyWidth > mobileLayout.viewportWidth || mobileLayout.composerBottom > mobileLayout.viewportHeight) {
    throw new Error(`Mobile layout overflow: ${JSON.stringify(mobileLayout)}`);
  }
  await mobilePage.getByRole('button', { name: '打开会话列表' }).click();
  await mobilePage.locator('#sidebar.open').waitFor();
  await mobilePage.screenshot({ path: path.join(outputDir, 'chat-mobile.png'), fullPage: true });

  await browser.close();
  if (errors.length) throw new Error(errors.join('\n'));
  console.log('UI smoke passed: desktop chat, mocked reply, Markdown export, mobile drawer');
  console.log(path.join(outputDir, 'chat-desktop.png'));
  console.log(path.join(outputDir, 'chat-mobile.png'));
}

run().catch(error => { console.error(error); process.exitCode = 1; });
