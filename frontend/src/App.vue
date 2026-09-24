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
const showLayers = ref(false)
const showNetwork = ref(false)
const error = ref('')
let timer, seq = 0

const sel = computed(() => cohort.value.find((p) => p.id === selId.value))
const label = (k) => meta.value.features.find((f) => f.key === k).label
const xFeature = computed(() => xKey.value === 'risk' ? {key: 'risk', label: 'Readmission Probability', min: 0, max: 1, step: 0.01} : meta.value.features.find((f) => f.key === xKey.value))
const yFeature = computed(() => yKey.value === 'risk' ? {key: 'risk', label: 'Readmission Probability', min: 0, max: 1, step: 0.01} : meta.value.features.find((f) => f.key === yKey.value))
const zFeature = computed(() => zKey.value === 'risk' ? {key: 'risk', label: 'Readmission Probability', min: 0, max: 1, step: 0.01} : meta.value.features.find((f) => f.key === zKey.value))
const dirty = computed(() => sel.value && meta.value.features.some((f) => values[f.key] !== sel.value.features[f.key]))
const delta = computed(() => (result.value && sel.value ? (result.value.risk - sel.value.risk) * 100 : 0))
const queue = computed(() => cohort.value.filter((p) => filter.value === 'all' || p.tier === filter.value))
const items = computed(() => result.value.contributions.map((c) => ({ ...c, label: label(c.key) })))
const whatIf = computed(() => (dirty.value ? { features: values, risk: result.value.risk, tier: result.value.tier } : null))
const counts = computed(() => Object.fromEntries(['high', 'moderate', 'low'].map((t) => [t, cohort.value.filter((p) => p.tier === t).length])))

function select(p) {
  selId.value = p.id
  Object.assign(values, p.features)
  result.value = { risk: p.risk, tier: p.tier, contributions: p.contributions }
}
function onSlide() {
  clearTimeout(timer)
  timer = setTimeout(async () => {
    const mine = ++seq
    try {
      const r = await fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ features: { ...values } }),
      })
      if (!r.ok) throw new Error(await r.text())
      const data = await r.json()
      if (mine === seq) result.value = data
    } catch (e) {
      error.value = 'Could not reach the prediction service. Start the API on port 8000.'
    }
  }, 90)
}
const fmt = (f, v) => (f.step < 1 ? Number(v).toFixed(1) : v)

onMounted(async () => {
  try {
    meta.value = await (await fetch('/api/meta')).json()
    cohort.value = await (await fetch('/api/cohort')).json()
    select(cohort.value[0])
  } catch (e) {
    error.value = 'Could not reach the prediction service. Start the API on port 8000.'
  }
})
</script>

