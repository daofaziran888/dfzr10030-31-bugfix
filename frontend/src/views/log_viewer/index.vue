<template>
  <section class="page" data-module="log_viewer">
    <header class="page-head">
      <div>
        <h2>采集日志管理</h2>
        <p class="page-desc">维护日志条目，围绕日志编号、关联任务、日志级别、记录时间做登记、筛选与状态流转；已处理/已忽略为终态，终态落版后跨终态动作会被拒绝。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">登记日志条目</button>
        <button class="btn" data-testid="open-ledger" type="button" @click="openLedger">终态日志台账</button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">导出采集日志清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>终态版本</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td data-testid="terminal-cell">
            <span v-if="row.terminal" :class="['terminal-tag', row.terminal.terminal_status === '已忽略' ? 'tag-danger' : 'tag-ok']">
              v{{ row.terminal.version }}·{{ row.terminal.terminal_status }}
            </span>
            <span v-else class="muted">—</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无采集日志数据，可先登记日志条目</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记日志条目</h3>
        <label v-for="field in columns" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <!-- 终态日志条目数据台账：每条日志唯一终态、被拒绝动作与负责人 -->
    <div v-if="showLedger" class="modal-backdrop" data-testid="ledger-modal" @click.self="showLedger = false">
      <div class="modal modal-wide">
        <div class="page-head">
          <div>
            <h3>终态日志条目数据台账</h3>
            <p class="page-desc">按终态边界归并处理与忽略动作，每条日志只保留一个终态版本；异常标记随版本冻结，监控数量不再来回变化。</p>
          </div>
          <div class="page-actions">
            <label class="filter-item"><span>仅看异常区</span>
              <input v-model="ledgerAbnormalOnly" type="checkbox" data-testid="ledger-abnormal-filter" @change="loadLedger" />
            </label>
            <select v-model="ledgerStatus" data-testid="ledger-status-filter" @change="loadLedger">
              <option value="">全部终态</option>
              <option value="已处理">已处理</option>
              <option value="已忽略">已忽略</option>
            </select>
            <button class="btn ghost" type="button" @click="showLedger = false">关闭</button>
          </div>
        </div>

        <div class="stat-row" v-if="ledgerStats">
          <article class="stat-card"><span class="stat-label">终态总数</span><strong class="stat-value">{{ ledgerStats.total_terminal }}</strong></article>
          <article class="stat-card"><span class="stat-label">已处理</span><strong class="stat-value">{{ ledgerStats.processed_count }}</strong></article>
          <article class="stat-card"><span class="stat-label">已忽略</span><strong class="stat-value">{{ ledgerStats.ignored_count }}</strong></article>
          <article class="stat-card"><span class="stat-label">异常区</span><strong class="stat-value" data-testid="ledger-exception-count">{{ ledgerStats.exception_count }}</strong></article>
          <article class="stat-card"><span class="stat-label">被拒绝动作</span><strong class="stat-value">{{ ledgerStats.rejected_action_count }}</strong></article>
        </div>

        <table class="data-table" v-if="ledgerRows.length">
          <thead>
            <tr>
              <th>日志编号</th><th>关联任务</th><th>终态</th><th>版本</th><th>负责人</th>
              <th>异常区</th><th>原摘要</th><th>被拒绝动作</th><th>落版时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in ledgerRows" :key="row.id" :data-testid="`ledger-row-${row.log_id}`" :data-terminal="row.terminal_status">
              <td>{{ row.日志编号 }}</td>
              <td>{{ row.关联任务 }}</td>
              <td>{{ row.terminal_status }}</td>
              <td>v{{ row.version }}</td>
              <td>{{ row.owner }}</td>
              <td data-testid="exception-flag">{{ row.in_exception_zone ? '是' : '否' }}</td>
              <td class="cell-ellipsis" :title="row.summary ?? ''">{{ row.summary ?? '—' }}</td>
              <td>
                <span v-if="!row.rejected_actions?.length" class="muted">—</span>
                <ul v-else class="reject-list">
                  <li v-for="(r, i) in row.rejected_actions" :key="i" :data-testid="`rejected-${row.log_id}-${i}`">
                    {{ r.action }}（{{ r.reason }}·{{ r.operator }}）
                  </li>
                </ul>
              </td>
              <td>{{ row.created_at }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state" data-testid="ledger-empty">{{ ledgerEmptyReason || '暂无命中的终态日志条目：日志仍处于未处理/处理中，尚无终态版本落版' }}</p>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条采集日志记录</span>
      <span class="error-text" data-testid="action-error">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/log_viewer'
const columns = ["日志编号", "关联任务", "日志级别", "记录时间", "日志内容", "错误堆栈", "处理状态", "处理人"]
const actions = ["开始处理", "标记已处理", "忽略日志"]
const statuses = ["未处理", "处理中", "已处理", "已忽略"]
const metricNames = ["未处理日志", "处理中日志", "已处理日志"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})

