const fs=require('fs');
const DATA=JSON.parse(fs.readFileSync(process.argv[2]));
eval(fs.readFileSync(__dirname+'/../src/engine.js','utf8')+';globalThis.createEngine=createEngine;globalThis.evaluationSteps=evaluationSteps;');
const E=createEngine(DATA);
const show=(items,f={})=>{const r=E.recommend(items,f,5,'C');console.log('\nQUERY',JSON.stringify(items),'took_ms',r.took_ms,'counts',r.counts,'unrec',JSON.stringify(r.unrecognized));
 r.results.forEach(s=>console.log(' ',(s.score*100).toFixed(1)+'%',E.recipes[s.ri].name,'| missing',s.why.miss.map(i=>E.vocab[i]).join(',')||'-'))};
show(['potato','onion','tomato','paneer','rice']);
show(['aloo','pyaz','jeera']);
console.log('--- edge cases');
console.log('empty',JSON.stringify(E.recommend([], {},5,'C').results.length));
show(['paneer']);
show(Array.from(new Set(E.recipes[10].core.concat(E.recipes[20].core,E.recipes[30].core))).slice(0,30).map(i=>E.vocab[i]));
console.log('only staples',E.recommend(['salt','water'],{},5,'C').onlyStaples);
const u=E.recommend(['aloo','jeeraa','tomatoo','xyzq'],{},3,'C'); console.log('unknown',JSON.stringify(u.unrecognized));
console.log('tie stability', JSON.stringify(E.recommend(['lemon'],{},5,'A').results.map(s=>s.id))===JSON.stringify(E.recommend(['lemon'],{},5,'A').results.map(s=>s.id)));
console.log('filters veg/30min', E.recommend(['potato','onion'],{diet:'veg',maxTime:30},3,'C').results.map(s=>E.recipes[s.ri].name+' '+E.recipes[s.ri].time));
console.log('jain', E.recommend(['potato','onion'],{diet:'jain'},3,'C').results.map(s=>E.recipes[s.ri].name));
for(const m of ['A','B','C'])console.log(m,E.recommend(['aloo','pyaz','jeera'],{},1,m).results.map(s=>E.recipes[s.ri].name+' '+s.score.toFixed(3)));
// small evaluation
const t0=Date.now();
const gen=evaluationSteps(E,{testCap:+process.argv[3]||60,devCap:+process.argv[4]||40});
let last;for(const st of gen){last=st}
const R=last.results;console.log('\nEVAL secs',(Date.now()-t0)/1000);
console.log(JSON.stringify(R.config));
const f=x=>Object.fromEntries(Object.entries(x).map(([k,v])=>[k,v.mean!==undefined?(v.mean*100).toFixed(1)+'±'+(v.sd*100).toFixed(1):v]));
for(const k of 'ABC')console.log('Test',k,JSON.stringify(f(R.tests[k])));
console.log(R.ablation.map(a=>`${a.label}: top1 ${(a.top1*100).toFixed(1)} top5 ${(a.top5*100).toFixed(1)} mrr ${a.mrr.toFixed(3)}`).join('\n'));
console.log('bySize',JSON.stringify(R.breakdownSize));console.log('byRegion',Object.keys(R.breakdownRegion));
console.log('fail',R.failures.misses,R.failures.nearDup,R.failures.worst.slice(0,3));
