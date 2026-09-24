<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import RiskScatter from './components/RiskScatter.vue'
import ContribBars from './components/ContribBars.vue'
import RiskGauge from './components/RiskGauge.vue'
import RiskJourney from './components/RiskJourney.vue'

const meta = ref(null)
const cohort = ref([])
const selId = ref(null)
const values = reactive({})
const result = ref(null)

const xKey = ref('age')
const yKey = ref('prior_admissions')
const zKey = ref('risk')
const filter = ref('all')
const search = ref('')
const error = ref('')

let timer
let seq = 0

const sel = computed(() =>
  cohort.value.find((p) => p.id === selId.value)
)

const label = (k) =>
  meta.value.features.find((f) => f.key === k)?.label || k

const xFeature = computed(() =>
  meta.value.features.find((f) => f.key === xKey.value)
)

const dirty = computed(() =>
  sel.value &&
  meta.value.features.some(
    (f) => values[f.key] !== sel.value.features[f.key]
  )
)

const delta = computed(() =>
  result.value && sel.value
    ? (result.value.risk - sel.value.risk) * 100
    : 0
)

const counts = computed(() =>
  Object.fromEntries(
    ['high', 'moderate', 'low'].map((t) => [
      t,
      cohort.value.filter((p) => p.tier === t).length
    ])
  )
)

const queue = computed(() => {
  const query = search.value.trim().toLowerCase()

  return cohort.value.filter((p) => {
    const matchesFilter =
      filter.value === 'all' || p.tier === filter.value

    const matchesSearch =
      !query ||
      p.id.toLowerCase().includes(query) ||
      label(p.top_driver).toLowerCase().includes(query)

    return matchesFilter && matchesSearch
  })
})

const items = computed(() =>
  result.value.contributions.map((c) => ({
    ...c,
    label: label(c.key)
  }))
)

const whatIf = computed(() =>
  dirty.value
    ? {
        x: values[xKey.value],
        y: result.value.risk,
        tier: result.value.tier
      }
    : null
)

const riskPercent = computed(() =>
  Math.round((result.value?.risk || 0) * 100)
)

const tierLabel = computed(() => {
  if (!result.value) return ''
  return result.value.tier.charAt(0).toUpperCase() +
    result.value.tier.slice(1)
})

function select(p) {
  selId.value = p.id

  Object.assign(values, p.features)

  result.value = {
    risk: p.risk,
    tier: p.tier,
    contributions: p.contributions
  }
}

function selectTier(tier) {
  filter.value = tier

  if (tier !== 'all') {
    const first = cohort.value.find((p) => p.tier === tier)

    if (first) {
      select(first)
    }
  }
}

function resetPatient() {
  if (sel.value) {
    select(sel.value)
  }
}

function onSlide() {
  clearTimeout(timer)

  timer = setTimeout(async () => {
    const mine = ++seq

    try {
      const r = await fetch('/api/predict', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          features: { ...values }
        })
      })

      if (!r.ok) {
        throw new Error(await r.text())
      }

      const data = await r.json()

      if (mine === seq) {
        result.value = data
      }
    } catch (e) {
      error.value =
        'Could not reach the prediction service. Start the API on port 8000.'
    }
  }, 90)
}

const fmt = (f, v) =>
  f.step < 1 ? Number(v).toFixed(1) : v

onMounted(async () => {
  try {
    meta.value = await (
      await fetch('/api/meta')
    ).json()

    cohort.value = await (
      await fetch('/api/cohort')
    ).json()

    select(cohort.value[0])
  } catch (e) {
    error.value =
      'Could not reach the prediction service. Start the API on port 8000.'
  }
})
</script>

