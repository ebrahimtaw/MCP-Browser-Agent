#!/usr/bin/env bash
set -euo pipefail

echo "=== node / npx on PATH ==="
which node && node --version
which npx && npx --version

echo ""
echo "=== @playwright/mcp installed globally ==="
npm ls -g --depth=0 2>/dev/null | grep playwright || echo "(none)"

GLOBAL_NPM=$(npm root -g)
echo "Global npm root: $GLOBAL_NPM"

echo ""
echo "=== Chromium binary present ==="
find /ms-playwright -name 'chrome' -path '*chrome-linux*' 2>/dev/null | head -3

echo ""
echo "=== Python deps importable ==="
python3 -c "import fastapi, mcp_agent, openai; print('OK -', fastapi.__version__)"

echo ""
echo "=== Headless Chromium can actually navigate ==="
PWCORE="/usr/lib/node_modules/@playwright/mcp/node_modules/playwright-core"
node -e "
const { chromium } = require('$PWCORE');
(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
  });
  const page = await browser.newPage();
  await page.goto('https://example.com', { waitUntil: 'load', timeout: 30000 });
  const title = await page.title();
  console.log('PAGE_TITLE:', title);
  await browser.close();
  if (title.toLowerCase().includes('example')) {
    console.log('CHROMIUM_CAN_BROWSE: YES');
    process.exit(0);
  } else {
    console.error('CHROMIUM_CAN_BROWSE: NO');
    process.exit(1);
  }
})().catch(e => { console.error('CHROMIUM_ERROR:', e.message); process.exit(2); });
"
