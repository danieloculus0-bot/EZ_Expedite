"use strict";
const {readFileSync}=require("node:fs");
const {test}=require("node:test");
const assert=require("node:assert/strict");
const vm=require("node:vm");
const html=readFileSync("web-rma/index.html","utf8");
const js=html.match(/<script>([\s\S]+?)<\/script>/)?.[1];
assert.ok(js,"App must contain a browser script");
const stub={getElementById(){return {value:"",checked:false}}};
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
test("closed RMAs leave the default queue while remaining accessible in history",()=>{
 assert.match(html,/<option value="open" selected>Open<\/option>/);
 assert.match(html,/data-close=/);
 assert.match(html,/data-delete=/);
 assert.match(html,/id="deleteBtn"/);
 assert.match(js,/indexedDB\.open\("EZ_RMA_Local",2\)/);
});
test("manual closure requires a reason, preserves audit trail and supports deletion",async()=>{
 sandbox.structuredClone=structuredClone;
 sandbox.confirm=()=>true;
 sandbox.prompt=()=>null;
 run("render=()=>{};notify=()=>{};showEditor=()=>{};hideEditor=()=>{};persist=async()=>{};deletePersisted=async()=>{};records=[normalize({caseNumber:'RMA-2026-0001',stage:'INTAKE'})]");
 assert.equal(await run("closeRecord(records[0])"),false);
 assert.equal(run("records[0].closedAt"),"");
 sandbox.prompt=()=>"Cancelled test case, no customer return";
 assert.equal(await run("closeRecord(records[0])"),true);
 assert.equal(run("records[0].stage"),"COMPLETE");
 assert.equal(run("records[0].preCloseStage"),"INTAKE");
 assert.equal(run("records[0].manualClosure"),true);
 assert.equal(run("records[0].log.some(e=>e.kind==='CLOSED - OVERRIDE')"),true);
 assert.equal(run("records.filter(r=>!r.closedAt).length"),0);
 sandbox.confirm=()=>false;
 assert.equal(await run("deleteRecord(records[0])"),false);
 assert.equal(run("records.length"),1);
 sandbox.confirm=()=>true;
 assert.equal(await run("deleteRecord(records[0])"),true);
 assert.equal(run("records.length"),0);
});


test("AI assistant and external call code fully removed",()=>{
 assert.doesNotMatch(html,/ChatGPT|OpenAI|Assistant|aiPreview|gateway|assistantSend|assistantToNote|chatBtn|caseAssistantBtn/i);
 assert.doesNotMatch(js,/fetch\s*\(/);
 assert.match(js,/indexedDB\.open/);
 assert.match(html,/id="closeBtn"/);
 assert.match(html,/id="deleteBtn"/);
});