<template>
  <div v-if="error" class="state-screen">
    <div class="error-box">
      <div class="error-icon">!</div>
      <h2>Connection problem</h2>
      <p>{{ error }}</p>
    </div>
  </div>

  <div
    v-else-if="!meta || !result"
    class="state-screen"
  >
    <div class="loading-box">
      <div class="loader"></div>
      <h2>Loading Risk Dashboard</h2>
      <p>Connecting to the prediction service...</p>
    </div>
  </div>

  <div v-else class="app">

    <!-- HEADER -->
    <header class="topbar">

      <div class="brand">
        <div class="brand-icon">+</div>

        <div>
          <div class="brand-name">
            HealthCheck
          </div>

          <div class="brand-subtitle">
            Clinical Risk Intelligence
          </div>
        </div>
      </div>

      <div class="header-center">
        <div class="status-dot"></div>
        <span>Prediction service online</span>
      </div>

      <div class="header-right">
        <div class="model-badge">
          <span>MODEL</span>
          Gradient Boosting
        </div>

        <div class="avatar">
          HC
        </div>
      </div>

    </header>

    <!-- PAGE INTRO -->
    <section class="page-heading">

      <div>
        <div class="eyebrow">
          PATIENT RISK OVERVIEW
        </div>

        <h1>
          30-day readmission risk
        </h1>

        <p>
          Monitor patient risk, explore contributing factors,
          and simulate how changes affect predicted outcomes.
        </p>
      </div>

      <div class="model-info">

        <div>
          <span>COHORT</span>
          <strong>{{ cohort.length }}</strong>
        </div>

        <div>
          <span>AUC</span>
          <strong>{{ meta.auc }}</strong>
        </div>

        <div>
          <span>BASE RATE</span>
          <strong>{{ Math.round(meta.prevalence * 100) }}%</strong>
        </div>

      </div>

    </section>

    <!-- KPI CARDS -->
    <section class="stats-grid">

      <button
        class="stat-card all-card"
        :class="{ active: filter === 'all' }"
        @click="selectTier('all')"
      >
        <div class="stat-top">
          <span class="stat-label">ALL PATIENTS</span>
          <span class="stat-arrow">→</span>
        </div>

        <div class="stat-number">
          {{ cohort.length }}
        </div>

        <div class="stat-bottom">
          Complete discharge cohort
        </div>
      </button>

      <button
        class="stat-card high-card"
        :class="{ active: filter === 'high' }"
        @click="selectTier('high')"
      >
        <div class="stat-top">
          <span class="risk-dot high"></span>
          <span class="stat-label">HIGH RISK</span>
          <span class="stat-arrow">→</span>
        </div>

        <div class="stat-number">
          {{ counts.high }}
        </div>

        <div class="stat-bottom">
          ≥ 40% predicted risk
        </div>
      </button>

      <button
        class="stat-card moderate-card"
        :class="{ active: filter === 'moderate' }"
        @click="selectTier('moderate')"
      >
        <div class="stat-top">
          <span class="risk-dot moderate"></span>
          <span class="stat-label">MODERATE RISK</span>
          <span class="stat-arrow">→</span>
        </div>

        <div class="stat-number">
          {{ counts.moderate }}
        </div>

        <div class="stat-bottom">
          20–39% predicted risk
        </div>
      </button>

      <button
        class="stat-card low-card"
        :class="{ active: filter === 'low' }"
        @click="selectTier('low')"
      >
        <div class="stat-top">
          <span class="risk-dot low"></span>
          <span class="stat-label">LOW RISK</span>
          <span class="stat-arrow">→</span>
        </div>

        <div class="stat-number">
          {{ counts.low }}
        </div>

        <div class="stat-bottom">
          &lt; 20% predicted risk
        </div>
      </button>

    </section>

    <!-- MAIN LAYOUT -->
    <div class="dashboard-grid">

      <!-- PATIENT QUEUE -->
      <aside class="queue-panel">

        <div class="panel-heading">

          <div>
            <div class="panel-kicker">
              CARE MANAGEMENT
            </div>

            <h2>
              Triage queue
            </h2>
          </div>

          <span class="queue-count">
            {{ queue.length }}
          </span>

        </div>

        <!-- SEARCH -->
        <div class="search-box">
          <span>⌕</span>

          <input
            v-model="search"
            type="text"
            placeholder="Search patient or factor..."
          />
        </div>

        <!-- FILTERS -->
        <div class="filter-row">

          <button
            v-for="t in ['all', 'high', 'moderate', 'low']"
            :key="t"
            :class="{ selected: filter === t }"
            @click="filter = t"
          >
            {{ t }}
          </button>

        </div>

        <!-- PATIENTS -->
        <div class="patient-list">

          <button
            v-for="p in queue"
            :key="p.id"
            class="patient-row"
            :class="{ selected: p.id === selId }"
            @click="select(p)"
          >

            <div
              class="patient-risk"
              :class="p.tier"
            ></div>

            <div class="patient-main">

              <strong>
                {{ p.id }}
              </strong>

              <span>
                {{ label(p.top_driver) }}
              </span>

            </div>

            <div
              class="patient-score"
              :class="p.tier"
            >
              {{ Math.round(p.risk * 100) }}%
            </div>

          </button>

          <div
            v-if="queue.length === 0"
            class="empty-state"
          >
            No patients found.
          </div>

        </div>

      </aside>

      <!-- CENTER -->
      <main class="content-column">

        <!-- SELECTED PATIENT SUMMARY -->
        <section class="patient-summary">

          <div class="patient-summary-left">

            <div class="patient-avatar">
              {{ sel.id.replace('P-', '') }}
            </div>

            <div>
              <div class="summary-label">
                SELECTED PATIENT
              </div>

              <h2>
                {{ sel.id }}
              </h2>

              <p>
                Primary driver:
                <strong>{{ label(sel.top_driver) }}</strong>
              </p>
            </div>

          </div>

          <div class="risk-summary">

            <span
              class="risk-pill"
              :class="result.tier"
            >
              {{ tierLabel }} Risk
            </span>

            <strong>
              {{ riskPercent }}%
            </strong>

            <span>
              predicted readmission
            </span>

          </div>

        </section>

        <!-- SCATTER -->
        <section class="content-card">

          <div class="card-heading">

            <div>
              <div class="panel-kicker">
                COHORT POSITION
              </div>

              <h2>
                Where this patient sits in the cohort
              </h2>

              <p>
                Compare the selected patient with the entire discharge cohort.
              </p>
            </div>

            <label class="select-control">
              <span>Plot against</span>

              <select v-model="xKey">
                <option
                  v-for="f in meta.features"
                  :key="f.key"
                  :value="f.key"
                >
                  {{ f.label }}
                </option>
              </select>
            </label>

          </div>

          <RiskScatter
            :patients="cohort"
            :selected="sel"
            :what-if="whatIf"
            :x-feature="xFeature"
            :tiers="meta.tiers"
            @pick="select"
          />

        </section>

        <!-- CONTRIBUTIONS -->
        <section class="content-card">

          <div class="card-heading">

            <div>
              <div class="panel-kicker">
                MODEL EXPLANATION
              </div>

              <h2>
                What is driving the risk?
              </h2>

              <p>
                Change in predicted probability compared with
                cohort-average values.
              </p>
            </div>

          </div>

          <ContribBars :items="items" />

        </section>

      </main>

      <!-- RIGHT PANEL -->
      <aside class="right-column">

        <!-- RISK CARD -->
        <section class="risk-card">

          <div class="risk-card-header">

            <div>
              <div class="panel-kicker">
                CURRENT ASSESSMENT
              </div>

              <h2>
                Risk score
              </h2>
            </div>

            <button
              class="reset-button"
              :disabled="!dirty"
              @click="resetPatient"
            >
              Reset
            </button>

          </div>

          <RiskGauge
            :risk="result.risk"
            :tier="result.tier"
            :tiers="meta.tiers"
          />

          <div
            class="risk-change"
            :class="{
              increase: delta > 0.05,
              decrease: delta < -0.05
            }"
          >

            <template v-if="!dirty">
              Recorded risk at discharge
            </template>

            <template v-else>
              {{ delta >= 0 ? '+' : '−' }}
              {{ Math.abs(delta).toFixed(1) }}
              points from recorded
              {{ Math.round(sel.risk * 100) }}%
            </template>

          </div>

        </section>

        <!-- SLIDERS -->
        <section class="controls-card">

          <div class="controls-header">

            <div>
              <div class="panel-kicker">
                WHAT-IF SIMULATION
              </div>

              <h2>
                Adjust risk factors
              </h2>
            </div>

            <span
              v-if="dirty"
              class="edited-badge"
            >
              LIVE
            </span>

          </div>

          <div
            v-for="f in meta.features"
            :key="f.key"
            class="slider-control"
          >

            <div class="slider-header">

              <label :for="f.key">
                {{ f.label }}
              </label>

              <strong>
                {{ fmt(f, values[f.key]) }}
                {{ f.unit }}
              </strong>

            </div>

            <input
              :id="f.key"
              v-model.number="values[f.key]"
              type="range"
              :min="f.min"
              :max="f.max"
              :step="f.step"
              :class="result.tier"
              @input="onSlide"
            />

            <div class="slider-range">
              <span>{{ f.min }}</span>
              <span>{{ f.max }}</span>
            </div>

          </div>

          <div
            v-if="dirty"
            class="simulation-message"
          >
            <span>●</span>
            Simulation active — prediction updates automatically.
          </div>

        </section>

      </aside>

    </div>

    <!-- FOOTER -->
    <footer>

      <div>
        <span class="footer-dot"></span>
        Demonstration environment
      </div>

      <span>
        Synthetic data · Not validated for clinical decisions
      </span>

    </footer>

  </div>
