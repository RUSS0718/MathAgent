import { expect, test } from '@playwright/test'
import { mockWorkspace } from './fixtures'
test('ordinary task defaults to the full star map and preserves accessible role selection', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await mockWorkspace(page, true)
  await page.goto('/dashboard-assets/session/session-demo')
  const map = page.locator('.constellation:not(.mini)')
  await expect(map).toBeVisible()
  await expect(map.locator('.orbit')).toHaveCount(3)
  const role = map.locator('button[data-role-state]').first()
  await map.getByRole('button', { name: '完整星图动效' }).click()
  await expect(map).toHaveClass(/motion-off/)
  await role.click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(role).toBeFocused()
  await expect(role).toHaveAttribute('aria-pressed', 'false')
  await expect(page.locator('.constellation:visible')).toHaveCount(1)
  await page.screenshot({ path: '../../../artifacts/constellation-refresh/desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: '../../../artifacts/constellation-refresh/mobile.png', fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('session search has recoverable empty state', async ({ page }) => {
  await mockWorkspace(page, true)
  await page.goto('/dashboard-assets/session/session-demo')
  const search = page.getByRole('searchbox', { name: '搜索会话' })
  await search.fill('不存在的题目')
  await expect(page.getByText('没有匹配的会话')).toBeVisible()
  await search.fill('多项式')
  await expect(page.locator('.session-row')).toHaveCount(1)
})

test('mini roles never overlap at desktop and narrow widths', async ({ page }) => {
  await mockWorkspace(page, true)
  await page.goto('/dashboard-assets/session/session-demo')
  await page.getByRole('button', { name: '关键进展', exact: true }).click()
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    const buttons = page.locator('.constellation.mini button')
    const boxes = await buttons.evaluateAll(nodes => nodes.map(n => { const r = n.getBoundingClientRect(); return { x:r.x,y:r.y,right:r.right,bottom:r.bottom } }))
    for (let i=0;i<boxes.length;i++) for(let j=i+1;j<boxes.length;j++) {
      const a=boxes[i]!, b=boxes[j]!
      expect(a.right <= b.x || b.right <= a.x || a.bottom <= b.y || b.bottom <= a.y).toBe(true)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
})

test('late messages follow SVG coordinates and respect motion controls', async ({ page }) => {
  await mockWorkspace(page)
  await page.goto('/dashboard-assets/session/session-demo')
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.evaluate(async () => {
    // Mount the real component through Vite; no production test hooks or provider calls.
    const vue = await import(/* @vite-ignore */ '/dashboard-assets/node_modules/.vite/deps/vue.js')
    const { default: Map } = await import(/* @vite-ignore */ '/dashboard-assets/src/components/AgentConstellation.vue')
    const messages = vue.ref([])
    const host = document.createElement('div')
    host.id = 'motion-fixture'
    host.style.cssText = 'position:fixed;inset:0;background:white;z-index:9999;width:1000px'
    document.body.append(host)
    vue.createApp({ render: () => vue.h(Map, { selected:'',roleStates:{},messages:messages.value,flights:messages.value.map(handoff => handoff.message) }) }).mount(host)
    ;(window as any).appendMessage = () => messages.value.push({
      message: { message_id: 'late', from_role: 'controller', to_role: 'planner', summary: '公开交接测试' },
      action: '交接', tone: 'handoff', order: 1,
    })
  })
  await page.evaluate(() => (window as any).appendMessage())
  const map = page.locator('#motion-fixture')
  await expect(map.locator('.message-flight')).toHaveCount(6)
  const distance = await map.locator('.message-flight').first().evaluate(node => {
    const animation = node.getAnimations()[0]!
    animation.pause(); animation.currentTime = 800
    const circle = node as SVGGraphicsElement
    const wire = node.parentElement!.querySelector('.message-highlight') as SVGPathElement
    const p = wire.getPointAtLength(wire.getTotalLength()/2)
    const expected = new DOMPoint(p.x,p.y).matrixTransform(wire.getScreenCTM()!)
    const actual = new DOMPoint(0,0).matrixTransform(circle.getScreenCTM()!)
    return Math.hypot(actual.x-expected.x,actual.y-expected.y)
  })
  expect(distance).toBeLessThan(3)
  await map.getByRole('button', { name:'完整星图动效' }).focus()
  await page.keyboard.press('Space')
  await expect(map.locator('.message-flight').first()).toBeHidden()
  await page.keyboard.press('Space')
  await page.emulateMedia({ reducedMotion:'reduce' })
  await expect(map.locator('.message-flight').first()).toBeHidden()
  await expect(map.locator('.message-wire')).toBeVisible()
})

test('empty entry examples and keyboard submission work at narrow widths', async ({ page }) => {
  await mockWorkspace(page)
  await page.goto('/dashboard-assets/session/session-demo')
  for (const width of [1440,390,320]) {
    await page.setViewportSize({width,height:1000})
    await page.screenshot({path:`../../../artifacts/constellation-refresh/empty-${width}.png`,fullPage:true})
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.getByRole('button', {name:/方程与候选根/}).click()
  const input=page.getByRole('textbox', {name:'数学问题'})
  await expect(input).toHaveValue('解方程 x² − 5x + 6 = 0，并验证候选根。')
  await input.press('End')
  await input.press('Shift+Enter')
  await expect(input).toHaveValue(/\n/)
  const request=page.waitForRequest(r=>r.url().endsWith('/api/agent/jobs') && r.method()==='POST')
  await input.press('Enter')
  await request
})


async function mountLiveWorkbench(page: import('@playwright/test').Page) {
  await mockWorkspace(page)
  await page.goto('/dashboard-assets/session/session-demo')
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.evaluate(async () => {
    const vue = await import(/* @vite-ignore */ '/dashboard-assets/node_modules/.vite/deps/vue.js')
    const { default: Workbench } = await import(/* @vite-ignore */ '/dashboard-assets/src/components/ConversationWorkbench.vue')
    const events = vue.ref([])
    let id = 0
    const host = document.createElement('div')
    host.id = 'live-fixture'
    host.style.cssText = 'position:absolute;inset:0;background:var(--background);z-index:9999'
    host.append(document.createTextNode('SYNTHETIC · 合成公开事件，仅用于界面验收'))
    const mount = document.createElement('div'); host.append(mount); document.body.append(host)
    vue.createApp({ render: () => vue.h(Workbench, { events:events.value,status:'running',animateLive:true }) }).mount(mount)
    ;(window as any).pushBatch = (ids: string[]) => {
      events.value.push(...(ids.length ? ids : [null]).map(message_id => ({ id:++id,event:'solver_progress',data:{type:'solver_progress', solver_event_type:'step_reported', step_id:`步骤 ${id}`, ...(message_id ? {workbench:{message_id,thread_id:'synthetic',from_role:'controller',to_role:'planner',kind:'reply',summary:'合成消息',plan_version:0,attempt_index:0}} : {})} })))
    }
  })
  await page.locator('#live-fixture').getByRole('button', {name:'完整星图',exact:true}).click()
}

test('live event batches retain independent lifetimes and deduplicate messages', async ({page}) => {
  await mountLiveWorkbench(page)
  await page.clock.install()
  const map=page.locator('#live-fixture .constellation:not(.mini)')
  const wires=map.locator('[data-flight]')
  await page.evaluate(() => (window as any).pushBatch(['first']))
  await page.clock.runFor(150)
  await expect(wires).toHaveCount(1)
  await page.clock.runFor(700)
  await page.evaluate(() => (window as any).pushBatch(['second','first']))
  await page.clock.runFor(150)
  await expect(wires).toHaveCount(2)
  await page.evaluate(() => (window as any).pushBatch([]))
  await page.clock.runFor(150)
  await expect(wires).toHaveCount(2)
  await page.clock.runFor(1000)
  await expect(wires).toHaveCount(2)
  await page.clock.runFor(500)
  await expect(wires).toHaveCount(1)
  await page.clock.runFor(900)
  await expect(wires).toHaveCount(0)
  await page.evaluate(() => (window as any).pushBatch(Array.from({length:15},(_,i)=>`burst-${i}`)))
  await page.clock.runFor(150)
  await expect(wires).toHaveCount(15)
  await expect(map.locator('.message-wire')).toHaveCount(1)
})

test('motion preferences and view changes preserve paths without replaying a flight', async ({ page }) => {
  await mountLiveWorkbench(page)
  const host = page.locator('#live-fixture')
  const toggle = host.getByRole('button', { name: '完整星图动效' })
  const flights = host.locator('[data-flight]')
  await page.evaluate(() => (window as any).pushBatch(['handoff']))
  await expect(flights).toHaveCount(1)
  await toggle.click()
  await expect(flights).toHaveCount(0)
  await expect(host.locator('.message-wire')).toBeVisible()
  await toggle.click()
  await expect(flights).toHaveCount(0)
  await host.getByRole('button', { name: '关键进展' }).click()
  await page.evaluate(() => (window as any).pushBatch(['while-hidden']))
  await expect(host.locator('.conversation-events > li')).toHaveCount(2)
  await host.getByRole('button', { name: '完整星图', exact: true }).click()
  await expect(flights).toHaveCount(0)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect(toggle).toBeDisabled()
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')
  await page.evaluate(() => (window as any).pushBatch(['reduced']))
  await expect(host.locator('.message-wire')).toBeVisible()
  await expect(flights).toHaveCount(0)
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await expect(toggle).toBeEnabled()
  await expect(flights).toHaveCount(0)
  await expect(host.locator('.message-wire')).toBeVisible()
})

test('opening the graph during batching does not animate a handoff received while hidden', async ({ page }) => {
  await mountLiveWorkbench(page)
  const time = new Date('2026-11-18T04:00:00Z')
  await page.clock.install({ time })
  await page.clock.pauseAt(new Date(time.valueOf() + 1000))
  const host = page.locator('#live-fixture')
  const view = (name: string) => host.getByRole('button', { name, exact: true })
  await view('关键进展').evaluate(button => button.click())
  await page.evaluate(() => (window as any).pushBatch(['hidden-before-flush']))
  await view('完整星图').evaluate(button => button.click())
  await page.clock.runFor(150)
  await expect(host.locator('.message-wire')).toBeVisible()
  await expect(host.locator('[data-flight]')).toHaveCount(0)
})

for (const width of [320,390]) test(`full map coordinates and readable bounds at ${width}`, async ({page}) => {
  await mockWorkspace(page,true)
  await page.setViewportSize({width,height:1000})
  await page.goto('/dashboard-assets/session/session-demo')
  await page.getByRole('button',{name:'完整星图',exact:true}).click()
  const map=page.locator('.constellation:not(.mini)')
  const geometry=await map.evaluate(el=>{
    const svg=el.querySelector('svg')!, outer=el.getBoundingClientRect()
    const buttons=Array.from(el.querySelectorAll<HTMLButtonElement>('button:not(.motion-toggle)'))
    const boxes=buttons.map(b=>b.getBoundingClientRect())
    const allBoxes=Array.from(el.querySelectorAll('button')).map(b=>b.getBoundingClientRect())
    return {
      errors:buttons.map((b,i)=>{ const p=new DOMPoint(parseFloat(b.style.left)*10,parseFloat(b.style.top)*7).matrixTransform(svg.getScreenCTM()!); const r=boxes[i]!; return Math.hypot(p.x-r.x-r.width/2,p.y-r.y-r.height/2) }),
      clipped:boxes.some(r=>r.left<outer.left || r.right>outer.right || r.top<outer.top || r.bottom>outer.bottom),
      overlaps:allBoxes.some((a,i)=>allBoxes.some((b,j)=>i<j && a.left<b.right+8 && b.left<a.right+8 && a.top<b.bottom+8 && b.top<a.bottom+8)),
    }
  })
  expect(Math.max(...geometry.errors)).toBeLessThan(1)
  expect(geometry.clipped).toBe(false)
  expect(geometry.overlaps).toBe(false)
  const selected=map.locator('button:not(.motion-toggle)').first()
  await selected.click()
  await selected.focus()
  expect(await selected.evaluate(b=>{
    const r=b.getBoundingClientRect(), outer=b.parentElement!.getBoundingClientRect(), style=getComputedStyle(b)
    const margin=parseFloat(style.outlineWidth)+parseFloat(style.outlineOffset)
    return margin>0 && r.left-margin>=outer.left && r.right+margin<=outer.right && r.top-margin>=outer.top && r.bottom+margin<=outer.bottom
  })).toBe(true)
  await map.screenshot({path:`../../../artifacts/constellation-refresh/full-map-${width}.png`})
})

for (const width of [320,390]) test(`arrival ripple is exposed outside the target button at ${width}`, async ({page})=>{
  await page.setViewportSize({width,height:1000})
  await mountLiveWorkbench(page)
  await page.clock.install()
  await page.evaluate(()=>(window as any).pushBatch(['arrival-proof']))
  await page.clock.runFor(150)
  const ripple=page.locator('#live-fixture .constellation:not(.mini) .arrival')
  await page.clock.runFor(1700)
  await expect(ripple).toBeVisible()
  const visible=await ripple.evaluate(el=>{
    // Sample the arrival phase deterministically; the timer assertion above
    // independently checks that the live queue has not removed this message.
    const a=el.getAnimations()[0]!; a.pause(); a.currentTime=2000
    const circle=el as SVGCircleElement, matrix=circle.getScreenCTM()!
    const points=Array.from({length:36},(_,i)=>{
      const angle=i*Math.PI/18
      return new DOMPoint(circle.cx.baseVal.value+circle.r.baseVal.value*Math.cos(angle),circle.cy.baseVal.value+circle.r.baseVal.value*Math.sin(angle)).matrixTransform(matrix)
    })
    const exposed=points.filter(p=>document.elementFromPoint(p.x,p.y)===el).length
    return {opacity:Number(getComputedStyle(el).opacity),width:el.getBoundingClientRect().width,exposed}
  })
  expect(visible.opacity).toBeGreaterThan(.1)
  expect(visible.width).toBeGreaterThan(10)
  expect(visible.exposed).toBeGreaterThan(0)
  await page.locator('#live-fixture .constellation:not(.mini)').screenshot({path:`../../../artifacts/constellation-refresh/ripple-${width}.png`})
})
