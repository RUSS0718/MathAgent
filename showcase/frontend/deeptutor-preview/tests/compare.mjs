// Run from the preview directory with both frontends started (see UPSTREAM.md).
import { createRequire } from 'node:module'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import assert from 'node:assert/strict'
import { mockWorkspace, report } from '../../chat-frontend/tests/browser/fixtures.ts'
import { examples } from '../lib/examples.ts'
const requireVue = createRequire(new URL('../../chat-frontend/package.json', import.meta.url))
const { chromium, expect } = requireVue('@playwright/test')
const sharp = createRequire(import.meta.url)('sharp')
const out = resolve('../../../artifacts/deeptutor-ui-stage1')
await mkdir(out, { recursive: true })
const browser = await chromium.launch()
const question = examples[0].question
const frame = (id, role, action, summary) => 'id: '+id+'\nevent: solver_progress\ndata: '+JSON.stringify({type:'solver_progress', role, solver_event_type:action, summary, evidence_kind:'scripted', solver_revision:id})+'\n\n'
const runningEvents = frame(1,'planner','initial_plan_generated','制定求解计划') + frame(2,'reasoner','step_reported',examples[0].method)
const doneEvents = runningEvents + frame(3,'step_verifier','step_reviewed',examples[0].check)+'id: 4\nevent: final_result\ndata: {"type":"final_result","status":"succeeded"}\n\n'
try {
  for (const [width,height] of [[1280,720],[390,844]]) {
    const context = await browser.newContext({viewport:{width,height},locale:'zh-CN',timezoneId:'Asia/Shanghai',reducedMotion:'reduce',colorScheme:'light'})
    const page = await context.newPage()
    const errors = [], requests = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', req => { if (new URL(req.url()).origin !== 'http://127.0.0.1:3090' || req.url().includes('/api/')) requests.push(req.url()) })
    await page.goto('http://127.0.0.1:3090/dashboard')
    await page.clock.install({ time:new Date('2026-11-19T10:00:00+08:00') })
    await page.clock.pauseAt(new Date('2026-11-19T10:01:00+08:00'))
    const shot = async (pg,side,state) => { await pg.evaluate(() => document.fonts.ready); await pg.screenshot({path:resolve(out,[side,width,state].join('-')+'.png'),animations:'disabled'}) }
    const input = page.getByRole('textbox',{name:'数学问题'})
    await input.fill('任意问题'); await input.press('Enter'); await expect(page.getByRole('main').getByRole('alert')).toBeVisible()
    await page.locator('.suggestions button').first().click(); await expect(input).toHaveValue(question)
    await input.dispatchEvent('compositionstart'); await input.press('Enter'); await expect(input).toBeVisible(); await input.dispatchEvent('compositionend'); await page.clock.runFor(16)
    await input.fill(question); await shot(page,'preview','new'); await input.press('Enter')
    await page.clock.runFor(1300); await expect(page.getByText('1 / 3 步完成')).toBeVisible(); await shot(page,'preview','running')
    await page.clock.runFor(1300); await expect(page.getByText('2 / 3 步完成')).toBeVisible(); await page.clock.runFor(1300); await expect(page.getByRole('article')).toContainText(examples[0].check); await shot(page,'preview','done')
    const expand = page.getByRole('button', {name:'展开星图'})
    await expect(expand).toBeVisible()
    await expand.click()
    const atlas = page.getByRole('dialog', {name:'协作星图', exact:true})
    await expect(atlas.getByRole('group').getByRole('button')).toHaveCount(9)
    const verifier = atlas.getByRole('button', {name:'查看步骤校验阶段成果'})
    await verifier.click()
    await expect(atlas.getByRole('dialog')).toContainText(examples[0].scope)
    await page.keyboard.press('Escape'); await expect(verifier).toBeFocused()
    await shot(page,'atlas','expanded')
    await page.keyboard.press('Escape'); await expect(expand).toBeFocused()
    const role = page.getByRole('button',{name:'查看推理阶段成果'}); await role.click(); await expect(page.getByRole('dialog')).toContainText(examples[0].method); await page.keyboard.press('Escape'); await expect(role).toBeFocused()
    await page.getByRole('button',{name:'关键进展'}).click(); const row = page.getByRole('button',{name:/检查候选结果/}); await row.focus(); await row.press('Enter'); await expect(row).toHaveAttribute('aria-expanded','true'); await page.getByRole('button',{name:'阶段成果',exact:true}).click(); await expect(page.getByRole('dialog')).toContainText(examples[0].check)
    await shot(page,'preview','drawer'); await page.keyboard.press('Escape'); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false)
    if(width < 720){const menu=page.getByRole('button',{name:'打开导航'}); await menu.click(); await expect(page.getByRole('dialog')).toContainText('示例题库'); await page.keyboard.press('Escape'); await expect(menu).toBeFocused()}
    await expect(page.locator('.answer .result .katex-html')).toContainText('或')
    await page.getByRole('main').getByRole('button',{name:'新建题目'}).click()
    await page.locator('.suggestions button').nth(1).click(); await page.getByRole('button',{name:'发送'}).click()
    for (const n of [1,2,3]) {
      await page.clock.runFor(1300); await expect(page.getByText(n+' / 3 步完成')).toBeVisible()
    }
    await expect(page.locator('.answer .result .katex-html')).toContainText('50×101=5050')
    assert.deepEqual(errors,[]); assert.deepEqual(requests,[])
    for (const state of ['new','running','done']) {
      const old=await context.newPage(); const running=state==='running'; await mockWorkspace(old,state!=='new',running?runningEvents:doneEvents)
      await old.route('**/api/agent/jobs/run-demo',r=>r.fulfill({json:{success:true,job_id:'run-demo',session_id:'session-demo',status:running?'running':'succeeded',last_event_id:0,result:{execution_mode:'fake'}}}))
      await old.route('**/api/agent/jobs/run-demo/answer',r=>r.fulfill({json:{job_id:'run-demo',mode:'solve',status:running?'running':'succeeded',presentation_status:running?'pending':'ready',answer:running?'':report.report.answer,notice:examples[0].scope}}))
      await old.goto('http://127.0.0.1:4190/dashboard-assets/'+(state==='new'?'':'session/session-demo'))
      if(state==='new') await old.getByRole('textbox',{name:'数学问题',exact:true}).fill(question)
      else { await expect(old.locator('.workbench-problem')).toContainText(question); if (!running) await expect(old.getByRole('region',{name:'最终答复'})).toContainText('因式分解') }
      await shot(old,'vue',state); await old.close()
      await sharp({create:{width:width*2,height,channels:3,background:'white'}}).composite(['vue','preview'].map((side,i)=>({input:resolve(out,[side,width,state].join('-')+'.png'),left:width*i,top:0}))).png().toFile(resolve(out,'compare-'+width+'-'+state+'.png'))
    }
    await context.close(); console.log(width+'px: interactions and three comparisons passed')
  }
} finally { await browser.close() }
