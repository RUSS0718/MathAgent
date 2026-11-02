import type { ResultSemantics } from '../../api/result-semantics.schemas'

/** Translate only explicit product observations; never infer them from unknown. */
export function describeResultSemantics(value: ResultSemantics): string {
  const execution = { queued: '任务排队中', running: '任务运行中', waiting_input: '任务等待补充', completed: '任务完成', needs_review: '任务需要复核', failed: '任务执行失败', canceled: '任务已取消' }
  const transport = { known: '传输结果已知', unknown: '远端请求结果未知，需要人工决定', pending: '请求进行中，结果尚未返回', unavailable: '传输记录不可用' }
  const review = { accepted: 'LLM 整题审查通过', rejected: 'LLM 整题审查拒绝', not_reviewed: '尚无整题审查', invalid_source: '整题审查来源无效' }
  const binding = { same_artifact: '绑定一致', artifact_changed: '文本已改写，旧审查不适用于当前答案', unbound: '未绑定有效整题审查' }
  const parts = [execution[value.execution], transport[value.transport], review[value.whole_review], binding[value.binding], '未作形式化验证']
  if (value.verification_requirement === 'required_unmet') parts.push('required 模式的额外验证要求尚未满足')
  return parts.join('；')
}
