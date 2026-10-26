"use strict";
const {readFileSync}=require("node:fs");
const {test}=require("node:test");
const assert=require("node:assert/strict");
const vm=require("node:vm");
const html=readFileSync("web-rma/index.html","utf8");
const js=html.match(/<script>([\s\S]+?)<\/script>/)?.[1];
assert.ok(js,"App must contain a browser script");
const stub={getElementById(name){return {value:name==="aiTask"?"guide":"",checked:false}}};
const sandbox={document:stub,console,Date,Math,setTimeout,clearTimeout};
vm.createContext(sandbox);
vm.runInContext(js.replace(/\s*start\(\);\s*$/,""),sandbox,{timeout:2000});
const run=(src)=>vm.runInContext(src,sandbox,{timeout:1000});
const intake={rmaNumber:"123",defectType:"Weld",csrName:"Sam",purchaseOrder:"P100",customer:"Sample Customer",contactName:"Pat",contactPhone:"5550100",description:"Missing weld"};
test("static app stores in IndexedDB with no server or token request",()=>{
 assert.match(js,/indexedDB\.open/);
 assert.doesNotMatch(js,/api\.openai\.com|github\.com\/repos|fetch\(["']/);
 assert.match(html,/RMA LOCAL/);
});
test("workflow matches EZ Expedite stages",()=>{
 assert.equal(run("STAGES.length"),5);
 assert.equal(run("STAGES[0].key"),"INTAKE");
 assert.equal(run("STAGES[4].key"),"COMPLETE");
});
test("intake requires core fields",()=>{
 assert.ok(run("blockers(normalize({stage:'INTAKE'})).length")>=8);
 assert.equal(run("blockers(normalize("+JSON.stringify(intake)+")).length"),0);
});
test("receiving and quality stage validation",()=>{
 assert.ok(run("blockers(normalize({stage:'AWAITING CUSTOMER RETURN'})).length")>=2);
 assert.equal(run("blockers(normalize({stage:'AWAITING CUSTOMER RETURN',receivedFromCustomer:'YES',receiveDate:'2026-10-22',holdAreaConfirmed:true})).length"),0);
 assert.ok(run("blockers(normalize({stage:'RMA REVIEW',productReviewed:true,workOrderRequired:'YES'})).length")>=2);
 assert.equal(run("blockers(normalize({stage:'RMA REVIEW',productReviewed:true,workOrderRequired:'YES',workOrderIssued:'YES',workOrder:'WO123'})).length"),0);
});
test("final inspection fail returns to Quality without shipping confirmation",()=>{
 assert.equal(run("blockers(normalize({stage:'RETURN TO CUSTOMER',finalQualityResult:'FAIL'})).length"),0);
 assert.ok(run("blockers(normalize({stage:'RETURN TO CUSTOMER',finalQualityResult:'PASS'})).length")>=4);
 assert.equal(run("blockers(normalize({stage:'RETURN TO CUSTOMER',finalQualityResult:'PASS',approvedToShip:true,readyToShip:true,shippedToCustomer:true,returnedToCustomerDate:'2026-10-25'})).length"),0);
});
test("closure blocks unfinished obligations and recovery",()=>{
 assert.ok(run("closureBlockers(normalize({stage:'COMPLETE',owner:'Lee',dispositionComplete:true,recoveryRequested:30,recoveryReceived:0})).length")>0);
 assert.equal(run("closureBlockers(normalize({stage:'COMPLETE',owner:'Lee',dispositionComplete:true,recoveryRequested:30,recoveryReceived:0,recoveryStatus:'WAIVED'})).length"),0);
});
test("CSV parsing handles quotes, rows and RMA export headers",()=>{
 assert.equal(run("parseCsv('a,b\\n\"hello, world\",2').length"),2);
 assert.equal(run("mapCsv('RMA Number,Customer,Part Number\\n122,Demo,ABC')[0].rmaNumber"),"122");
});
test("HTML output escapes user input",()=>assert.equal(run("esc('<img src=x onerror=alert(1)>')"),"&lt;img src=x onerror=alert(1)&gt;"));
test("ChatGPT companion omits confidential fields unless selected",()=>{
 run("records=[normalize({rmaNumber:'SECRET-ID-55',customer:'PRIVATE CUSTOMER',description:'SECRET ISSUE',stage:'INTAKE'})];assistantId=records[0].id");
 const prompt=run("assistantPrompt()");
 assert.doesNotMatch(prompt,/SECRET-ID-55|PRIVATE CUSTOMER|SECRET ISSUE/);
 assert.match(prompt,/Current workflow stage/);
});