</template>

<style>
:root {
  --bg: #f5f7fa;
  --surface: #ffffff;
  --surface-soft: #f8fafc;

  --text: #172033;
  --muted: #697586;
  --border: #e4e9ef;

  --blue: #2563eb;
  --blue-soft: #eff6ff;

  --high: #dc4b45;
  --high-soft: #fff1f0;

  --moderate: #d99a24;
  --moderate-soft: #fff8e8;

  --low: #29936f;
  --low-soft: #ecf9f4;

  --shadow: 0 8px 30px rgba(23, 32, 51, 0.06);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family:
    Inter,
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    sans-serif;
}

button,
input,
select {
  font: inherit;
}

button {
  cursor: pointer;
}

button:focus-visible,
input:focus-visible,
select:focus-visible {
  outline: 3px solid rgba(37, 99, 235, 0.2);
  outline-offset: 2px;
}

/* APP */

.app {
  max-width: 1600px;
  margin: 0 auto;
  padding: 0 28px 28px;
}

/* TOPBAR */

.topbar {
  min-height: 74px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;

  border-bottom: 1px solid var(--border);
  background: var(--surface);
  margin: 0 -28px 28px;
  padding: 0 28px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-icon {
  width: 38px;
  height: 38px;

  display: grid;
  place-items: center;

  border-radius: 10px;
  background: var(--blue);
  color: white;

  font-size: 25px;
  font-weight: 700;
}

.brand-name {
  font-weight: 800;
  font-size: 17px;
}

.brand-subtitle {
  color: var(--muted);
  font-size: 11px;
  margin-top: 1px;
}

.header-center {
  display: flex;
  align-items: center;
  gap: 8px;

  color: var(--muted);
  font-size: 13px;
}

.status-dot {
  width: 8px;
  height: 8px;

  border-radius: 50%;
  background: var(--low);

  box-shadow: 0 0 0 4px var(--low-soft);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.model-badge {
  padding: 7px 11px;

  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 8px;

  color: var(--text);
  font-size: 12px;
}

.model-badge span {
  color: var(--muted);
  margin-right: 5px;
  font-size: 9px;
  font-weight: 800;
}

.avatar {
  width: 36px;
  height: 36px;

  display: grid;
  place-items: center;

  border-radius: 50%;
  background: #e9efff;
  color: var(--blue);

  font-size: 11px;
  font-weight: 800;
}

/* HEADING */

.page-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;

  gap: 30px;
  margin-bottom: 22px;
}

.eyebrow,
.panel-kicker,
.summary-label {
  color: var(--blue);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.page-heading h1 {
  margin: 5px 0 6px;
  font-size: 31px;
  letter-spacing: -0.03em;
}

.page-heading p {
  margin: 0;
  color: var(--muted);
  max-width: 680px;
  font-size: 14px;
}

.model-info {
  display: flex;
  gap: 26px;
  padding: 12px 18px;

  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;

  box-shadow: var(--shadow);
}

.model-info div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.model-info span {
  font-size: 9px;
  color: var(--muted);
  font-weight: 800;
  letter-spacing: 0.08em;
}

.model-info strong {
  font-size: 18px;
}

/* STATS */

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 18px;
}

.stat-card {
  position: relative;

  min-height: 125px;
  padding: 17px;

  text-align: left;

  border: 1px solid var(--border);
  border-radius: 13px;

  background: var(--surface);

  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}

.stat-card.active {
  border-color: var(--blue);
  box-shadow:
    0 0 0 2px rgba(37, 99, 235, 0.08),
    var(--shadow);
}

.stat-top {
  display: flex;
  align-items: center;
  gap: 7px;
}

.stat-label {
  font-size: 10px;
  font-weight: 800;
  color: var(--muted);
  letter-spacing: 0.08em;
}

.stat-arrow {
  margin-left: auto;
  color: var(--muted);
}

.risk-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.risk-dot.high {
  background: var(--high);
}

.risk-dot.moderate {
  background: var(--moderate);
}

.risk-dot.low {
  background: var(--low);
}

.stat-number {
  margin-top: 9px;
  font-size: 31px;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.stat-bottom {
  color: var(--muted);
  font-size: 11px;
}

/* MAIN GRID */

.dashboard-grid {
  display: grid;
  grid-template-columns: 285px minmax(0, 1fr) 340px;
  gap: 16px;
  align-items: start;
}

.queue-panel,
.content-card,
.risk-card,
.controls-card,
.patient-summary {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 13px;
  box-shadow: var(--shadow);
}

/* QUEUE */

.queue-panel {
  position: sticky;
  top: 14px;
  overflow: hidden;
}

.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;

  padding: 17px 17px 12px;
}

.panel-heading h2 {
  margin: 3px 0 0;
  font-size: 17px;
}

.queue-count {
  display: grid;
  place-items: center;

  min-width: 28px;
  height: 28px;

  border-radius: 8px;
  background: var(--surface-soft);

  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;

  margin: 0 12px 10px;
  padding: 9px 10px;

  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 9px;

  color: var(--muted);
}

.search-box input {
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;

  color: var(--text);
  font-size: 12px;
}

.search-box input::placeholder {
  color: #9aa4b2;
}

.filter-row {
  display: flex;
  gap: 5px;
  padding: 0 12px 11px;
}

.filter-row button {
  flex: 1;

  padding: 6px 5px;

  border: 1px solid var(--border);
  border-radius: 7px;

  background: white;
  color: var(--muted);

  font-size: 10px;
  font-weight: 700;

  text-transform: capitalize;
}

.filter-row button:hover {
  background: var(--surface-soft);
}

.filter-row button.selected {
  background: var(--text);
  color: white;
  border-color: var(--text);
}

.patient-list {
  max-height: 590px;
  overflow-y: auto;
  border-top: 1px solid var(--border);
}

.patient-row {
  width: 100%;

  display: grid;
  grid-template-columns: 8px 1fr auto;
  gap: 10px;
  align-items: center;

  padding: 11px 13px;

  border: 0;
  border-bottom: 1px solid var(--border);

  background: transparent;
  text-align: left;

  transition: background 0.15s ease;
}

.patient-row:hover {
  background: var(--surface-soft);
}

.patient-row.selected {
  background: var(--blue-soft);
}

.patient-risk {
  width: 7px;
  height: 34px;
  border-radius: 8px;
}

.patient-risk.high {
  background: var(--high);
}

.patient-risk.moderate {
  background: var(--moderate);
}

.patient-risk.low {
  background: var(--low);
}

.patient-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.patient-main strong {
  font-size: 12px;
}

.patient-main span {
  color: var(--muted);
  font-size: 10px;

  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.patient-score {
  font-size: 13px;
  font-weight: 800;
}

.patient-score.high {
  color: var(--high);
}

.patient-score.moderate {
  color: var(--moderate);
}

.patient-score.low {
  color: var(--low);
}

.empty-state {
  padding: 35px 15px;
  text-align: center;
  color: var(--muted);
  font-size: 12px;
}

/* CONTENT */

.content-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.patient-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;

  padding: 16px 18px;
}

.patient-summary-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.patient-avatar {
  width: 46px;
  height: 46px;

  display: grid;
  place-items: center;

  border-radius: 12px;

  background: var(--blue-soft);
  color: var(--blue);

  font-size: 11px;
  font-weight: 800;
}

.patient-summary h2 {
  margin: 2px 0;
  font-size: 18px;
}

.patient-summary p {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
}

.risk-summary {
  display: flex;
  align-items: center;
  gap: 8px;
}

.risk-summary strong {
  font-size: 28px;
  letter-spacing: -0.04em;
}

.risk-summary > span:last-child {
  color: var(--muted);
  font-size: 10px;
}

.risk-pill {
  padding: 5px 8px;
  border-radius: 999px;

  font-size: 10px;
  font-weight: 800;
}

.risk-pill.high {
  color: var(--high);
  background: var(--high-soft);
}

.risk-pill.moderate {
  color: var(--moderate);
  background: var(--moderate-soft);
}

.risk-pill.low {
  color: var(--low);
  background: var(--low-soft);
}

/* CARDS */

.content-card {
  padding: 18px;
  min-width: 0;
}

.card-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;

  gap: 15px;
  margin-bottom: 8px;
}

