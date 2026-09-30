const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const fs=require('fs');
(async () => {
  const mode=process.argv[2];
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  await p.goto('file://'+__dirname+'/comp.html');
  await p.evaluate(()=>window.ready);
  let times;
  if(mode==='stills'){ times=process.argv.slice(3).map(Number); fs.mkdirSync('stills',{recursive:true}); }
  else { times=[...Array(630).keys()].map(i=>i/30); fs.mkdirSync('frames',{recursive:true}); }
  for(let i=0;i<times.length;i++){
    await p.evaluate(t=>window.render(t),times[i]);
    const out= mode==='stills'?`stills/t${times[i].toFixed(2)}.png`:`frames/f${String(i).padStart(4,'0')}.png`;
    await p.screenshot({path:out});
  }
  await b.close();
})();
