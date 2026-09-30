const { chromium } = require('/opt/node22/lib/node_modules/playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1600, height: 1900 }, deviceScaleFactor: 2 });
  for (const m of [12, 34, 58]) {
    await p.goto(`http://localhost:8599/?m=${m}`, { waitUntil: 'networkidle' });
    await p.waitForSelector('text=System Status', { timeout: 30000 });
    await p.waitForTimeout(2500);
    await p.screenshot({ path: `dash_${m}.png`, fullPage: true });
  }
  await b.close();
})();
