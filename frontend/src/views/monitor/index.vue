<template>
  <section class="page" data-module="monitor">
    <header class="page-head">
      <div><h2>采集监控</h2><p class="page-desc">维护监控面板，围绕面板编号、采集源总数、今日采集量、成功率做登记、筛选与状态流转；异常数按终态日志条目数据台账的处理状态版本统计。</p></div>
    </header>
    <div class="analysis-summary">
      <article v-for="m in summaryMetrics" :key="m.label" class="analysis-card" data-testid="kpi-card">
        <span style="font-size:12px;color:var(--muted)">{{ m.label }}</span>
        <strong style="font-size:22px;display:block">{{ m.value }}</strong>
        <span :class="m.trend > 0 ? 'trend-up' : 'trend-down'" style="font-size:12px">{{ m.trend > 0 ? '↑' : '↓' }}{{ Math.abs(m.trend) }}%</span>
      </article>
    </div>

    <!-- 终态日志条目数据台账：监控分析服务同步消费后的统计口径 -->
    <div class="terminal-panel" data-testid="terminal-panel">
      <div class="page-head">
        <div>
          <h3>终态日志监控（终态日志条目数据台账）</h3>
          <p class="page-desc">每条日志只保留一个终态版本，已处理与忽略数量按处理状态版本计算；已处理日志不会被随后的忽略动作改成无告警，异常数不再来回变化。</p>
        </div>
        <div class="page-actions">
          <button class="btn" type="button" data-testid="refresh-terminal" @click="loadTerminalData">刷新台账</button>
        </div>
      </div>
      <div class="stat-row" v-if="terminalStats">
        <article class="stat-card"><span class="stat-label">终态日志总数</span><strong class="stat-value">{{ terminalStats.total_terminal }}</strong></article>
        <article class="stat-card"><span class="stat-label">已处理数量</span><strong class="stat-value" data-testid="processed-count">{{ terminalStats.processed_count }}</strong></article>
        <article class="stat-card"><span class="stat-label">已忽略数量</span><strong class="stat-value" data-testid="ignored-count">{{ terminalStats.ignored_count }}</strong></article>
        <article class="stat-card"><span class="stat-label">异常区数量</span><strong class="stat-value" data-testid="exception-count">{{ terminalStats.exception_count }}</strong></article>
        <article class="stat-card"><span class="stat-label">待复核数量</span><strong class="stat-value">{{ terminalStats.pending_review_count }}</strong></article>
        <article class="stat-card"><span class="stat-label">被拒绝动作</span><strong class="stat-value">{{ terminalStats.rejected_action_count }}</strong></article>
      </div>
      <p v-if="terminalStats && terminalStats.empty_reason" class="empty-state" data-testid="terminal-empty-reason">{{ terminalStats.empty_reason }}</p>

      <div class="filter-bar">
        <label class="filter-item"><span>终态筛选</span>
          <select v-model="ledgerFilter.status" data-testid="review-status-filter" @change="loadTerminalData">
            <option value="">全部</option>
            <option value="已处理">已处理</option>
            <option value="已忽略">已忽略</option>
          </select>
        </label>
        <label class="filter-item"><span>仅异常区</span>
          <input v-model="ledgerFilter.abnormalOnly" type="checkbox" data-testid="review-abnormal-filter" @change="loadTerminalData" />
        </label>
      </div>

      <table class="data-table" v-if="ledgerRows.length">
        <thead>
          <tr>
            <th>日志编号</th><th>关联任务</th><th>终态版本</th><th>负责人</th><th>异常区</th>
            <th>复核状态</th><th>核对结果</th><th>复核人</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in ledgerRows" :key="row.id" :data-testid="`review-row-${row.log_id}`" :data-terminal="row.terminal_status">
            <td>{{ row.日志编号 }}</td>
            <td>{{ row.关联任务 }}</td>
            <td>v{{ row.version }}·{{ row.terminal_status }}</td>
            <td>{{ row.owner }}</td>
            <td :class="{ 'danger-text': row.in_exception_zone }" data-testid="exception-flag">{{ row.in_exception_zone ? '异常区' : '正常' }}</td>
            <td>{{ row.review_status }}</td>
            <td>{{ row.check_result ?? '—' }}</td>
            <td>{{ row.reviewer ?? '—' }}</td>
            <td class="row-actions">
              <button
                v-if="row.review_status === '待复核'"
                class="link"
                type="button"
                :data-testid="`check-${row.log_id}`"
                @click="writeCheck(row)"
              >写回核对结果</button>
              <span v-else class="muted">已复核</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-state" data-testid="review-empty">{{ reviewEmptyReason || '暂无待复核数据：终态日志台账尚未产生条目，或全部条目均已复核' }}</p>
      <p v-if="reviewMessage" class="error-text" data-testid="review-message">{{ reviewMessage }}</p>
    </div>

    <form class="analysis-form" @submit.prevent="runAnalysis">
      <label v-for="field in paramFields" :key="field"><span>{{ field }}</span>
        <select v-if="field.includes('方法')||field.includes('策略')||field.includes('粒度')" v-model="params[field]"><option v-for="o in options[field]" :key="o" :value="o">{{ o }}</option></select>
        <input v-else v-model="params[field]" :placeholder="`请输入${field}`" />
      </label>
      <button class="btn primary" type="submit" data-testid="run-analysis">运行分析</button>
    </form>
    <div v-if="chartData.length" class="analysis-chart">
      <div v-for="(bar, i) in chartData" :key="i" class="analysis-bar" :style="{ height: barHeight(bar.value) + 'px' }"><span>{{ bar.label }}</span></div>
    </div>
    <table class="data-table" v-if="results.length">
      <thead><tr><th v-for="c in resultColumns" :key="c">{{ c }}</th></tr></thead>
      <tbody><tr v-for="row in results" :key="row.id"><td v-for="c in resultColumns" :key="c">{{ row[c] ?? '—' }}</td></tr></tbody>
    </table>
    <p v-if="!results.length && !loading" style="text-align:center;color:var(--muted)">请配置参数后运行分析</p>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { request } from '@/api/client'
