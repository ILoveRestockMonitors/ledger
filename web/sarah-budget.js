/* Uses the same posted, non-transfer category totals as the Home constellation. */
((root)=>{
 function totals(categories){
  const isRent=name=>/^rent(?:\s*(?:\/|&|and)\s*mortgage)?$/i.test(String(name||'').trim());
  let rentCents=0,otherCents=0;const others=[];
  for(const category of categories||[]){
   const value=Number(category.amt);if(!Number.isFinite(value)||value<0)continue;
   const cents=Math.round(value*100);
   if(isRent(category.name))rentCents+=cents;
   else{otherCents+=cents;others.push(category);}
  }
  const totalCents=rentCents+otherCents;
  return {rent:rentCents/100,spent:otherCents/100,total:totalCents/100,share:totalCents?otherCents/totalCents*100:0,categories:others};
 }
 root.LedgerSarahBudget={totals};
 if(typeof module==='object'&&module.exports)module.exports={totals};
})(globalThis);
