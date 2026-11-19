import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile } from 'node:fs/promises'
import { mockWorkspace } from '../../chat-frontend/tests/browser/fixtures.ts'
const { chromium, expect } = createRequire(new URL('../../chat-frontend/package.json', import.meta.url))('@playwright/test')
const base = process.env.SHOWCASE_URL ?? 'http://127.0.0.1:8090'
const browser = await chromium.launch()
async function scenario(name, run) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, reducedMotion: 'reduce' })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  try {
    await mockWorkspace(page, true, '')
    await run(page)
    assert.deepEqual(errors, [])
    console.log('PASS', name)
  } finally { await page.close() }
}
const saved = { job_id: 'run-demo', session_id: 'session-demo', status: 'succeeded', success: true }
const answer = { job_id: saved.job_id, status: 'succeeded', mode: 'solve', presentation_status: 'ready', answer: '原会话答案 x = 4', notice: '已代回检查。' }
const caps = { profile: 'showcase', jobs: { enabled:true, status:'available' }, sse: { enabled:true, status:'available' }, files: { upload: { enabled:true, max_bytes:131072 } } }
const button = (page, name) => page.getByRole('button', { name, exact:true })
try {
  await scenario('首页、别名和已保存会话共用一个工作台', async page => {
    const writes = [], reads = []
    page.on('request', req => {
      if (req.method() === 'POST') writes.push(req.url())
      if (req.url().includes('/api/load_session?')) reads.push(new URL(req.url()).searchParams.get('session'))
    })
    for (const path of ['/', '/dashboard', '/dashboard/', '/dashboard/chat', '/dashboard/workspace', '/dashboard-assets/index.html']) {
      await page.goto(base + path)
      await expect(page.getByRole('navigation',{name:'工作台导航'})).toBeVisible()
      await expect(page.getByLabel('数学问题')).toBeVisible()
    }
    await page.route('**/api/agent/jobs/run-demo/answer', r => r.fulfill({ json: answer }))
    await page.locator('.saved-session-row').getByRole('button',{name:'多项式候选根验证',exact:true}).click()
    await expect(page).toHaveURL(base + '/dashboard/session/session-demo')
    await expect(page.getByRole('region',{name:'最终答复'})).toContainText(answer.answer)
    await page.goto(base + '/dashboard-assets/session/session-demo')
    await expect(page).toHaveURL(base + '/dashboard/session/session-demo')
    await expect(page.getByRole('region',{name:'最终答复'})).toContainText(answer.answer)
    await button(page,'切换到深色模式').click(); await page.reload()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expect(page.getByRole('region',{name:'最终答复'})).toContainText(answer.answer)
    await button(page,'新建题目').click(); await expect(page.getByLabel('数学问题')).toBeVisible()
    assert.ok(reads.length >= 2); assert.ok(reads.every(id => id === saved.session_id)); assert.deepEqual(writes, [])
  })
  await scenario('旧题图书签读取同一会话', async page => {
    const writes = []
    page.on('request', r => { if (r.method() === 'POST') writes.push(r.url()) })
    await page.route('**/api/agent/jobs/run-demo/answer', r => r.fulfill({json:answer}))
    await page.goto(base+'/dashboard#image/run/run-demo')
    await expect(page).toHaveURL(base+'/dashboard/session/session-demo')
    await expect(page.getByRole('region',{name:'最终答复'})).toContainText(answer.answer)
    assert.deepEqual(writes,[])
  })
  await scenario('仅按本任务允许的动作补条件', async page => {
    const writes = []; let answered = false
    const state = { phase:'clarification', allowed_actions:['answer_clarification'], clarification:{ task_id:'run-demo', request_id:'req-demo', input_version:2, status:'waiting', question:'对应的高是多少？', reason:'已有底边。' } }
    await page.route('**/api/agent/jobs/run-demo', r => r.fulfill({json: answered ? saved : {...saved,status:'waiting_input', result:{ faithful:state }}}))
    await page.route('**/api/agent/jobs/run-demo/answer', r => r.fulfill({json: answered ? answer : {...answer, status:'waiting_input',answer:'',presentation_status:'pending'}}))
    await page.route('**/api/agent/jobs/run-demo/clarifications/req-demo', r => {
      assert.deepEqual(r.request().postDataJSON(),{task_id:'run-demo',input_version:2,answer:'高为 5 厘米'})
      assert.ok(r.request().headers()['idempotency-key']); assert.ok(r.request().headers()['x-csrf-token']); answered=true
      return r.fulfill({json:saved})
    })
    page.on('request', r=>{if(r.method()==='POST')writes.push(new URL(r.url()).pathname)})
    await page.goto(base + '/dashboard/session/session-demo')
    await expect(page.getByText('对应的高是多少？')).toBeVisible()
    await expect(button(page,'恢复执行')).toHaveCount(0)
    await page.getByLabel('补充条件',{exact:true}).fill('高为 5 厘米'); await button(page,'回答并继续').click()
    await expect(page.getByRole('region',{name:'最终答复'})).toContainText(answer.answer)
    assert.deepEqual(writes,['/api/agent/jobs/run-demo/clarifications/req-demo'])
  })
  await scenario('题图能力开关、大小限制、提交中断恢复与报告', async page => {
    const uploads=[], requests=[], lookups=[]; let enabled=false
    await page.route('**/api/capabilities', r => r.fulfill({json:{...caps,files:{upload:{enabled,max_bytes:131072}}}}))
    await page.route('**/api/upload_file', r => { uploads.push(r.request().method()); return r.fulfill({json:{file:{file_id:'file-demo'}}}) })
    await page.route('**/api/files', r=>r.fulfill({json:[]}))
    await page.route('**/api/agent/jobs',r=>{requests.push({key:r.request().headers()['idempotency-key'],body:r.request().postDataJSON()}); return r.abort('failed')})
    await page.route('**/api/agent/submissions/*',r=>{lookups.push(new URL(r.request().url()).pathname.split('/').pop()); return r.fulfill({json:saved})})
    await page.route('**/api/agent/jobs/run-demo/answer', r => r.fulfill({json:answer}))
    await page.goto(base + '/dashboard#image')
    await expect(page.getByText('当前工作台未开启题图上传。')).toBeVisible()
    enabled=true; await page.reload()
    await page.getByLabel('选择 PNG 题图').setInputFiles({name:'过大.png',mimeType:'image/png',buffer:Buffer.alloc(131073)})
    await expect(page.getByRole('alert')).toContainText('128 KiB'); await expect(button(page,'发送题图')).toBeDisabled()
    await button(page,'使用示例题图').click(); await expect(page.getByAltText('待提交的题图')).toBeVisible()
    await page.getByLabel('补充要求（可选）').fill('请代回。'); await page.getByLabel('题图输出模式').selectOption('report')
    await button(page,'发送题图').click(); await expect(page.getByRole('alert')).toBeVisible()
    await expect(page).toHaveURL(/#image\/pending\//); await page.reload(); assert.equal(requests.length,1)
    await button(page,'核对原提交').click(); await expect(page).toHaveURL(base+'/dashboard/session/session-demo')
    await page.reload(); await expect(page.getByRole('heading',{name:'最终答复 · 报告'})).toBeVisible()
    await page.context().grantPermissions(['clipboard-read','clipboard-write'])
    await button(page,'复制报告').click(); await expect(page.getByText('报告已复制')).toBeVisible()
    const downloaded=page.waitForEvent('download'); await button(page,'导出 Markdown').click()
    const file=await downloaded; const text=await readFile(await file.path(),'utf8')
    assert.equal(text,(await page.evaluate(()=>navigator.clipboard.readText())).replaceAll('\r\n','\n')); assert.ok(text.includes(answer.answer))
    assert.deepEqual(uploads,['POST']); assert.equal(requests.length,1); assert.equal(requests[0].body.input_user_file_id,'file-demo')
    assert.match(requests[0].body.message,/请代回。.*求解报告/s); assert.deepEqual(lookups,[requests[0].key])
  })
  await scenario('手输题目走服务，选择示例走演示', async page => {
    let sent
    await page.route('**/api/agent/jobs', r=>{sent=r.request().postDataJSON();return r.fulfill({json:saved})})
    await page.route('**/api/agent/jobs/run-demo/answer',r=>r.fulfill({json:answer}))
    await page.goto(base+'/dashboard'); await page.getByLabel('数学问题').fill('解方程 3x = 12'); await button(page,'发送').click()
    await expect(page).toHaveURL(base+'/dashboard/session/session-demo'); await expect(page.getByRole('region',{name:'最终答复'})).toContainText('x = 4')
    assert.equal(sent.message,'解方程 3x = 12'); assert.equal(sent.input_user_file_id,undefined)
    sent = undefined
    await button(page,'新建题目').click()
    await page.locator('.suggestions').getByRole('button',{name:/四次方程/}).click()
    await button(page,'发送').click()
    await expect(page.locator('.atlas')).toBeVisible(); assert.equal(sent,undefined)
  })
} finally { await browser.close() }