const ENDPOINT = '/api/monitor'
const summaryMetrics = ref<{label:string;value:number;trend:number}[]>([])
const results = ref<any[]>([]); const chartData = ref<{label:string;value:number}[]>([])
const loading = ref(false)
const params = ref<Record<string,string>>({})
const paramFields = ["面板编号", "采集源总数", "今日采集量", "成功率", "平均延迟", "失败重试", "异常告警", "更新时间"].filter((f: string) => !['编号','名称','版本'].includes(f)).slice(0, 4)
const options: Record<string,string[]> = { '统计粒度': ['按日','按周','按月'], '分组字段': ['全量','按类型','按区域'], '比较方法': ['环比','同比','绝对值'], '时间范围': ['最近7天','最近30天','最近90天'] }
const resultColumns = ["面板编号", "采集源总数", "今日采集量", "成功率", "平均延迟", "失败重试", "异常告警", "更新时间"].slice(0, 5)
function barHeight(v: number) { const max = Math.max(...chartData.value.map(d => d.value), 1); return Math.max(10, (v / max) * 140) }

// 终态台账与待复核台账
const terminalStats = ref<Record<string, any> | null>(null)
const ledgerRows = ref<any[]>([])
const reviewEmptyReason = ref('')
const reviewMessage = ref('')
const ledgerFilter = ref<{ status: string; abnormalOnly: boolean }>({ status: '', abnormalOnly: false })

async function fetchSummary() {
  try {
    const res = await request(`${ENDPOINT}/summary`)
    const data = await res.json()
    summaryMetrics.value = data.metrics || []
    terminalStats.value = data.terminal_stats ?? null
  } catch (e) {
    reviewMessage.value = '监控汇总读取失败'
  }
}

async function loadTerminalData() {
  reviewMessage.value = ''
  try {
    const query = new URLSearchParams()
    if (ledgerFilter.value.status) query.set('status', ledgerFilter.value.status)
    if (ledgerFilter.value.abnormalOnly) query.set('abnormal_only', 'true')
    // 终态台账来自采集日志服务，监控分析服务同步消费后落到待复核台账。
    const [ledgerRes, reviewRes] = await Promise.all([
      request(`/api/log_viewer/terminal-ledger?${query.toString()}`),
      request(`${ENDPOINT}/pending-review`),
    ])
    const ledgerPayload = await ledgerRes.json()
    const reviewPayload = await reviewRes.json()
    const terminalItems: any[] = ledgerPayload.items ?? []
    const reviewItems: any[] = reviewPayload.items ?? []
    const reviewByLog = new Map<number, any>(reviewItems.map((item) => [Number(item.log_id), item]))
    // 以终态台账为主表，左连接待复核台账的核对结果。
    ledgerRows.value = terminalItems.map((item) => ({
      ...item,
      ...(reviewByLog.get(Number(item.log_id)) ?? { review_status: '待复核', check_result: null, reviewer: null }),
    }))
    reviewEmptyReason.value = ledgerRows.value.length
      ? ''
      : (reviewPayload.empty_reason || '暂无命中的终态日志条目：当前筛选下没有已落版的终态版本')
    await fetchSummary()
  } catch (e) {
    ledgerRows.value = []
    reviewEmptyReason.value = '终态台账读取失败，请确认采集日志服务可用'
  }
}

async function writeCheck(row: any) {
  reviewMessage.value = ''
  try {
    const res = await request(`${ENDPOINT}/pending-review/${row.log_id}/check`, {
      method: 'POST',
      body: JSON.stringify({ result: '核对一致' }),
    })
    const payload = await res.json()
    if (!payload.ok) {
      // 同窗口重复核对被拒绝：提示但不改变现有结果。
      reviewMessage.value = payload.message || '核对结果写入被拒绝'
    }
    await loadTerminalData()
  } catch (e) {
    reviewMessage.value = '核对结果写入失败'
  }
}

async function runAnalysis() {
  loading.value = true
  try { const res = await request(`${ENDPOINT}/run`, { method: 'POST', body: JSON.stringify({ values: params.value }) }); const data = await res.json(); results.value = data.items || []; chartData.value = (data.items || []).map((r: any) => ({ label: Object.values(r)[0] as string, value: Object.values(r).filter(v => typeof v === 'number')[0] as number || 0 })).slice(0, 6) } catch(e) { results.value = [] }
  loading.value = false
}
onMounted(() => { void fetchSummary(); void loadTerminalData() })
</script>
<style scoped>
.terminal-panel { border: 1px solid var(--border, #e4e7ec); border-radius: 10px; padding: 16px; margin-bottom: 20px; }
.danger-text { color: #b42318; font-weight: 600; }
.muted { color: var(--muted); }
</style>
