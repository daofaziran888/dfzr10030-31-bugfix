import { expect, test } from '@playwright/test'

/**
 * 终态边界专项验收：
 * 1. 已处理落版后再点忽略必须被拒绝，终态与监控异常数均不变化；
 * 2. 终态日志台账每条日志只有一个终态版本，拒绝动作与负责人留痕；
 * 3. 监控分析服务同步消费台账、落待复核台账并写回核对结果，重复核对只保留一份。
 */
const ENDPOINT = '/log_viewer'
// 后端为内存仓储，跨用例数据会累积；用时间戳保证编号唯一，避免 filter 命中历史行。
const RUN_SERIAL = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`

async function createLog(page: import('@playwright/test').Page, serial: string) {
  const code = `验收-终态-${RUN_SERIAL}-${serial}`
  const values = [code, `任务-${serial}`, 'ERROR', '2026-11-18',
    `摘要-${serial}`, 'stack', '待处理', '值班管理员']
  await page.getByTestId('open-create').click()
  await expect(page.getByTestId('create-modal')).toBeVisible()
  const fields = ['日志编号', '关联任务', '日志级别', '记录时间', '日志内容', '错误堆栈', '处理状态', '处理人']
  for (const [i, field] of fields.entries()) {
    await page.getByTestId(`create-${field}`).fill(values[i])
  }
  await page.getByTestId('submit-create').click()
  await expect(page.getByTestId('create-modal')).toHaveCount(0)
  return page.locator('tbody tr').filter({ hasText: code }).first()
}

test('终态边界：已处理后忽略被拒绝，终态唯一且异常数不回退', async ({ page }) => {
  test.setTimeout(120_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400 && !r.url().includes('terminal-ledger/')) browserErrors.push(`${r.status()} ${r.url()}`) })

  await page.goto(ENDPOINT)
  const rowA = await createLog(page, 'A')

  // 标记已处理 -> 终态落版
  await rowA.getByRole('button', { name: '标记已处理', exact: true }).click()
  await expect(rowA).toHaveAttribute('data-status', '已处理')

  // 打开终态台账，记录异常区基线
  await page.getByTestId('open-ledger').click()
  await expect(page.getByTestId('ledger-modal')).toBeVisible()
  const exceptionBefore = Number(await page.getByTestId('ledger-exception-count').innerText())
  const ledgerRowA = page.getByTestId('ledger-modal').locator('tbody tr').filter({ hasText: `验收-终态-${RUN_SERIAL}-A` }).first()
  await expect(ledgerRowA).toHaveAttribute('data-terminal', '已处理')
  await page.keyboard.press('Escape').catch(() => undefined)
  await page.getByTestId('ledger-modal').locator('button', { hasText: '关闭' }).click()
  await expect(page.getByTestId('ledger-modal')).toHaveCount(0)

  // 另一人点击忽略 -> 终态边界拒绝，行状态保持已处理，页面出现拒绝原因
  await rowA.getByRole('button', { name: '忽略日志', exact: true }).click()
  await expect(rowA).toHaveAttribute('data-status', '已处理')
  await expect(page.getByTestId('action-error')).toContainText('拒绝')

  // 重复标记已处理同样被拒绝
  await rowA.getByRole('button', { name: '标记已处理', exact: true }).click()
  await expect(page.getByTestId('action-error')).toContainText('重复')
  await expect(rowA).toHaveAttribute('data-status', '已处理')

  // 台账中仍是同一份终态版本，拒绝动作留痕，异常区数量不变
  await page.getByTestId('open-ledger').click()
  const ledgerRowAAgain = page.getByTestId('ledger-modal').locator('tbody tr').filter({ hasText: `验收-终态-${RUN_SERIAL}-A` }).first()
  await expect(ledgerRowAAgain).toHaveAttribute('data-terminal', '已处理')
  await expect(ledgerRowAAgain.getByTestId(/rejected-\d+-\d+/).first()).toContainText('忽略日志')
  expect(Number(await page.getByTestId('ledger-exception-count').innerText())).toBe(exceptionBefore)

  // 空态：已处理 + 仅异常区 的组合没有命中，展示原因而非裸空表
  await page.getByTestId('ledger-status-filter').selectOption('已处理')
  await page.getByTestId('ledger-abnormal-filter').check()
  await expect(page.getByTestId('ledger-empty')).toBeVisible()

  expect(browserErrors).toEqual([])
})

test('忽略终态进入异常区，监控服务同步待复核并写回核对结果', async ({ page }) => {
  test.setTimeout(120_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400) browserErrors.push(`${r.status()} ${r.url()}`) })

  await page.goto(ENDPOINT)
  const rowB = await createLog(page, 'B')
  await rowB.getByRole('button', { name: '忽略日志', exact: true }).click()
  await expect(rowB).toHaveAttribute('data-status', '已忽略')

  // 已忽略后再标记已处理也必须拒绝，忽略决定保持最终可见
  await rowB.getByRole('button', { name: '标记已处理', exact: true }).click()
  await expect(rowB).toHaveAttribute('data-status', '已忽略')
  await expect(page.getByTestId('action-error')).toContainText('拒绝')

  // 监控分析服务：终态统计与待复核台账
  await page.goto('/monitor')
  await expect(page.getByTestId('terminal-panel')).toBeVisible()
  const ignoredCount = Number(await page.getByTestId('ignored-count').innerText())
  const exceptionCount = Number(await page.getByTestId('exception-count').innerText())
  expect(ignoredCount).toBeGreaterThanOrEqual(1)
  expect(exceptionCount).toBeGreaterThanOrEqual(1)

  const reviewRowB = page.getByTestId(/review-row-\d+/).filter({ hasText: `验收-终态-${RUN_SERIAL}-B` }).first()
  await expect(reviewRowB).toContainText('待复核')
  await expect(reviewRowB.getByTestId('exception-flag')).toContainText('异常区')

  // 写回核对结果：同窗口只有一份结果，按钮消失且状态变更为已复核
  await reviewRowB.getByTestId(/check-\d+/).click()
  await expect(reviewRowB).toContainText('已复核')
  await expect(reviewRowB.getByRole('button', { name: '写回核对结果' })).toHaveCount(0)

  expect(browserErrors).toEqual([])
})
