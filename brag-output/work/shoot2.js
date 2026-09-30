const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const fs=require('fs');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 980, height: 2400 }, deviceScaleFactor: 2 });
  const meta={};
  for (const m of [12, 34]) {
    await p.goto(`http://localhost:8599/?m=${m}`, { waitUntil: 'networkidle' });
    await p.waitForSelector('text=System Status', { timeout: 30000 });
    await p.addStyleTag({content:'[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],header{display:none!important}'});
    await p.waitForTimeout(2000);
    const box=async sel=>{const l=p.locator(sel).first();if(!(await l.count()))return null;return await l.boundingBox()};
    const h1=await box('h1:has-text("Live Analytics")'); const cap=await box('text=Real-time match tracking');
    const card=await p.evaluate(()=>{const e=[...document.querySelectorAll('[data-testid=stVerticalBlock]')].filter(x=>getComputedStyle(x).borderTopWidth==='1px'&&x.textContent.includes('Argentina')).pop();const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}});
    const pf=await box('h3:has-text("Player Fitness")');
    const sr=await box('h3:has-text("Substitution Recommendations")');
    const r2=await box('p:has-text("80% Confidence")');
    const off=m===12?null:await box('li:has-text("Off: Striker #9")'); const on=m===12?null:await box('li:has-text("On: Forward #19")');
    const arg=await box('text=Argentina Fitness');
    const L=card.x, W=card.width;
    const clip=async(name,x,y,w,h)=>{await p.screenshot({path:`ui/${name}.png`,clip:{x,y,width:w,height:h}}); meta[name]={x,y,w,h}};
    if(m===12){ await clip('fit12',L,pf.y-14,W,(sr?sr.y:card.y+card.height)-pf.y); }
    else {
      await clip('title',h1.x-4,h1.y-6,W,cap.y+cap.height-h1.y+14);
      const rowH=pf.y-card.y-8;
      await clip('score',L,card.y,W,rowH);
      await clip('fit34',L,pf.y-14,W,sr.y-pf.y);
      await clip('rec',L,sr.y-14,W,r2.y-sr.y+4);
      meta.off={x:off.x-L,y:off.y-(sr.y-14),w:off.width,h:off.height};
      meta.on={x:on.x-L,y:on.y-(sr.y-14),w:on.width,h:on.height};
    }
  }
  fs.writeFileSync('ui/meta.json',JSON.stringify(meta,null,1));
  await b.close();
})();
