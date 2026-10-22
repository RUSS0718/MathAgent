/* Same request contracts; errors remain plain text, never injected HTML. */
const form = document.getElementById('problem-form')
const button = form.querySelector('button')
const input = document.getElementById('problem')
const result = document.getElementById('result')
const state = document.getElementById('state')

async function request(url, init) {
  const response = await fetch(url, init)
  const body = await response.json()
  if (!response.ok) throw new Error(body.error || '服务暂不可用')
  return body
}

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  if (!input.value.trim() || button.disabled) return
  button.disabled = true
  form.setAttribute('aria-busy', 'true')
  state.textContent = '处理中…'
  try {
    const init = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ problem: input.value.trim() }) }
    if (document.body.dataset.page === 'demo') {
      result.textContent = JSON.stringify(await request('/solve', init), null, 2)
      state.textContent = '请求完成，请核对公开结果。'
    } else {
      const created = await request('/api/runs', init)
      const events = await request('/api/runs/' + encodeURIComponent(created.run_id) + '/events')
      const evidence = await request('/api/runs/' + encodeURIComponent(created.run_id) + '/evidence')
      state.textContent = (created.execution_mode || 'unavailable') + ' / ' + created.status + ' / ' + created.stage
      result.textContent = JSON.stringify({ run: created, events, evidence }, null, 2)
    }
  } catch (error) {
    state.textContent = '请求失败，可重试。'
    result.textContent = error instanceof Error ? error.message : String(error)
  } finally {
    button.disabled = false
    form.removeAttribute('aria-busy')
  }
})
