import type { Example } from './examples'

export const triangleQuestion = '求这个三角形的数值面积。'
export const triangleTitle = '三角形面积条件补充'

export function triangleResult(base: number, height: number): Example {
  const area = Number((base * height / 2).toPrecision(12))
  return {
    title: triangleTitle, subject: '条件澄清', question: `${triangleQuestion} 底为 ${base} 厘米，对应的高为 ${height} 厘米。`,
    method: `以 ${base} 厘米为底，用对应的高 ${height} 厘米计算三角形的面积。`,
    formula: `S=\\frac{${base}\\times ${height}}{2}`, answer: `S=${area}\\,\\mathrm{cm}^2`,
    prompt: '同底同高的三角形与平行四边形，面积有什么关系？', hint: '两个全等的三角形可以拼成这个平行四边形。',
    alternative: '将两个全等三角形拼成同底同高的平行四边形，它的面积是三角形的两倍。',
    check: `底乘高再除以 2，面积为 ${area} 平方厘米。`, scope: '按本次补充的底和对应高计算。',
    followUps: [{ step: 2, question: '这里的高是哪一条？', answer: '从底边对面的顶点向这条底边所在直线作垂线，这条垂线段的长度就是对应的高。' }],
  }
}
