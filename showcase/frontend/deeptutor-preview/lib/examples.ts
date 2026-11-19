export interface DemoStep {
  role: string
  label: string
  note: string
  incoming?: { kind: 'handoff' | 'challenge' | 'rollback' | 'approve'; label: string }
}

export interface FollowUp {
  question: string
  answer: string
  step: number
}

export interface Example {
  title: string
  subject: string
  question: string
  method: string
  formula: string
  answer: string
  check: string
  scope: string
  prompt: string
  hint: string
  alternative: string
  script?: DemoStep[]
  followUps?: FollowUp[]
  review?: { candidate: number; challenge: number; revision: number }
  variant?: Example
}

// Synthetic public demo records. The polynomial mirrors chat-frontend/tests/browser/fixtures.ts.
export const examples: Example[] = [
  { title: '多项式候选根验证', subject: '一元二次方程', question: '求解 x² − 5x + 6 = 0，并验证候选根。',
    prompt: '哪两个整数的积是 6、和是 −5？它们和方程的根是什么关系？',
    hint: '先试 −2 和 −3，再将两个一次因式分别置零。',
    alternative: '配方法也能得到同一对根：移项并补平方，得到 (x − 5/2)² = 1/4。',
    method: '将多项式分解为两个一次因式，分别令它们为零。', formula: '(x-2)(x-3)=0', answer: 'x=2 \\quad\\text{或}\\quad x=3',
    check: '将 2 和 3 分别代回原式，两次结果均为 0。', scope: '本例只检查两个候选根的代回结果。',
    followUps: [{ step: 2, question: '为什么还要代回检查？', answer: '因为分解和移项都可能引入抄写错误。把 2 和 3 代回原式都得到 0，才能确认候选根确实满足原方程。' }] },
  { title: '等差数列求和', subject: '等差数列', question: '计算 1 到 100 的整数之和，并用首尾配对检查。',
    prompt: '把 1 与 100 配成一组后，下一组是哪两个数？一共有多少组？',
    hint: '依次取两端未使用的数。每组消耗两个不同的数。',
    alternative: '也可以把数列写成正序和倒序两行。两行的和是 100 个 101，最后除以 2。',
    method: '首项与末项配成一组，再依次向中间配对，共有 50 组。', formula: '1+100=2+99=101', answer: 'S=50\\times101=5050',
    check: '每组和为 101，共 50 组，乘积为 5050。', scope: '本例只检查从 1 到 100 的首尾配对。',
    followUps: [{ step: 2, question: '为什么一共有 50 组？', answer: '1 到 100 一共有 100 个数，每组使用两个数，且首尾配对不会重复，所以共有 100÷2=50 组。' }] },
  { title: '参数四次方程的四根之谜', subject: '九角色协作演示', question: '当 a 取何值时，方程 x⁴ − 2ax² + a + 2 = 0 有四个不同实根？若四根从小到大成等差数列，再求 a。',
    prompt: '令 y = x² 后，两个不同的实数 y 根一定给出四个实数 x 根吗？再想想四个等差根的对称中心。',
    hint: '实数的平方非负。要得到四个不同的 x，需要两个不同的正 y。对称的四项等差数列可以写成 −3r、−r、r、3r。',
    alternative: '从等差条件倒推：把原式写成 (x² − r²)(x² − 9r²)，与题目逐项比较系数，再检查得到的参数是否落在四根区间。',
    method: '令 y = x²。四个不同实根要求两个 y 根互异且均为正。由判别式、根和及根积联立得 a > 2。若四根成等差数列，由对称性可写为 −3r、−r、r、3r（r > 0）。令 t = r²，则两根为 t 和 9t，根和给出 t = a/5，根积给出下式。',
    formula: '9a^2-25a-50=0', answer: 'a>2;\\qquad a_{\\rm AP}=\\frac{25+5\\sqrt{97}}{18}',
    check: '二次方程的负根不满足 a > 2。正根对应 t = a/5 > 0，四根相邻差均为 2√t。', scope: '整段为预编数学示例，含判别式反例、参数边界及等差条件复核。',
    script: [
      { role: 'controller', label: '拆分两个目标', note: '先找四个不同实根的参数范围，再在这个范围内筛选等差解。' },
      { role: 'explore', label: '利用偶对称降次', note: '代换 y = x²，得到 y² − 2ay + a + 2 = 0。只有正的 y 才产生一对不同实根。', incoming: { kind: 'handoff', label: '分派' } },
      { role: 'researcher', label: '整理可用判据', note: '记录韦达关系：两个 y 根之和为 2a，积为 a + 2，判别式为 4(a − 2)(a + 1)。', incoming: { kind: 'handoff', label: '转交' } },
      { role: 'planner', label: '安排分支与复核', note: '推理角色先按判别式列出候选区间，校验角色再检查 y 的符号和重根边界。', incoming: { kind: 'handoff', label: '汇总' } },
      { role: 'reasoner', label: '提交候选区间', note: '由判别式大于零，候选为 a < −1 或 a > 2。两支均需检查正根条件。', incoming: { kind: 'handoff', label: '执行' } },
      { role: 'step_verifier', label: '给出反例，退回负分支', note: '取 a = −3，两个 y 根之积为 −1，一正一负，原方程只有两个实根。判别式条件不充分。', incoming: { kind: 'handoff', label: '送审' } },
      { role: 'meta', label: '调整求解策略', note: '将“两个相异正根”写成三条联合约束，再处理等差条件。', incoming: { kind: 'challenge', label: '质疑' } },
      { role: 'reasoner', label: '修正参数范围', note: '要求判别式 > 0、2a > 0、a + 2 > 0，交集为 a > 2。a = 2 时方程为 (x² − 2)² = 0。', incoming: { kind: 'rollback', label: '退回' } },
      { role: 'step_verifier', label: '核对等差结构', note: '由对称性四根为 −3r、−r、r、3r。令 t = r²，得到 10t = 2a，9t² = a + 2。', incoming: { kind: 'handoff', label: '再送审' } },
      { role: 'whole_solution_verifier', label: '整题回代复核', note: '消元得 9a² − 25a − 50 = 0。仅正根满足 a > 2，取 t = a/5 后根和、根积及公差均成立。', incoming: { kind: 'approve', label: '通过' } },
      { role: 'final_generator', label: '整理两问答案', note: '分别给出四根范围和唯一等差参数，附负分支反例与端点说明。', incoming: { kind: 'approve', label: '通过' } },
    ],
    review: { candidate: 4, challenge: 5, revision: 7 },
    followUps: [
      { step: 5, question: '为什么要检查负分支？', answer: '取 a = −3，两个 y 根的积为 −1，一正一负。只有正的 y 能给出一对实根，因此仅凭判别式无法接受这个分支。' },
      { step: 7, question: '为什么 a = 2 也不行？', answer: '此时原式为 (x² − 2)² = 0，只有 x = ±√2 两个不同实根，每个根都出现两次。' },
    ],
    variant: {
      title: '变式 · 恰有两个不同实根', subject: '参数变式', question: '当 a 取何值时，方程 x⁴ − 2ax² + a + 2 = 0 恰有两个不同实根？',
      prompt: '一个正的 y 根对应几个 x？正的重根又会怎样？', hint: '检查两根异号、重根，以及 y = 0 的边界。',
      method: '令 y = x²。当 a < −2 时，两根的积 a + 2 为负，恰有一个正 y。另一种情况是两个 y 根重合且为正，得到 a = 2。',
      alternative: '按 a = −2、−1、2 划分区间，分别数正 y、零根和重根各自贡献的不同实根。',
      formula: 'y_1y_2=a+2,\\quad \\Delta=4(a-2)(a+1)', answer: 'a<-2\\quad\\text{或}\\quad a=2',
      check: 'a = −2 时只有实根 0。−2 < a ≤ −1 时两个 y 根均为负，−1 < a < 2 时无实 y 根。a > 2 时有四个不同实根。',
      scope: '按两个 y 根的符号、重数和零根边界检查全部实参数。',
    }, },
]

export function stepsFor(example: Example): DemoStep[] {
  return example.script ?? [
    { role: 'planner', label: '制定求解计划', note: '确定求解方法，最后用题目给定的条件检查结果。' },
    { role: 'reasoner', label: '推导候选答案', note: example.method },
    { role: 'step_verifier', label: '检查候选结果', note: example.check },
  ]
}