.card-heading h2 {
  margin: 4px 0;
  font-size: 17px;
}

.card-heading p {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
}

.select-control {
  display: flex;
  align-items: center;
  gap: 7px;

  color: var(--muted);
  font-size: 11px;
}

.select-control select {
  padding: 7px 10px;

  border: 1px solid var(--border);
  border-radius: 8px;

  background: white;
  color: var(--text);
}

/* RIGHT */

.right-column {
  display: flex;
  flex-direction: column;
  gap: 16px;

  position: sticky;
  top: 14px;
}

.risk-card,
.controls-card {
  padding: 18px;
}

.risk-card-header,
.controls-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.risk-card-header h2,
.controls-header h2 {
  margin: 3px 0 0;
  font-size: 17px;
}

.reset-button {
  padding: 6px 10px;

  border: 1px solid var(--border);
  border-radius: 7px;

  background: white;
  color: var(--muted);

  font-size: 10px;
  font-weight: 700;
}

.reset-button:hover:not(:disabled) {
  background: var(--surface-soft);
}

.reset-button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.risk-change {
  margin-top: -5px;

  text-align: center;

  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
}

.risk-change.increase {
  color: var(--high);
}

.risk-change.decrease {
  color: var(--low);
}

.edited-badge {
  padding: 4px 7px;

  border-radius: 6px;

  background: var(--blue-soft);
  color: var(--blue);

  font-size: 9px;
  font-weight: 800;
}

