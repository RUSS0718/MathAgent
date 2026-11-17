const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('../../node_modules/playwright');
const {expect}=require('../../node_modules/@playwright/test');
const dist=path.resolve(__dirname,'../../dist');
const output=path.resolve(process.argv[2]);fs.mkdirSync(output,{recursive:true});
const origin='http://terminal-plan-193.invalid';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
// Standalone test: build first, then pass an ignored output directory as argv[2].
// Every request is fulfilled locally or aborted; no server or provider is used.
const record={workspaceSha256:sha(fs.readFileSync(path.resolve(__dirname,'../../src/components/ChatWorkspace.vue'))),kind:'controlled synthetic Vue DOM fixture; NOT live04 or restarted service',source:require('child_process').execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),requests:[],assets:[],console:[],pageerror:[],cases:{}};
const progress={plan_version:1,steps:[{label:'S1',goal_summary:'自造目标：读取数字',current:true,reported:true},{label:'S2',goal_summary:'自造目标：检查数字',current:false,reported:false},{label:'S3',goal_summary:'自造目标：保存检查',verdict:'ACCEPT',valid:true},{label:'S4',goal_summary:'自造目标：复核分歧',verdict:'CHALLENGE',current:true}]};
const fixtureCases=[{name:'failed',status:'failed',phase:'needs_review',expected:['任务已结束，步骤结果未确认','历史记录：等待执行','步骤检查通过','发现问题']},{name:'canceled',status:'canceled',phase:'canceled',expected:['任务已结束，步骤结果未确认','历史记录：等待执行','步骤检查通过','发现问题']},{name:'success',status:'succeeded',phase:'completed',expected:['步骤检查通过','步骤检查通过']},{name:'unknown',status:'waiting_input',phase:'needs_review',expected:['结果未知','等待执行','步骤检查通过','发现问题']}];
(async()=>{const browser=await chromium.launch({headless:true});try{
for(const scenario of fixtureCases){const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'});try{
 const p=scenario.name==='success'?{plan_version:1,steps:[{label:'S1',goal_summary:'自造目标甲',current:true,verdict:'ACCEPT',valid:true},{label:'S2',goal_summary:'自造目标乙',verdict:'ACCEPT',valid:true}]}:progress;
 const result={execution_mode:'fake',presentation_mode:'solve',faithful:{phase:scenario.phase,allowed_actions:[]},solver:{state_revision:1,progress:p}};
 const job={success:true,job_id:'run-fixture',session_id:'session-fixture',status:scenario.status,last_event_id:0,result};
 await context.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());const log={case:scenario.name,method:req.method(),path:u.origin===origin?u.pathname:'[other origin]',action:'abort'};record.requests.push(log);
 if(u.origin!==origin||!['GET','HEAD','OPTIONS'].includes(req.method()))return route.abort('blockedbyclient');
 let body;
 if(u.pathname.startsWith('/dashboard/session/')){log.action='fulfill-local';return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(dist,'index.html'))});}
 if(u.pathname.startsWith('/dashboard-assets/assets/')){const rel=u.pathname.slice('/dashboard-assets/'.length);const file=path.resolve(dist,rel);if(!file.startsWith(path.resolve(dist)+path.sep)||!fs.existsSync(file))return route.abort();const bytes=fs.readFileSync(file);record.assets.push({case:scenario.name,path:u.pathname,bytes:bytes.length,sha256:sha(bytes)});log.action='fulfill-local';return route.fulfill({contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'application/octet-stream',body:bytes});}
 if(u.pathname==='/api/check_auth')body={isLoggedIn:true,username:'fixture-user',permissions:['dashboard.access']};
 else if(u.pathname==='/api/sessions')body=[['session-fixture',{preview:'自造非敏感题目',last_time:'2026-11-17 09:00'}]];
 else if(u.pathname==='/api/load_session')body={success:true,messages:[{sender:'user',text:'自造练习：观察数字1。',analysis_job_id:'run-fixture'}]};
 else if(u.pathname==='/api/capabilities')body={profile:'showcase',execution:{mode:'fake',provider:'synthetic',status:'available'},jobs:{enabled:true,status:'available'},sse:{enabled:true,status:'available'},verification_mode:['auto'],files:{upload:{enabled:false}},capabilities:{jobs:true,sse:true,verification_mode:['auto'],file_upload:{enabled:false}}};
 else if(u.pathname==='/api/agent/jobs/active')body={success:true,jobs:[]};
 else if(u.pathname==='/api/agent/jobs/run-fixture')body=job;
 else if(u.pathname==='/api/agent/jobs/run-fixture/answer')body={job_id:'run-fixture',status:scenario.status,mode:'solve',answer:scenario.name==='success'?'自造答复：数字为1。':'自造回退：结果尚未确认。',presentation_status:'ready',notice:'受控模拟数据，不证明真实求解能力。'};
 else if(u.pathname==='/api/agent/jobs/run-fixture/events'){log.action='fulfill-memory';const ev={type:'solver_progress',solver_revision:1,solver:{progress:p}};const tail=scenario.name==='unknown'?'id: 2\nevent: interrupt\ndata: {"type":"interrupt","status":"waiting_input"}\n\n':'';return route.fulfill({contentType:'text/event-stream',body:'id: 1\nevent: solver_progress\ndata: '+JSON.stringify(ev)+'\n\n'+tail});}
 else return route.abort('blockedbyclient');
 log.action='fulfill-memory';return route.fulfill({json:body});
 });
 const page=await context.newPage();page.on('console',m=>record.console.push({case:scenario.name,type:m.type(),text:m.text()}));page.on('pageerror',e=>record.pageerror.push({case:scenario.name,message:e.message}));
 const c=record.cases[scenario.name]={};await page.goto(origin+'/dashboard/session/session-fixture');
 await expect(page.locator('[aria-label="最终答复"]')).toBeVisible();
 async function openPlan(){const summary=page.locator('details.execution-process > summary');if(!await page.locator('details.execution-process').getAttribute('open')&&await page.locator('details.execution-process').getAttribute('open')!== ''){await summary.focus();await page.keyboard.press('Enter');}const plan=page.locator('aside[aria-label="求解计划"] > details');if(await plan.getAttribute('open')===null)await plan.locator(':scope > summary').click();await expect(plan.locator('ol li')).toHaveCount(scenario.expected.length);return plan;}
 let plan=await openPlan();c.keyboardExpanded=await page.locator('details.execution-process').getAttribute('open')!==null;
 for(const [size,width]of [['desktop',1440],['mobile',320]]){await page.setViewportSize({width,height:1000});const labels=await plan.locator('ol li > span').allTextContents();c[size]={labels,planVisible:await plan.isVisible(),overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)};c[size].matchesRequired=JSON.stringify(labels)===JSON.stringify(scenario.expected);await plan.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,scenario.name+'-'+size+'.png'),fullPage:true,mask:[page.locator('.sidebar')]});}
 await page.reload();plan=await openPlan();c.refreshLabels=await plan.locator('ol li > span').allTextContents();c.refreshMatchesRequired=JSON.stringify(c.refreshLabels)===JSON.stringify(scenario.expected);
 if(scenario.name==='failed') {await page.locator('details.replay-controls > summary').click();const slider=page.getByLabel('回放位置（不是求解进度）');await expect(slider).toHaveAttribute('max','1');await slider.focus();await page.keyboard.press('Home');await page.keyboard.press('End');await expect(plan.locator('ol li > span').first()).toHaveText('历史记录：执行中（结果未确认）');c.replayLabels=await plan.locator('ol li > span').allTextContents();expect(c.replayLabels).toEqual(['历史记录：执行中（结果未确认）','历史记录：等待执行','步骤检查通过','发现问题']);c.replayVisible=await page.locator('.workbench-toolbar').innerText();await plan.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'failed-replay.png'),fullPage:true,mask:[page.locator('.sidebar')]});}
 if(scenario.name==='failed'){await page.getByRole('button',{name:'返回任务状态',exact:true}).click();expect(await plan.locator('ol li > span').allTextContents()).toEqual(scenario.expected);}
 c.pass=c.keyboardExpanded&&c.desktop.planVisible&&c.mobile.planVisible&&!c.desktop.overflow&&!c.mobile.overflow&&c.desktop.matchesRequired&&c.mobile.matchesRequired&&c.refreshMatchesRequired;
}catch(e){record.cases[scenario.name]={...record.cases[scenario.name],pass:false,error:e.message};}finally{await context.close();}
}
}finally{await browser.close();record.guard={allHandledLocally:record.requests.every(x=>/^fulfill|abort$/.test(x.action)),nonGet:record.requests.filter(x=>!['GET','HEAD','OPTIONS'].includes(x.method)).length,aborted:record.requests.filter(x=>x.action==='abort'),externalNetworkDispatch:0,listenerStarted:false};fs.writeFileSync(path.join(output,'observations.json'),JSON.stringify(record,null,2));process.exitCode=Object.values(record.cases).every(c=>c.pass)&&record.guard.nonGet===0&&record.guard.aborted.length===0&&record.console.length===0&&record.pageerror.length===0?0:1;console.log(JSON.stringify({cases:record.cases,assets:[...new Map(record.assets.map(x=>[x.path,x])).values()],guard:record.guard,console:record.console,pageerror:record.pageerror},null,2));}})().catch(e=>{console.error(e.message);process.exitCode=1});

