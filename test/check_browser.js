const { chromium } = require('playwright');
(async()=>{
 const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium'}).catch(async()=>chromium.launch());
 const p=await b.newPage({viewport:{width:360,height:800}});
 const errs=[];p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});p.on('pageerror',e=>errs.push('PAGEERR '+e.message));
 // wrap file like the publisher does
 const body=require('fs').readFileSync(process.argv[2]||'index.html','utf8');
 await p.setContent('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>'+body+'</body></html>');
 await p.waitForSelector('#app:not([hidden])',{timeout:20000});
 await p.fill('#ing-input','aloo, pyaz jeera'); await p.press('#ing-input','Enter');
 await p.waitForSelector('.recipe');
 console.log('cards',await p.locator('.recipe').count(),'chips',await p.locator('#my-chips .chip').allTextContents());
 console.log('groups',await p.locator('.group h2').allTextContents());
 await p.fill('#ing-input','jeeraa'); await p.press('#ing-input','Enter');
 console.log('unknown:',await p.locator('#unknown-notice').innerText());
 await p.click('[data-detail]'); console.log('detail lines',await p.locator('.lines li').count(), (await p.locator('.lines li.have').count())+' have');
 await p.click('#close-detail');
 console.log('overflowX', await p.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth));
 await p.screenshot({path:'build/shot_find.png'});
 await p.click('#tab-how'); console.log('how h2',(await p.locator('#panel-how h2').allTextContents()).join('|'));
 await p.click('#tab-eval'); await p.click('#run-eval');
 const t0=Date.now(); await p.waitForSelector('#eval-out .card',{timeout:300000}); 
 console.log('eval secs',(Date.now()-t0)/1000); console.log((await p.locator('#eval-status').innerText()));
 await p.screenshot({path:'build/shot_eval.png',fullPage:true});
 console.log((await p.locator('#eval-out').innerText()).slice(0,3500));
 console.log('ERRORS',errs);
 await b.close();
})();
