import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'

type ModuleCase = {
  key: string
  fields: string[]
  actions: string[]
  actionTargets: string[]
  shape: string
}

const modules: ModuleCase[] = [
  {
    "key": "datasource",
    "fields": [
      "源端编号",
      "连接类型",
      "接入地址",
      "认证方式",
      "采样周期",
      "超时秒数",
      "重试上限",
      "负责人"
    ],
    "actions": [
      "提交校验",
      "启用配置",
      "停用配置"
    ],
    "actionTargets": [
      "待校验",
      "已启用",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "crawler",
    "fields": [
      "规则编号",
      "目标网址",
      "页面选择器",
      "正文选择器",
      "翻页参数",
      "抓取频率",
      "字符编码",
      "去重策略"
    ],
    "actions": [
      "提交测试",
      "发布规则",
      "停用规则"
    ],
    "actionTargets": [
      "测试中",
      "已发布",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "apiclient",
    "fields": [
      "客户端编号",
      "接口名称",
      "请求方法",
      "认证凭证",
      "限流令牌",
      "重试策略",
      "超时配置",
      "启用状态"
    ],
    "actions": [
      "完成配置",
      "启动接入",
      "停用接入"
    ],
    "actionTargets": [
      "已配置",
      "运行中",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "incremental",
    "fields": [
      "游标编号",
      "来源标识",
      "增量字段",
      "当前水位",
      "批次大小",
      "采集间隔",
      "上次采集",
      "下次采集"
    ],
    "actions": [
      "启动采集",
      "暂停采集",
      "标记失败"
    ],
    "actionTargets": [
      "运行中",
      "待启动",
      "失败"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "robot_task",
    "fields": [
      "任务编号",
      "任务名称",
      "页面定位器",
      "动作序列",
      "等待条件",
      "结果字段",
      "超时秒数",
      "执行批次"
    ],
    "actions": [
      "开始执行",
      "暂停任务",
      "标记失败"
    ],
    "actionTargets": [
      "执行中",
      "待执行",
      "执行失败"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "ingestion",
    "fields": [
      "通道编号",
      "通道名称",
      "输入格式",
      "解析引擎",
      "并发数量",
      "背压阈值",
      "缓冲队列",
      "通道状态"
    ],
    "actions": [
      "开通通道",
      "暂停通道",
      "关闭通道"
    ],
    "actionTargets": [
      "开通中",
      "运行中",
      "已关闭"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "parser",
    "fields": [
      "解析编号",
      "输入格式",
      "输出格式",
      "字段映射",
      "类型转换",
      "空值处理",
      "异常策略",
      "解析状态"
    ],
    "actions": [
      "提交配置",
      "启用解析",
      "废弃解析"
    ],
    "actionTargets": [
      "已配置",
      "生效中",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "validator",
    "fields": [
      "规则编号",
      "校验字段",
      "校验类型",
      "期望值",
      "容错范围",
      "采样比例",
      "阻断级别",
      "规则状态"
    ],
    "actions": [
      "提交测试",
      "启用规则",
      "停用规则"
    ],
    "actionTargets": [
      "待测试",
      "已启用",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "dedup",
    "fields": [
      "策略编号",
      "输入来源",
      "去重键",
      "排序字段",
      "保留策略",
      "时间窗口",
      "重复阈值",
      "策略状态"
    ],
    "actions": [
      "提交配置",
      "启用策略",
      "停用策略"
    ],
    "actionTargets": [
      "已配置",
      "生效中",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "schedule",
    "fields": [
      "计划编号",
      "关联任务",
      "调度周期",
      "开始时间",
      "结束时间",
      "依赖任务",
      "失败策略",
      "计划状态"
    ],
    "actions": [
      "确认排期",
      "启动调度",
      "暂停调度"
    ],
    "actionTargets": [
      "已排期",
      "运行中",
      "已暂停"
    ],
    "shape": "crud-table"
  },
  {
    "key": "monitor",
    "fields": [
      "面板编号",
      "采集源总数",
      "今日采集量",
      "成功率",
      "平均延迟",
      "失败重试",
      "异常告警",
      "更新时间"
    ],
    "actions": [
      "查看详情"
    ],
    "actionTargets": [
      "正常"
    ],
    "shape": "analysis-dashboard"
  },
  {
    "key": "log_viewer",
    "fields": [
      "日志编号",
      "关联任务",
      "日志级别",
      "记录时间",
      "日志内容",
      "错误堆栈",
      "处理状态",
      "处理人"
    ],
    "actions": [
      "开始处理",
      "标记已处理",
      "忽略日志"
    ],
    "actionTargets": [
      "处理中",
      "已处理",
      "已忽略"
    ],
    "shape": "crud-table"
  },
  {
    "key": "auth",
    "fields": [
      "凭证编号",
      "凭证类型",
      "关联数据源",
      "凭证内容",
      "有效期至",
      "创建时间",
      "最后使用",
      "凭证状态"
    ],
    "actions": [
      "续期凭证",
      "吊销凭证"
    ],
    "actionTargets": [
      "有效",
      "已吊销"
    ],
    "shape": "crud-table"
  },
  {
    "key": "transform",
    "fields": [
      "节点编号",
      "输入来源",
      "输出目标",
      "转换表达式",
      "执行顺序",
      "依赖节点",
      "失败策略",
      "节点状态"
    ],
    "actions": [
      "提交校验",
      "启用节点",
      "停用节点"
    ],
    "actionTargets": [
      "待校验",
      "已启用",
      "已停用"
    ],
    "shape": "dag-graph"
  },
  {
    "key": "flow",
    "fields": [
      "管道编号",
      "管道名称",
      "起始节点",
      "终止节点",
      "中间节点",
      "流转条件",
      "并行数量",
      "管道状态"
    ],
    "actions": [
      "提交校验",
      "启用管道",
      "停用管道"
    ],
    "actionTargets": [
      "待校验",
      "已启用",
      "已停用"
    ],
    "shape": "dag-graph"
  },
  {
    "key": "lineage",
    "fields": [
      "关系编号",
      "上游节点",
      "下游节点",
      "来源字段",
      "目标字段",
      "转换说明",
      "采集批次",
      "关系版本"
    ],
    "actions": [
      "记录关系",
      "验证关系",
      "归档关系"
    ],
    "actionTargets": [
      "已记录",
      "已验证",
      "已归档"
    ],
    "shape": "dag-graph"
  },
  {
    "key": "report",
    "fields": [
      "报告编号",
      "采集源",
      "统计周期",
      "总采集量",
      "成功量",
      "失败量",
      "平均耗秒",
      "生成时间"
    ],
    "actions": [
      "重新生成"
    ],
    "actionTargets": [
      "已生成"
    ],
    "shape": "analysis-dashboard"
  }
]
const repoKind = 'fullstack'
// log_viewer 的终态边界（已处理后忽略必须被拒绝）由 terminal-ledger.spec.ts 专项验收，
// 不再走通用的「三个动作顺序执行」链路，否则终态拒绝会与通用预期冲突。
const crudModules = modules.filter(m => m.shape === 'crud-table' && m.key !== 'log_viewer')
const dagModules = modules.filter(m => m.shape === 'dag-graph')
const timelineModules = modules.filter(m => m.shape === 'job-timeline')
const analysisModules = modules.filter(m => m.shape === 'analysis-dashboard')

function parseCsv(text: string): string[][] {
  const records: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  const input = text.replace(/^\uFEFF/, '')
  for (let index = 0; index < input.length; index++) {
    const char = input[index]
    if (quoted) {
      if (char === '"' && input[index + 1] === '"') { cell += '"'; index++ }
      else if (char === '"') { quoted = false }
      else { cell += char }
    } else if (char === '"' && cell === '') { quoted = true }
    else if (char === ',') { row.push(cell); cell = '' }
    else if (char === '\n') {
      row.push(cell.replace(/\r$/, ''))
      if (row.some(v => v !== '')) records.push(row)
      row = []; cell = ''
    } else { cell += char }
  }
  row.push(cell.replace(/\r$/, ''))
  if (row.some(v => v !== '')) records.push(row)
  return records
}

test('CRUD模块：筛选、导出、登记、动作、指标全链路', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (crudModules.length === 0) { test.skip(); return }

  for (const mod of crudModules) {
    await page.goto(`/${mod.key}`)
    await page.waitForTimeout(3000)
    const bodyRows = page.locator('tbody tr[data-testid^="row-"]')
    await expect(bodyRows).toHaveCount(3)
    const firstValue = await bodyRows.nth(0).locator('td').nth(0).innerText()

    await page.getByTestId(`filter-${mod.fields[0]}`).fill(firstValue)
    await page.getByTestId('query').click()
    await expect(bodyRows).toHaveCount(1)
    await page.getByTestId('reset').click()
    await expect(bodyRows).toHaveCount(3)

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    const createdValues = mod.fields.map((f, i) => `验收-${mod.key}-${i+1}`)
    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.entries()) {
      await page.getByTestId(`create-${field}`).fill(createdValues[i])
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
    await expect(bodyRows).toHaveCount(4)

    const createdRow = page.locator('tbody tr').filter({ hasText: createdValues[0] })
    for (const [i, action] of mod.actions.entries()) {
      await createdRow.getByRole('button', { name: action, exact: true }).click()
      await expect(createdRow).toHaveAttribute('data-status', mod.actionTargets[i])
    }
  }

  expect(browserErrors).toEqual([])
})

test('DAG拓扑模块：节点渲染、详情、动作、导出', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (dagModules.length === 0) { test.skip(); return }

  for (const mod of dagModules) {
    await page.goto(`/${mod.key}`)
    await page.waitForTimeout(3000)
    await expect(page.locator('svg.dag-svg')).toBeVisible()
    const nodes = page.locator('g.dag-node')
    const count = await nodes.count()
    expect(count).toBeGreaterThanOrEqual(3)

    await nodes.first().click()
    await expect(page.getByTestId('dag-detail')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.slice(0,3).entries()) {
      await page.locator('.create-field input').nth(i).fill(`E2E-${mod.key}-${i}`)
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
  }

  expect(browserErrors).toEqual([])
})

test('时间线模块：甘特条渲染、日期筛选、日志查看、登记', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (timelineModules.length === 0) { test.skip(); return }

  for (const mod of timelineModules) {
    await page.goto(`/${mod.key}`)
    await expect(page.locator('.timeline-bar').first()).toBeVisible({ timeout: 10000 })
    const bars = page.locator('.timeline-bar')
    const count = await bars.count()
    expect(count).toBeGreaterThanOrEqual(3)

    await bars.first().click()
    await expect(page.getByTestId('timeline-log')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.slice(0,3).entries()) {
      await page.locator('.create-field input').nth(i).fill(`E2E-${mod.key}-${i}`)
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
  }

  expect(browserErrors).toEqual([])
})

test('分析看板模块：KPI卡片、运行分析、图表渲染', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (analysisModules.length === 0) { test.skip(); return }

  for (const mod of analysisModules) {
    await page.goto(`/${mod.key}`)
    await expect(page.getByTestId('kpi-card').first()).toBeVisible({ timeout: 10000 })
    const kpiCards = page.getByTestId('kpi-card')
    const kpiCount = await kpiCards.count()
    expect(kpiCount).toBeGreaterThanOrEqual(2)
    await expect(kpiCards.first().locator('strong')).toBeVisible()

    await page.getByTestId('run-analysis').click()
    await expect(page.locator('.analysis-bar').first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator('.data-table tbody tr').first()).toBeVisible({ timeout: 5000 })
  }

  expect(browserErrors).toEqual([])
})

test('概览汇总', async ({ page }) => {
  test.setTimeout(300_000)
  await page.goto('/')
  await expect(page.locator('.stat-value').nth(1)).toBeVisible()
  // 验证概览页加载正常即可，不硬编码精确计数（取决于各模块 E2E 登记成功数）
})
