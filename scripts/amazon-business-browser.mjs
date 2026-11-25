/* Direct, account-scoped Amazon Business report & payment reader. No Codex/MCP/model calls.
   Secrets travel over stdin and are encrypted locally when Remember is selected. */
import readline from 'node:readline';
import {existsSync,mkdirSync,readFileSync,writeFileSync,unlinkSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {randomBytes,createCipheriv,createDecipheriv} from 'node:crypto';

const root=resolve(process.env.LEDGER_AMAZON_DIR||'');
if(!process.env.LEDGER_AMAZON_DIR||root===resolve('/')) process.exit(2);
mkdirSync(root,{recursive:true,mode:0o700});
const REPORT='https://www.amazon.com/b2b/aba/reports';
const PAYMENTS='https://www.amazon.com/cpe/yourpayments/transactions';
let context,page,pendingCredentials=null;
const file=name=>join(root,name);
const read=name=>{try{return JSON.parse(readFileSync(file(name),'utf8'));}catch{return null;}};
const write=(name,value)=>writeFileSync(file(name),JSON.stringify(value),{mode:0o600});
function seal(value){
 const p=file('credentials.key');if(!existsSync(p))writeFileSync(p,randomBytes(32),{mode:0o600,flag:'wx'});
 const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',readFileSync(p),iv);
 const data=Buffer.concat([cipher.update(JSON.stringify(value),'utf8'),cipher.final()]);
 write('credentials.enc',{iv:iv.toString('base64'),tag:cipher.getAuthTag().toString('base64'),data:data.toString('base64')});
}
function unseal(){try{
 const c=read('credentials.enc');if(!c)return null;
 const cipher=createDecipheriv('aes-256-gcm',readFileSync(file('credentials.key')),Buffer.from(c.iv,'base64'));
 cipher.setAuthTag(Buffer.from(c.tag,'base64'));
 return JSON.parse(Buffer.concat([cipher.update(Buffer.from(c.data,'base64')),cipher.final()]).toString('utf8'));
}catch{return null;}}
function safe(url){try{const u=new URL(url);return u.protocol==='https:'&&['www.amazon.com','amazon.com'].includes(u.hostname)&&!u.username&&!u.password;}catch{return false;}}
function reportURL(url){try{const u=new URL(url);return safe(url)&&/^\/b2b\/(?:aba|analytics)(?:\/|$)/.test(u.pathname);}catch{return false;}}
async function ensure(){
 if(page)return;
 const {chromium}=await import('playwright');
 context=await chromium.launchPersistentContext(file('profile'),{channel:'chromium',headless:true,acceptDownloads:true,viewport:{width:1280,height:900}});
 await context.route('**/*',async route=>{
  const req=route.request();
  if(req.isNavigationRequest()&&req.frame()===req.frame().page().mainFrame()&&!safe(req.url()))return route.abort();
  return route.continue();
 });
 page=context.pages()[0]||await context.newPage();page.setDefaultTimeout(12000);
}
async function settle(){await page.waitForLoadState('domcontentloaded').catch(()=>{});await page.waitForTimeout(600);}
async function visible(selector){const loc=page.locator(selector).first();return await loc.isVisible().catch(()=>false)?loc:null;}
async function submit(selector){const loc=await visible(selector);if(!loc)return false;await loc.click();await settle();return true;}
async function state(){
 if(!safe(page.url()))return {stage:'attention',connected:false,message:'Amazon redirected outside its supported sign-in pages.'};
 const captcha=await visible('#auth-captcha-image, img[alt*="captcha" i], img[src*="captcha"]');
 if(captcha){return {stage:'captcha',connected:false,message:'Enter the characters shown by Amazon.',captcha_image:'data:image/png;base64,'+(await captcha.screenshot()).toString('base64')};}
 if(await visible('input[name="otpCode"], input[name="code"], #auth-mfa-otpcode, #cvf-input-code, #input-box-otp, input[autocomplete="one-time-code"]'))return {stage:'otp',connected:false,message:'Enter the one-time verification code sent by Amazon.'};
 if(await visible('#auth-error-message-box, #auth-warning-message-box'))return {stage:'attention',connected:false,message:'Amazon did not accept this sign-in step. Check your details or reconnect.'};
 if(await visible('#ap_password, input[name="password"]'))return {stage:'password',connected:false,message:'Amazon needs your password. Reconnect with your Amazon Business email and password.'};
 if(await visible('#ap_email, #ap_email_login, input[type="email"]'))return {stage:'disconnected',connected:false,message:'Sign in with your Amazon Business account.'};
 const body=(await page.locator('body').innerText()).slice(0,60000);
 if(/access restricted|unauthorized ai agent|automated access/i.test(body)||await visible('img[src*="error/title"]')){
  return {stage:'csv_required',connected:false,message:'Amazon blocked automated server browser sign-in (“Access restricted”). Open Amazon Business Reports in your regular browser, download your CSV, and import it below to name all your purchases immediately.'};
 }
 if(/approve (?:the |this )?sign.in|check your (?:email|phone)|notification.*(?:approve|sign.in)/i.test(body))return {stage:'approval',connected:false,message:'Approve Amazon’s sign-in notification, then choose Check again.'};
 const nav=await page.locator('#nav-link-accountList').innerText().catch(()=>'');
 const pathname=new URL(page.url()).pathname;
 const signedIn=!/hello,?\s*sign\s*in/i.test(nav)&&!/^\/(?:ap|ax)\//.test(pathname);
 const business=reportURL(page.url())&&/business analytics|reconciliation|spend visibility|reports/i.test(body);
 const payments=/^\/(?:cpe\/yourpayments|gp\/(?:your-account|css)|your-orders)(?:\/|$)/.test(pathname)&&/transactions|your orders|order details/i.test(body);
 if((business||payments)&&signedIn){
  if(pendingCredentials){if(pendingCredentials.remember!==false)seal({email:pendingCredentials.email,password:pendingCredentials.password});pendingCredentials=null;}
  return {stage:'connected',connected:true,message:'Amazon Business sign-in is connected.'};
 }
 if(/^\/(?:ap|ax)\//.test(pathname))return {stage:'approval',connected:false,message:'Complete Amazon’s additional verification, then choose Check again. If it cannot be completed here, reconnect later.'};
 if(signedIn){
  if(pendingCredentials){if(pendingCredentials.remember!==false)seal({email:pendingCredentials.email,password:pendingCredentials.password});pendingCredentials=null;}
  return {stage:'connected',connected:true,message:'Amazon account is connected.'};
 }
 return {stage:'attention',connected:false,message:'Amazon sign-in could not be verified. Try reconnecting.'};
}
async function login(credentials,fresh=false){
 if(fresh){await context.clearCookies();pendingCredentials={...credentials};if(!credentials.remember){try{unlinkSync(file('credentials.enc'));}catch{}}}
 await page.goto(REPORT,{waitUntil:'domcontentloaded',timeout:45000});await settle();
 if(!safe(page.url())||!/^\/(?:ap|ax)\//.test(new URL(page.url()).pathname))return state();
 let email=await visible('#ap_email_login, #ap_email, input[type="email"]');
 if(email){await email.fill(credentials.email);await submit('#continue, input[type="submit"], button[type="submit"]');}
 if(!safe(page.url())||!/^\/(?:ap|ax)\//.test(new URL(page.url()).pathname))return state();
 const password=await visible('#ap_password, input[name="password"]');
 if(password){await password.fill(credentials.password);await submit('#signInSubmit, input[type="submit"], button[type="submit"]');}
 return state();
}
async function verify(code){
 if(!safe(page.url())||!/^\/(?:ap|ax|errors)\//.test(new URL(page.url()).pathname))return state();
 const otp=await visible('#auth-mfa-otpcode, input[name="otpCode"], input[name="code"], #cvf-input-code, #input-box-otp, input[autocomplete="one-time-code"]');
 if(otp){await otp.fill(code);await submit('#auth-signin-button, input[type="submit"], button[type="submit"]');}
 else {const captcha=await visible('#auth-captcha-guess, #captchacharacters, input[name="guess"]');if(captcha){
  await captcha.fill(code);
  const credentials=pendingCredentials||unseal(),password=await visible('#ap_password, input[name="password"]');
  if(password&&credentials?.password)await password.fill(credentials.password);
  await submit('#signInSubmit, input[type="submit"], button[type="submit"]');
 }}
 return state();
}
async function named(role,regex){const loc=page.getByRole(role,{name:regex}).first();return await loc.isVisible().catch(()=>false)?loc:null;}
async function reportPage(){
 const location=read('report-location.json')?.url;
 await page.goto(reportURL(location)?location:REPORT,{waitUntil:'domcontentloaded',timeout:45000});await settle();
 let s=await state();
 if(!s.connected){const credentials=unseal();if(credentials)s=await login(credentials);if(!s.connected)return s;}
 if(!/reconciliation/i.test(await page.locator('body').innerText())){
  const menu=await named('button',/^reports$/i);if(menu){await menu.click();await settle();}
 }
 let target=await named('link',/^reconciliation(?:\s*\(?new\)?)?$/i)||await named('menuitem',/^reconciliation(?:\s*\(?new\)?)?$/i);
 if(target){const href=await target.getAttribute('href');if(href&&!reportURL(new URL(href,page.url()).href))return {stage:'attention',connected:true,noReport:true};await target.click();await settle();}
 else {
  for(const select of await page.locator('select').all()){
   const option=await select.locator('option').evaluateAll(es=>es.find(e=>/^reconciliation(?:\s*\(?new\)?)?$/i.test(e.textContent.trim()))?.value);
   if(option){await select.selectOption(option);await settle();break;}
  }
 }
 if(!reportURL(page.url())||!/reconciliation/i.test(await page.locator('body').innerText()))return {stage:'connected',connected:true,noReport:true};
 write('report-location.json',{url:page.url()});
 for(const select of await page.locator('select').all()){
  const option=await select.locator('option').evaluateAll(es=>es.find(e=>/^(?:past|last) 12 months$/i.test(e.textContent.trim()))?.value);
  if(option){await select.selectOption(option);await settle();break;}
 }
 const adjust=await named('button',/^adjust columns$/i);
 if(adjust){
  await adjust.click();await settle();
  const columns=['Charge Identifier','Payment Date','Transaction Date','Payment Amount','Currency','Payment Identifier','Payment Instrument Last 4 Digits','Order ID','Title','Item Total','Item Net Total','Net Total','Item Tax','Tax','Shipping','PO Line Item ID','Invoice Number','Shipment ID','Transaction Type','ASIN','UNSPSC','GL Code'];
  for(const label of columns){const checkbox=await named('checkbox',new RegExp('^'+label+'$','i'));if(checkbox)await checkbox.check();}
  const apply=await named('button',/^(?:submit|apply)$/i);if(apply){await apply.click();await settle();}
 }
 return {connected:true};
}
async function scrapePaymentTransactions(limitOrders=25){
 try{
  await page.goto(PAYMENTS,{waitUntil:'domcontentloaded',timeout:35000});await settle();
  if(!safe(page.url())||/^\/(?:ap|ax)\//.test(new URL(page.url()).pathname))return [];
  const rawCharges=await page.evaluate(()=>{
   const out=[];
   const dateRe=/^(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}$/i;
   let currentDate='';
   const blocks=document.querySelectorAll('.apx-transactions-line-item-component-container, .a-box-group, .pmts-portal-component, div');
   for(const el of blocks){
    const txt=(el.innerText||'').trim();
    if(dateRe.test(txt)){currentDate=txt;continue;}
    if(!txt||txt.length>600||!/Order\s*#?\s*\d{3}-\d{7}-\d{7}/i.test(txt))continue;
    const orderMatch=txt.match(/(\d{3}-\d{7}-\d{7})/);
    const amtMatch=txt.match(/-\s*\$(\d[\d,]*\.\d{2})|\$(\d[\d,]*\.\d{2})/);
    const cardMatch=txt.match(/(?:ending in|[*•xX]{2,})\s*(\d{4})\b/i);
    const dateInline=txt.match(/(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}/i);
    const posted=dateInline?dateInline[0]:currentDate;
    const amount=amtMatch?(amtMatch[1]||amtMatch[2]):'';
    if(orderMatch&&amount&&posted&&cardMatch){
     out.push({order_id:orderMatch[1],amount,posted,card_last4:cardMatch[1]});
    }
   }
   const uniq=new Map();
   for(const c of out){uniq.set(`${c.order_id}|${c.amount}|${c.posted}|${c.card_last4}`,c);}
   return [...uniq.values()];
  });
  if(!rawCharges.length)return [];
  const orderItems=new Map();
  const uniqueOrders=[...new Set(rawCharges.map(c=>c.order_id))].slice(0,limitOrders);
  for(const orderId of uniqueOrders){
   const url=`https://www.amazon.com/gp/css/summary/print.html?orderID=${encodeURIComponent(orderId)}`;
   await page.goto(url,{waitUntil:'domcontentloaded',timeout:25000}).catch(()=>{});await settle();
   if(!safe(page.url()))continue;
   const titles=await page.evaluate(()=>{
    const items=[];
    for(const el of document.querySelectorAll('i, .yohtmlc-product-title, .a-link-normal[href*="/dp/"], .a-link-normal[href*="/gp/product/"]')){
     const t=(el.textContent||'').replace(/\s+/g,' ').trim();
     if(t.length>=4&&t.length<=300&&!/^(?:view|track|return|buy it again|write a product review|invoice|printable)/i.test(t)){
      items.push(t);
     }
    }
    return [...new Set(items)].slice(0,25);
   });
   if(titles.length)orderItems.set(orderId,titles);
  }
  return rawCharges.filter(c=>orderItems.has(c.order_id)).map(c=>({
   order_id:c.order_id,
   orders:[c.order_id],
   posted:c.posted,
   amount:c.amount,
   card_last4:c.card_last4,
   items:orderItems.get(c.order_id).map(description=>({description}))
  }));
 }catch{return [];}
}
async function downloadText(download){
 const stream=await download.createReadStream();let length=0;const parts=[];
 for await(const part of stream){length+=part.length;if(length>12_000_000){stream.destroy();await download.delete();throw Error('report too large');}parts.push(part);}
 await download.delete();return Buffer.concat(parts).toString('utf8');
}
async function sync(){
 const s=await reportPage();
 if(!s.connected)return s;
 let csv=null;
 if(!s.noReport){
  let button=await named('button',/^(?:generate report|download csv|export csv|download report|download)$/i)||await named('link',/^(?:download csv|export csv|download report)$/i);
  if(button){
   const first=page.waitForEvent('download',{timeout:12000}).catch(()=>null);
   await button.click();let download=await first;
   if(!download){
    const next=page.getByRole('button',{name:/^(?:download csv|download report|download)$/i}).first();
    await next.waitFor({state:'visible',timeout:60000}).catch(()=>{});
    if(await next.isVisible().catch(()=>false)){
     const waiting=page.waitForEvent('download',{timeout:30000}).catch(()=>null);await next.click();download=await waiting;
    }
   }
   if(download)csv=await downloadText(download);
  }
 }
 const direct_charges=await scrapePaymentTransactions(csv?15:35);
 if(!csv&&!direct_charges.length){
  return {stage:'attention',connected:true,message:'Amazon’s report download control was unavailable and no recent card charges were found. You can also import a reconciliation or order CSV below.'};
 }
 return {connected:true,stage:'connected',message:'Amazon Business synced.',...(csv?{csv}:{}),...(direct_charges.length?{direct_charges}:{})};
}
async function dispatch(input){
 await ensure();
 if(input.action==='connect')return login(input,true);
 if(input.action==='verify')return verify(input.code);
 if(input.action==='refresh'){await settle();return state();}
 if(input.action==='sync')return sync();
 throw Error('invalid action');
}
async function close(){try{await context?.close();}finally{process.exit(0);}}
export async function execute(input,browserContext=null){
 if(browserContext){context=browserContext;page=context.pages()[0]||await context.newPage();}
 return dispatch(input);
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 let chain=Promise.resolve();
 const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
 lines.on('line',line=>{chain=chain.then(async()=>{try{if(line.length>20000)throw Error('input too large');const result=await dispatch(JSON.parse(line));process.stdout.write(JSON.stringify(result)+'\n');}catch{process.stdout.write(JSON.stringify({error:true})+'\n');}});});
 process.on('SIGTERM',close);process.on('SIGINT',close);lines.on('close',close);
}
