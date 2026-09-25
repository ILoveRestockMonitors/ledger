const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const context = {module: {exports: {}}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/home-cache.js'), 'utf8'), context);
const createCache = context.module.exports;
test('scope-independent reads and in-flight requests are reused until expiry', async () => {
 let now=0, calls=0;
 const c=createCache(async path=>({path,n:++calls}),()=>now,15000);
 const a=c.read('/accounts'), b=c.read('/accounts');
 assert.equal(a,b); await a;
 await c.read('/accounts'); assert.equal(calls,1);
 await c.read('/overview?scope=personal'); await c.read('/overview?scope=business'); assert.equal(calls,3);
 now=15001; await c.read('/accounts'); assert.equal(calls,4);
});
test('mutations clear cached and pending reads without stale results repopulating them', async () => {
 let resolve, calls=0;
 const c=createCache(()=>{calls++;return calls===1?new Promise(r=>resolve=r):Promise.resolve('new');});
 const stale=c.read('/accounts'); await Promise.resolve();
 c.clear(); assert.equal(await c.read('/accounts'),'new');
 resolve('old'); await stale;
 assert.equal(await c.read('/accounts'),'new');assert.equal(calls,2);
});
test('failed requests are retried',async()=>{
 let calls=0;const c=createCache(async()=>{if(++calls===1)throw Error('network');return 'ok';});
 await assert.rejects(c.read('/accounts'));assert.equal(await c.read('/accounts'),'ok');
});