/* SLIDERS */

.slider-control {
  padding: 13px 0;

  border-bottom: 1px solid var(--border);
}

.slider-control:last-of-type {
  border-bottom: 0;
}

.slider-header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.slider-header label {
  color: var(--text);
  font-size: 11px;
  font-weight: 600;
}

.slider-header strong {
  font-size: 11px;
}

input[type="range"] {
  width: 100%;
  height: 5px;

  margin: 9px 0 4px;

  accent-color: var(--blue);
  cursor: pointer;
}

input[type="range"].high {
  accent-color: var(--high);
}

input[type="range"].moderate {
  accent-color: var(--moderate);
}

input[type="range"].low {
  accent-color: var(--low);
}

.slider-range {
  display: flex;
  justify-content: space-between;

  color: #9aa4b2;
  font-size: 8px;
}

.simulation-message {
  margin-top: 12px;
  padding: 9px;

  border-radius: 8px;

  background: var(--blue-soft);
  color: var(--blue);

  font-size: 10px;
  line-height: 1.4;
}

.simulation-message span {
  margin-right: 4px;
}

/* FOOTER */

footer {
  display: flex;
  justify-content: space-between;

  margin-top: 18px;
  padding: 12px 2px;

  color: var(--muted);
  font-size: 10px;
}