// 终态台账弹窗状态
const showLedger = ref(false)
const ledgerRows = ref<Row[]>([])
const ledgerStats = ref<Row | null>(null)
const ledgerEmptyReason = ref('')
const ledgerStatus = ref('')
const ledgerAbnormalOnly = ref(false)

const stats = computed(() => [
  { label: metricNames[0], value: total.value },
  { label: metricNames[1], value: rows.value.filter((row) => row.status === statuses[1]).length },
  { label: metricNames[2], value: rows.value.filter((row) => row.status === statuses[statuses.length - 1]).length },
])

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value).toString()
  try {
    const response = await request(`${ENDPOINT}/export?${query}`)
    if (!response.ok) throw new Error('导出失败，请稍后重试')
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = 'log_viewer.csv'
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(columns.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST', body: JSON.stringify(createValues.value),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '登记失败')
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

function makeClientToken(action: string, row: Row): string {
  // 同窗口并发去重：一次点击一个令牌，重复点击/并发提交带相同令牌时后端只保留一份结果。
  return `${row.id}-${action}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action, client_token: makeClientToken(action, row) }),
    })
    if (!response.ok) {
      throw new Error('采集日志动作未生效，请稍后重试')
    }
    const payload = await response.json()
    // 先刷新列表（reload 会清空旧提示），再写入本次终态边界拒绝原因，避免消息被覆盖。
    await reload()
    // 终态边界拒绝（已处理后忽略、终态重复动作等）：后端返回 ok=false 并附原因，状态不变。
    if (!payload.ok) {
      errorMessage.value = payload.message || '动作被终态边界拒绝'
    }
    if (showLedger.value) {
      await loadLedger()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '采集日志操作失败'
  }
}

async function openLedger() {
  showLedger.value = true
  await loadLedger()
}

async function loadLedger() {
  const params = new URLSearchParams()
  if (ledgerStatus.value) params.set('status', ledgerStatus.value)
  if (ledgerAbnormalOnly.value) params.set('abnormal_only', 'true')
  try {
    const response = await request(`${ENDPOINT}/terminal-ledger?${params.toString()}`)
    if (!response.ok) throw new Error('终态台账读取失败')
    const payload = await response.json()
    ledgerRows.value = payload.items ?? []
    ledgerStats.value = payload.total !== undefined
      ? { total_terminal: payload.total }
      : ledgerStats.value
    ledgerEmptyReason.value = payload.items?.length
      ? ''
      : '暂无命中的终态日志条目：当前筛选下没有已落版的终态版本（日志仍处于未处理/处理中）'
  } catch (error) {
    ledgerRows.value = []
    ledgerEmptyReason.value = error instanceof Error ? error.message : '终态台账读取失败'
  }
  // 统计口径独立取一次，保证与监控分析服务一致。
  try {
    const summaryRes = await request('/api/monitor/summary')
    if (summaryRes.ok) {
      const summary = await summaryRes.json()
      ledgerStats.value = summary.terminal_stats ?? ledgerStats.value
    }
  } catch {
    // 监控服务暂不可用时保留台账自身计数
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('日志条目列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '采集日志列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.modal-wide { width: min(1080px, 94vw); max-height: 86vh; overflow: auto; }
.terminal-tag { padding: 2px 8px; border-radius: 10px; font-size: 12px; white-space: nowrap; }
.tag-ok { background: #ecfdf3; color: #027a48; }
.tag-danger { background: #fef3f2; color: #b42318; }
.muted { color: var(--muted); }
.cell-ellipsis { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reject-list { margin: 0; padding-left: 16px; }
.reject-list li { color: #b42318; font-size: 12px; }
</style>