<template>
  <div v-if="error" class="fail">{{ error }}</div>
  <div v-else-if="!meta || !result" class="fail">Loading model and cohort…</div>
  <div v-else class="shell">
    <header class="app-header">
      <div>
        <h1>Clinical Risk Intelligence</h1>
        <p>Synthetic cohort of {{ cohort.length }} discharges. 30-day readmission prediction model.</p>
      </div>
      <div class="tally">
        <span v-for="t in ['high', 'moderate', 'low']" :key="t"><i :class="t" />{{ counts[t] }} {{ t }}</span>
      </div>
    </header>

    <aside class="queue">
      <h2>Triage queue</h2>
      <div class="chips" role="group" aria-label="Filter by tier">
        <button v-for="t in ['all', 'critical', 'high', 'moderate', 'low']" :key="t" :class="{ on: filter === t }" @click="filter = t">{{ t }}</button>
      </div>
      <transition-group name="list" tag="ul">
        <li v-for="p in queue" :key="p.id">
          <button :class="{ on: p.id === selId }" @click="select(p)">
            <i :class="p.tier" />
            <span class="id">{{ p.id }}</span>
            <span class="drv">{{ label(p.top_driver) }}</span>
            <b>{{ Math.round(p.risk * 100) }}%</b>
          </button>
        </li>
      </transition-group>
    </aside>

    <main>
      <section class="card three-d-landscape" style="background: #0f172a; color: #fff; border: 1px solid #1e293b;">
        <div class="row" style="margin-bottom: 12px;">
          <h2 style="color: #f8fafc; font-weight: 600;">3D Risk Landscape</h2>
          <div class="axes-controls" style="display:flex; gap:12px;">
            <label style="color: #cbd5e1;">X Axis
              <select v-model="xKey" style="background:#1e293b; color:#fff; border-color:#334155;">
                <option v-for="f in [{key: 'risk', label: 'Readmission Probability'}, ...meta.features]" :key="f.key" :value="f.key">{{ f.label }}</option>
              </select>
            </label>
            <label style="color: #cbd5e1;">Y Axis
              <select v-model="yKey" style="background:#1e293b; color:#fff; border-color:#334155;">
                <option v-for="f in [{key: 'risk', label: 'Readmission Probability'}, ...meta.features]" :key="f.key" :value="f.key">{{ f.label }}</option>
              </select>
            </label>
            <label style="color: #cbd5e1;">Depth
              <select v-model="zKey" style="background:#1e293b; color:#fff; border-color:#334155;">
                <option v-for="f in [{key: 'risk', label: 'Readmission Probability'}, ...meta.features]" :key="f.key" :value="f.key">{{ f.label }}</option>
              </select>
            </label>
          </div>
          <div class="toggles" style="display:flex; gap:12px; margin-top: 12px;">
            <label style="color: #cbd5e1;"><input type="checkbox" v-model="showLayers" /> Show Risk Layers</label>
            <label style="color: #cbd5e1;"><input type="checkbox" v-model="showNetwork" /> Show Patient Network</label>
          </div>
        </div>
        <RiskScatter :patients="cohort" :filter="filter" :selected="sel" :what-if="whatIf" :x-feature="xFeature" :y-feature="yFeature" :z-feature="zFeature" :tiers="meta.tiers" :show-layers="showLayers" :show-network="showNetwork" @pick="select" />
      </section>
      <section class="card">
        <div class="row">
          <h2 style="color:#1e293b;">Why is the model predicting this risk?</h2>
          <span title="This section explains which recorded factors had the largest influence on the model's prediction. It is not a medical diagnosis." style="cursor:help; font-size:16px; color:var(--accent);">ⓘ</span>
        </div>
        <p class="hint">These factors influenced the model's estimated 30-day readmission probability.</p>
        <ContribBars :items="items" :patient="sel" :prediction="sel ? { risk: sel.risk, tier: sel.tier } : null" />
      </section>
    </main>

    <aside class="panel">
      <section class="card">
        <div class="row">
          <h2>{{ sel.id }}</h2>
          <button class="reset" :disabled="!dirty" @click="select(sel)">Reset to chart values</button>
        </div>
        <RiskGauge :risk="result.risk" :tier="result.tier" :tiers="meta.tiers" />
        <p class="delta" :class="{ up: delta > 0.05, down: delta < -0.05 }">
          <template v-if="!dirty">Recorded risk at discharge</template>
          <template v-else>{{ delta >= 0 ? '+' : '−' }}{{ Math.abs(delta).toFixed(1) }} points from recorded {{ Math.round(sel.risk * 100) }}%</template>
        </p>
      </section>
      <section class="card">
        <h2>RISKLAB: What-if simulation</h2>
        <div v-for="f in meta.features" :key="f.key" class="slider">
          <label :for="f.key">
            <span>{{ f.label }}<em v-if="values[f.key] !== sel.features[f.key]"> (edited)</em></span>
            <b>{{ fmt(f, values[f.key]) }} {{ f.unit }}</b>
          </label>
          <input :id="f.key" type="range" v-model.number="values[f.key]" :min="f.min" :max="f.max" :step="f.step" :class="result.tier" @input="onSlide" />
        </div>
        <p class="hint" style="margin-top: 10px;">Hypothetical model simulation, not a clinical recommendation.</p>
      </section>
      <section class="card">
        <h2>Patient Risk Journey</h2>
        <RiskJourney :risk="result.risk" :patient-id="sel.id" />
      </section>
    </aside>
    <footer>Demonstration on synthetic data. Not validated for clinical decisions.</footer>
  </div>
</template>

