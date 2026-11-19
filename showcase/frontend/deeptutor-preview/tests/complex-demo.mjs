import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {mkdir,readFile} from 'node:fs/promises'
const {chromium,expect}=createRequire(new URL('../../chat-frontend/package.json',import.meta.url))('@playwright/test')
const browser=await chromium.launch()
const out='../../../artifacts/deeptutor-complex-demo'
await mkdir(out,{recursive:true})
try {
  for(const width of [1280,390]) {
    const page=await browser.newPage({viewport:{width,height:width===390?844:800},reducedMotion:width===390?'reduce':'no-preference'})
    const api=[], errors=[]
    page.on('request',r=>{if(new URL(r.url()).origin!=='http://127.0.0.1:3090'||new URL(r.url()).pathname.startsWith('/api/')) api.push(r.url())}); page.on('pageerror',e=>errors.push(e.message))
    await page.goto('http://127.0.0.1:3090/dashboard')
    const dark=page.getByRole('button',{name:'切换到深色模式'})
    await expect(dark).toBeVisible({timeout:1200}); await dark.click(); await page.reload()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expect(page.getByRole('button',{name:'切换到浅色模式'})).toBeVisible()
    const field = page.getByRole('textbox',{name:'数学问题'})
    await field.fill('/exlpore'); await field.press('Enter')
    await expect(page.getByRole('main').getByRole('alert')).toContainText('题目',{timeout:2000})
    await page.locator('.suggestions').getByRole('button',{name:/四次方程/}).click()
    await expect(field).toHaveValue(/^\/explore /); await page.clock.install(); await page.clock.pauseAt(new Date(Date.now()+60000))
    await page.getByRole('button',{name:'发送',exact:true}).click()
    await page.getByRole('button',{name:'展开星图'}).click()
    const atlas=page.getByRole('dialog',{name:'协作星图',exact:true})
    for(let i=0;i<11;i++) {
      await expect(atlas.locator('.atlas-caption')).toContainText(i+1+' / 11')
      await expect(atlas.locator('.atlas-caption small')).toHaveText((i+1)+' / 11',{timeout:1500})
      if(i>0) await expect(atlas.locator('.atlas-link')).toHaveCount(1)
      if(i===3) {
        const before=await atlas.locator('.atlas').evaluate(el=>getComputedStyle(el).backgroundColor)
        await atlas.getByRole('button',{name:'切换到浅色模式'}).click()
        await expect(atlas.locator('.atlas-caption small')).toHaveText('4 / 11')
        assert.notEqual(await atlas.locator('.atlas').evaluate(el=>getComputedStyle(el).backgroundColor),before)
        await atlas.getByRole('button',{name:'切换到深色模式'}).click()
      }
      if(i===5){
        await expect(atlas.locator('.atlas-caption')).toContainText('步骤校验'); await expect(atlas.locator('.atlas-caption')).toContainText('反例')
        await expect(atlas.locator('.atlas-packet'))[width===390?'toBeHidden':'toBeVisible']()
        const arrival=atlas.getByRole('button',{name:'查看步骤校验阶段成果'}).locator('.atlas-arrival')
        await expect(atlas.locator('.atlas-arrival')).toHaveCount(1)
        if(width===390) await expect(arrival).toBeHidden()
        if(width===1280) {
          const flightTime=await atlas.locator('.atlas-packet').evaluate(el=>el.getAnimations()[0].effect.getTiming().duration)
          const samples=await arrival.evaluate((el,flight)=>{
            const pulse=el.getAnimations()[0]
            const {delay,duration}=pulse.effect.getTiming()
            pulse.pause()
            const opacityAt=t=>{pulse.currentTime=t;return Number(getComputedStyle(el).opacity)}
            return [delay===flight,opacityAt(delay-1),opacityAt(delay+duration/3)>0,opacityAt(delay+duration)]
          },flightTime)
          assert.deepEqual(samples,[true,0,true,0])
          const travelled = await atlas.locator('.atlas-packet').evaluate(el => {
            const animation = el.getAnimations()[0]
            animation.pause()
            animation.currentTime = 0
            const start = el.getBoundingClientRect()
            animation.currentTime = 1200
            const end = el.getBoundingClientRect()
            animation.play()
            return { dx:end.x-start.x, dy:end.y-start.y }
          })
          assert.ok(travelled.dx > 20 && travelled.dy > 30, '光点必须由右上方推理角色飞向右下方步骤校验角色')
        }
        await atlas.getByRole('button',{name:'暂停演示'}).click(); await page.clock.runFor(4000); await expect(atlas.locator('.atlas-caption')).toContainText('6 / 11')
        await page.screenshot({path:out+'/handoff-'+width+'.png'}); await atlas.getByRole('button',{name:'继续演示'}).click()
      }
      await page.clock.runFor(3300)
    }
    await expect(atlas.getByRole('button',{name:'重新播放'})).toBeVisible(); await atlas.getByRole('button',{name:'收起星图'}).click()
    await expect(page.getByRole('article')).toContainText('候选路线');
    await expect(page.getByRole('group',{name:'模拟答复模式'})).toHaveCount(0)
    await page.context().grantPermissions(['clipboard-read','clipboard-write'])
    for (const [mode,label] of [['report','报告'],['teach','教学'],['solve','求解']]) {
      await page.getByRole('main').getByRole('button',{name:'新建题目'}).click()
      await page.getByRole('combobox',{name:'输出模式'}).selectOption(mode)
      await page.locator('.suggestions').getByRole('button',{name:/四次方程/}).click()
      await page.getByRole('button',{name:'发送',exact:true}).click()
      for(let n=1;n<=11;n++) {
        await page.clock.runFor(3300)
        await expect(page.getByText(n+' / 11 步完成',{exact:true})).toBeVisible()
      }
      const article=page.getByRole('article',{name:label+'模拟答复'})
      await expect(article).toBeVisible()
      await expect(page.getByRole('article')).toHaveCount(1)
      if(mode==='report') {
        await article.getByRole('button',{name:'复制报告'}).click()
        await expect(article.getByRole('status')).toHaveText('报告已复制')
        const copied=await page.evaluate(()=>navigator.clipboard.readText())
        const downloadPromise=page.waitForEvent('download')
        await article.getByRole('button',{name:'导出 Markdown'}).click()
        const download=await downloadPromise
        assert.ok(download.suggestedFilename().endsWith('.md'))
        const content=await readFile(await download.path(),'utf8')
        assert.equal(content.replaceAll('\r\n','\n'),copied.replaceAll('\r\n','\n'))
        for(const section of ['## 题目','## 结论','## 推导依据','## 复核结果','## 检查范围','$$','模拟演示']) assert.ok(content.includes(section))
      } else await expect(article.getByRole('button',{name:'复制报告'})).toHaveCount(0)
      if(mode==='teach') { await article.getByText('展开提示').click(); await article.getByText('查看参考解答').click() }
      if(mode!=='solve') await article.screenshot({path:out+'/skill-'+mode+'-'+width+'.png'})
    }
    if(width===390) await page.getByRole('button',{name:'打开导航'}).click()
    await page.getByRole('button',{name:'参数四次方程的四根之谜 · 报告',exact:true}).click()
    await expect(page.getByRole('article',{name:'报告模拟答复'})).toBeVisible()
 await expect(page.getByRole('article').locator('.katex-error')).toHaveCount(0)
    await page.getByRole('button',{name:'重新播放'}).click(); await expect(page.locator('.atlas-caption')).toContainText('1 / 11'); await expect(page.getByRole('article')).toHaveCount(0)
    assert.deepEqual(api,[]);assert.deepEqual(errors,[]);await page.close();console.log(width+'px passed')
  }
} finally { await browser.close() }