footer > div {
  display: flex;
  align-items: center;
  gap: 6px;
}

.footer-dot {
  width: 6px;
  height: 6px;

  border-radius: 50%;
  background: var(--low);
}

/* LOADING */

.state-screen {
  min-height: 70vh;

  display: grid;
  place-items: center;

  padding: 30px;
  background: var(--bg);
}

.loading-box,
.error-box {
  width: min(420px, 100%);

  padding: 35px;

  text-align: center;

  background: white;
  border: 1px solid var(--border);
  border-radius: 15px;

  box-shadow: var(--shadow);
}

.loading-box h2,
.error-box h2 {
  margin: 12px 0 5px;
}

.loading-box p,
.error-box p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}

.loader {
  width: 36px;
  height: 36px;

  margin: auto;

  border: 3px solid #e5e7eb;
  border-top-color: var(--blue);
  border-radius: 50%;

  animation: spin 0.8s linear infinite;
}

.error-icon {
  width: 42px;
  height: 42px;

  display: grid;
  place-items: center;

  margin: auto;

  border-radius: 50%;

  background: var(--high-soft);
  color: var(--high);

  font-weight: 900;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* RESPONSIVE */

@media (max-width: 1250px) {
  .dashboard-grid {
    grid-template-columns: 250px minmax(0, 1fr);
  }

  .right-column {
    grid-column: 1 / -1;

    position: static;

    display: grid;
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 900px) {
  .app {
    padding: 0 16px 20px;
  }

  .topbar {
    margin-left: -16px;
    margin-right: -16px;
    padding: 0 16px;
  }

  .header-center,
  .model-badge {
    display: none;
  }

  .page-heading {
    flex-direction: column;
    align-items: flex-start;
  }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .queue-panel {
    position: static;
  }

  .right-column {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .page-heading h1 {
    font-size: 25px;
  }

  .stats-grid {
    grid-template-columns: 1fr 1fr;
  }

  .model-info {
    width: 100%;
    justify-content: space-between;
  }

  .patient-summary {
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
  }

  .risk-summary {
    width: 100%;
    justify-content: flex-start;
  }

  .card-heading {
    flex-direction: column;
  }

  .select-control {
    width: 100%;
    justify-content: space-between;
  }

  .select-control select {
    flex: 1;
  }

  footer {
    flex-direction: column;
    gap: 6px;
  }
}
</style>
