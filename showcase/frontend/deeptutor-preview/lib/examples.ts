// Synthetic public demo records. The polynomial mirrors chat-frontend/tests/browser/fixtures.ts.
export const examples = [
  { title: '多项式候选根验证', subject: '一元二次方程', question: '求解 x² − 5x + 6 = 0，并验证候选根。',
    method: '将多项式分解为两个一次因式，分别令它们为零。', formula: '(x-2)(x-3)=0', answer: 'x=2 \\quad\\text{或}\\quad x=3',
    check: '将 2 和 3 分别代回原式，两次结果均为 0。', scope: '本例只检查两个候选根的代回结果。' },
  { title: '等差数列求和', subject: '等差数列', question: '计算 1 到 100 的整数之和，并用首尾配对检查。',
    method: '首项与末项配成一组，再依次向中间配对，共有 50 组。', formula: '1+100=2+99=101', answer: 'S=50\\times101=5050',
    check: '每组和为 101，共 50 组，乘积为 5050。', scope: '本例只检查从 1 到 100 的首尾配对。' },
] as const
export type Example = typeof examples[number]