<style>
:root {
  --paper: #eef2f6; --panel: rgba(255,255,255,0.85); --ink: #14222e; --muted: #5b6b78; --line: rgba(216, 224, 230, 0.6); --accent: #1f5f8b;
  --low: #2e8b6a; --moderate: #d9992b; --high: #c8473f;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.45 'Public Sans', system-ui, sans-serif; overflow-x: hidden; }
h1 { font-size: 26px; margin: 0 0 2px; letter-spacing: -0.01em; color: #1e293b; }
h2 { font-size: 16px; margin: 0 0 10px; text-transform: uppercase; letter-spacing: 0.05em; color: #475569; }
p { margin: 0; color: var(--muted); }
button, select { font: inherit; color: inherit; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.fail { padding: 60px 24px; text-align: center; color: var(--muted); }
.shell { display: grid; grid-template-columns: 290px minmax(0, 1fr) 340px; gap: 20px; padding: 24px; max-width: 1600px; margin: 0 auto; }

/* Staggered Animations */
.app-header { animation: slideDown 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards; opacity: 0; grid-column: 1 / -1; display: flex; justify-content: space-between; align-items: end; flex-wrap: wrap; gap: 8px; padding-bottom: 16px; border-bottom: 1px solid var(--line); margin-bottom: 8px; }
.queue { animation: slideRight 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.2s forwards; opacity: 0; align-self: start; position: sticky; top: 12px; }
main { animation: scaleIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.4s forwards; opacity: 0; display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.panel { animation: slideLeft 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.6s forwards; opacity: 0; display: flex; flex-direction: column; gap: 16px; min-width: 0; }
footer { grid-column: 1 / -1; font-size: 13px; color: var(--muted); text-align: center; padding: 20px 0; animation: fade 1s 1s forwards; opacity: 0; }

@keyframes slideDown { from { opacity: 0; transform: translateY(-20px); } to { opacity: 1; transform: translateY(0); } }
@keyframes slideRight { from { opacity: 0; transform: translateX(-30px); } to { opacity: 1; transform: translateX(0); } }
@keyframes slideLeft { from { opacity: 0; transform: translateX(30px); } to { opacity: 1; transform: translateX(0); } }
@keyframes scaleIn { from { opacity: 0; transform: scale(0.97); } to { opacity: 1; transform: scale(1); } }
@keyframes fade { to { opacity: 1; } }

.tally { display: flex; gap: 16px; font-weight: 500; }
i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
i.low { background: var(--low); } i.moderate { background: var(--moderate); } i.high { background: var(--high); } i.critical { background: #ff1100; }
.card, .queue { 
  background: var(--panel); 
  border: 1px solid var(--line); 
  border-radius: 12px; 
  padding: 16px; 
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.08);
}
.three-d-landscape {
  background: rgba(15, 23, 42, 0.95) !important;
  backdrop-filter: blur(20px);
  border: 1px solid rgba(30, 41, 59, 0.8) !important;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3) !important;
}
.row { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.row label { font-size: 13px; color: var(--muted); }
select { border: 1px solid var(--line); border-radius: 6px; padding: 4px 6px; background: #fff; margin-left: 4px; }
.hint { font-size: 13px; margin: -6px 0 6px; }
.queue { align-self: start; position: sticky; top: 12px; }
.chips { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
.chips button { border: 1px solid var(--line); background: rgba(255,255,255,0.5); border-radius: 999px; padding: 4px 12px; font-size: 13px; cursor: pointer; text-transform: capitalize; transition: all 0.3s ease; font-weight: 500; }
.chips button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
.chips button.on { background: var(--ink); color: #fff; border-color: var(--ink); box-shadow: 0 0 10px rgba(20, 34, 46, 0.2); }

.queue ul { list-style: none; margin: 0; padding: 0; max-height: calc(100vh - 170px); overflow-y: auto; overflow-x: hidden; transform: translateZ(0); will-change: scroll-position; contain: paint; overscroll-behavior: contain; }
.queue li button { width: 100%; display: grid; grid-template-columns: 16px 58px 1fr auto; align-items: center; text-align: left; padding: 10px 8px; border: 0; border-bottom: 1px solid var(--line); background: none; cursor: pointer; transition: all 0.3s ease; position: relative; }
.queue li button:hover { transform: translateX(4px); background: rgba(31, 95, 139, 0.03); box-shadow: -2px 0 0 var(--accent); }
.queue li button.on { background: rgba(31, 95, 139, 0.08); box-shadow: -3px 0 0 var(--accent); }

/* List Transitions */
.list-enter-active, .list-leave-active { transition: all 0.4s ease; }
.list-enter-from, .list-leave-to { opacity: 0; transform: translateX(-30px); }
.list-leave-active { position: absolute; width: 100%; }

.drv { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 8px; }
.reset { border: 1px solid var(--line); background: #fff; border-radius: 6px; padding: 4px 12px; font-size: 13px; cursor: pointer; transition: all 0.2s ease; }
.reset:hover:not(:disabled) { transform: scale(1.02); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.reset:active:not(:disabled) { transform: scale(0.98); }
.reset:disabled { opacity: 0.4; cursor: default; }
.delta { text-align: center; font-weight: 500; }
.delta.up { color: var(--high); } .delta.down { color: var(--low); }
.slider { margin-bottom: 12px; }
.slider label { display: flex; justify-content: space-between; font-size: 14px; }
.slider em { color: var(--accent); font-style: normal; font-size: 12px; }
input[type='range'] { width: 100%; margin: 4px 0 0; accent-color: var(--accent); transition: all 0.3s ease; }
input[type='range']:hover { filter: brightness(1.2); }
input[type='range']:focus { outline: none; filter: drop-shadow(0 0 4px var(--accent)); }
input.low { accent-color: var(--low); } input.moderate { accent-color: var(--moderate); } input.high { accent-color: var(--high); }
@media (max-width: 1100px) { .shell { grid-template-columns: 1fr; } .queue { position: static; } .queue ul { max-height: 260px; } }

</style>
