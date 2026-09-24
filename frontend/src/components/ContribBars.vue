<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import * as d3 from 'd3'

const props = defineProps({ items: Array, patient: Object, prediction: Object })
const viewMode = ref('simple')
const selectedExplanation = ref(null)

const sortedItems = computed(() => [...(props.items || [])].sort((a, b) => Math.abs(b.value) - Math.abs(a.value)))

const summary = computed(() => {
  const top = sortedItems.value.slice(0, 3)
  return top.map(d => ({
    label: d.label,
    icon: d.value > 0.15 ? '🔴' : (d.value > 0 ? '🟠' : '🟢'),
    impact: getSemantic(d.value)
  }))
})

// Default discussion prompts based on static rules (used if Groq fails or before loading)
const defaultDiscussionPrompts = computed(() => {
  const prompts = []
  const topLabels = sortedItems.value.slice(0, 3).map(d => d.key)
  if (topLabels.includes('prior_admissions')) prompts.push("Review recent hospital admissions and follow-up planning with your healthcare team.")
  if (topLabels.includes('length_of_stay')) prompts.push("Discuss your recent hospitalization and discharge/follow-up plan with your healthcare team.")
  if (topLabels.includes('charlson')) prompts.push("Ask your healthcare professional how your existing conditions are being followed.")
  if (topLabels.includes('ed_visits')) prompts.push("Discuss recent emergency department visits and potential preventative care.")
  if (prompts.length === 0) prompts.push("Discuss this predictive model's risk estimate during your next standard follow-up.")
  return prompts
})

function getSemantic(val) {
  const v = Math.abs(val)
  if (val === 0) return "Minimal influence"
  if (val < 0) return "Lower risk contribution"
  if (v > 0.15) return "Strong influence"
  if (v > 0.05) return "Moderate influence"
  return "Lower influence"
}

const animatedData = ref([])
const maxVal = computed(() => Math.max(0.08, d3.max(sortedItems.value, d => Math.abs(d.value)) * 1.1))
const scale = computed(() => d3.scaleLinear().domain([0, maxVal.value]).range([0, 50]))

// D3 tweening for numbers in Technical view
function animateNumbers() {
  const data = sortedItems.value
  if (animatedData.value.length === 0) {
    animatedData.value = data.map(d => ({ ...d, displayVal: 0 }))
  }

  d3.selection()
    .transition()
    .duration(700)
    .ease(d3.easeCubicOut)
    .tween("numbers", () => {
      const interpolators = data.map(d => {
        const oldTarget = animatedData.value.find(x => x.key === d.key)
        const oldVal = oldTarget ? (oldTarget.displayVal || 0) : 0
        return d3.interpolate(oldVal, d.value)
      })
      
      return (t) => {
        animatedData.value = data.map((d, i) => ({
          ...d,
          displayVal: interpolators[i](t)
        }))
      }
    })
}

onMounted(animateNumbers)
watch(() => props.items, animateNumbers)

function formatValue(d) {
  if (viewMode.value === 'technical') {
    const matched = animatedData.value.find(x => x.key === d.key)
    const val = matched ? matched.displayVal : d.value
    return `${val >= 0 ? '+' : '−'}${Math.abs(val * 100).toFixed(1)} pts`
  }
  return getSemantic(d.value)
}

// --------------------------------------------------
// GROQ AI LOGIC
// --------------------------------------------------
const groqCache = ref({})
const isAnalyzing = ref(false)
const groqError = ref(false)
const showGeneratedQuestions = ref(false)

async function fetchGroqExplanation() {
  if (!props.patient || !props.prediction) return null
  
  // Cache key could be patient ID + prediction tier to support RiskLab changes
  const cacheKey = `${props.patient.id}_${props.prediction.risk.toFixed(2)}`
  
  if (groqCache.value[cacheKey]) {
    return groqCache.value[cacheKey]
  }

  isAnalyzing.value = true
  groqError.value = false
  
  try {
    const payload = {
      patient: { patient_id: props.patient.id, ...props.patient.features },
      prediction: { risk_probability: props.prediction.risk, risk_category: props.prediction.tier },
      risk_factors: sortedItems.value.map(d => ({ name: d.label, contribution: d.value }))
    }
    
    const res = await fetch("/api/risk/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
    
    if (!res.ok) throw new Error("Groq API Error")
    const data = await res.json()
    
    groqCache.value[cacheKey] = data
    return data
  } catch (err) {
    console.error("Failed to fetch Groq explanation:", err)
    groqError.value = true
    return null
  } finally {
    isAnalyzing.value = false
  }
}

// Factor Click -> Show Explanation
async function showWhy(d) {
  selectedExplanation.value = {
    label: d.label,
    semantic: getSemantic(d.value),
    val: `${d.value >= 0 ? '+' : '−'}${Math.abs(d.value * 100).toFixed(1)} percentage points`,
    loading: true,
    aiExplanation: "",
    aiDiscussion: ""
  }

  const aiData = await fetchGroqExplanation()
  
  if (aiData && aiData.important_factors) {
    const factorMatch = aiData.important_factors.find(f => f.factor.toLowerCase() === d.label.toLowerCase() || d.label.toLowerCase().includes(f.factor.toLowerCase()))
    
    if (factorMatch) {
      selectedExplanation.value.aiExplanation = factorMatch.explanation
      selectedExplanation.value.aiDiscussion = factorMatch.discussion_point
    } else {
      selectedExplanation.value.aiExplanation = `The model gave this factor a ${selectedExplanation.value.semantic.toLowerCase()} on this patient's predicted probability.`
      selectedExplanation.value.aiDiscussion = "Review this factor with your care team."
    }
  } else {
    // Fallback if Groq fails
    selectedExplanation.value.aiExplanation = `The model gave this factor a ${selectedExplanation.value.semantic.toLowerCase()} on this patient's predicted probability.`
    selectedExplanation.value.aiDiscussion = "Review this factor with your care team."
  }
  selectedExplanation.value.loading = false
}

// Generate Questions Click
const generatedQuestionsList = ref([])

async function generateQuestions() {
  showGeneratedQuestions.value = true
  const aiData = await fetchGroqExplanation()
  
  if (aiData && aiData.questions_for_care_team) {
    generatedQuestionsList.value = aiData.questions_for_care_team
  } else {
    // Fallback
    generatedQuestionsList.value = [
      "Could we review the reasons for my recent hospital admissions?",
      "What follow-up should I have after my recent hospitalization?",
      "Are any of my existing conditions important to review?"
    ]
  }
}

// Reset state when patient changes
watch(() => props.patient, () => {
  showGeneratedQuestions.value = false
  generatedQuestionsList.value = []
  groqError.value = false
  chatMessages.value = []
})

// Current patient active data
const currentAiData = computed(() => {
  if (!props.patient || !props.prediction) return null
  const cacheKey = `${props.patient.id}_${props.prediction.risk.toFixed(2)}`
  return groqCache.value[cacheKey] || null
})

// --------------------------------------------------
// CHAT LOGIC
// --------------------------------------------------
const chatMessages = ref([])
const chatInput = ref('')
const isChatting = ref(false)

async function sendChatMessage() {
  if (!chatInput.value.trim() || isChatting.value) return
  
  const userText = chatInput.value.trim()
  chatMessages.value.push({ role: 'user', content: userText })
  chatInput.value = ''
  isChatting.value = true
  
  try {
    const payload = {
      patient: { patient_id: props.patient.id, ...props.patient.features },
      prediction: { risk_probability: props.prediction.risk, risk_category: props.prediction.tier },
      risk_factors: sortedItems.value.map(d => ({ name: d.label, contribution: d.value })),
      messages: chatMessages.value
    }
    
    const res = await fetch("/api/risk/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
    
    if (!res.ok) throw new Error("Chat API Error")
    const data = await res.json()
    
    chatMessages.value.push({ role: 'assistant', content: data.reply })
  } catch (err) {
    console.error("Failed to send chat message:", err)
    chatMessages.value.push({ role: 'assistant', content: "Sorry, I am currently unable to answer questions." })
  } finally {
    isChatting.value = false
  }
}
</script>

<template>
  <div class="shadcn-container">
    <div class="bars-header">
      <div class="shadcn-tabs">
        <button :class="{ active: viewMode === 'simple' }" @click="viewMode = 'simple'">Simple View</button>
        <button :class="{ active: viewMode === 'technical' }" @click="viewMode = 'technical'">Technical View</button>
      </div>
    </div>

    <!-- Shadcn Card for Summary -->
    <div class="shadcn-card summary-card">
      <div class="shadcn-card-header">
        <h3 class="shadcn-card-title">AI RISK EXPLANATION</h3>
        <p v-if="currentAiData" class="shadcn-card-description">{{ currentAiData.summary }}</p>
        <p v-else class="shadcn-card-description">The model's prediction is mainly influenced by:</p>
      </div>
      <div class="shadcn-card-content">
        <div v-for="item in summary" :key="item.label" class="summary-row">
          <div class="summary-label"><span>{{ item.icon }}</span> {{ item.label }}</div>
          <div class="summary-val">{{ item.impact }}</div>
        </div>
      </div>
    </div>
    
    <div class="section-label">Model Influence</div>
    
    <!-- Loading overlay for AI -->
    <div v-if="isAnalyzing" class="ai-loading">
      <div class="dots">
        <span>Analyzing</span><span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
      </div>
    </div>
    
    <div v-if="groqError" class="ai-error">
      AI explanation is temporarily unavailable. Displaying standard model results.
    </div>

    <!-- HTML Bar Chart (Shadcn style) -->
    <div class="chart-container" :style="{ opacity: isAnalyzing ? 0.5 : 1 }">
      <div class="center-line"></div>
      
      <div v-for="d in sortedItems" :key="d.key" class="chart-row group">
        <div class="row-label">{{ d.label }}</div>
        
        <div class="row-viz">
          <div class="bar-fill" 
               :class="d.value > 0 ? 'positive' : (d.value < 0 ? 'negative' : 'neutral')"
               :style="{ 
                 width: scale(Math.abs(d.value)) + '%', 
                 left: d.value >= 0 ? '50%' : (50 - scale(Math.abs(d.value))) + '%' 
               }">
          </div>
        </div>
        
        <div class="row-value" :class="d.value > 0 ? 'text-destructive' : (d.value < 0 ? 'text-primary' : 'text-muted')">
          {{ formatValue(d) }}
        </div>
        
        <button class="shadcn-btn-outline outline-why" @click="showWhy(d)">Why?</button>
      </div>
    </div>
    
    <!-- Shadcn Modal -->
    <div v-if="selectedExplanation" class="shadcn-dialog-overlay" @click.self="selectedExplanation = null">
      <div class="shadcn-dialog-content">
        <div class="shadcn-dialog-header">
          <h2 class="shadcn-dialog-title">{{ selectedExplanation.label }}</h2>
          <p class="shadcn-dialog-description">{{ selectedExplanation.semantic }}</p>
        </div>
        <div class="shadcn-dialog-body">
          <div v-if="selectedExplanation.loading" class="ai-loading-modal">
            Generating explanation...
          </div>
          <template v-else>
            <div style="font-size:12px; font-weight:600; color:hsl(var(--foreground)); margin-bottom:8px;">WHY?</div>
            <p class="expl-text">"{{ selectedExplanation.aiExplanation }}"</p>
            
            <div class="stat-box" style="margin-bottom: 16px;">
              <div class="stat-row">
                <span class="stat-label">Technical model contribution</span>
                <span class="stat-val">{{ selectedExplanation.val }}</span>
              </div>
            </div>
            
            <div style="font-size:12px; font-weight:600; color:hsl(var(--foreground)); margin-bottom:8px;">WHAT TO DISCUSS</div>
            <p class="expl-text">"{{ selectedExplanation.aiDiscussion }}"</p>
          </template>
        </div>
        <div class="shadcn-dialog-footer">
          <button class="shadcn-btn" @click="selectedExplanation = null">Close</button>
        </div>
      </div>
    </div>
    
    <!-- Discussion Prompts -->
    <div class="discussion-section">
      <h4 class="disc-title">WHAT TO DISCUSS WITH YOUR CARE TEAM</h4>
      <ul class="shadcn-list">
        <!-- Display AI generated next steps if available, otherwise default -->
        <template v-if="currentAiData && currentAiData.next_steps">
          <li v-for="step in currentAiData.next_steps" :key="step">✓ {{ step }}</li>
        </template>
        <template v-else>
          <li v-for="prompt in defaultDiscussionPrompts" :key="prompt">✓ {{ prompt }}</li>
        </template>
      </ul>
      
      <div class="questions-section">
        <button v-if="!showGeneratedQuestions" class="shadcn-btn-outline gen-btn" @click="generateQuestions" :disabled="isAnalyzing">
          Generate Questions for My Care Team
        </button>
        
        <div v-if="showGeneratedQuestions" class="questions-list">
          <h5 style="margin: 0 0 12px; font-size: 13px; font-weight: 600;">QUESTIONS TO DISCUSS</h5>
          <ol v-if="generatedQuestionsList.length > 0">
            <li v-for="(q, i) in generatedQuestionsList" :key="i" class="animate-q" :style="{ animationDelay: (i * 0.15) + 's' }">
              {{ q }}
            </li>
          </ol>
          <div v-else-if="isAnalyzing" style="font-size: 13px; color: hsl(var(--muted-foreground));">Generating questions...</div>
        </div>
      </div>
      
      <div class="chat-section">
        <h5 style="margin: 0 0 12px; font-size: 13px; font-weight: 600;">ASK AI ASSISTANT</h5>
        <div class="chat-messages" v-if="chatMessages.length > 0">
          <div v-for="(msg, i) in chatMessages" :key="i" class="chat-message" :class="msg.role">
            <div class="msg-bubble">{{ msg.content }}</div>
          </div>
          <div v-if="isChatting" class="chat-message assistant">
            <div class="msg-bubble loading"><span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></div>
          </div>
        </div>
        <div class="chat-input-row">
          <input v-model="chatInput" @keyup.enter="sendChatMessage" placeholder="Ask a follow-up question..." class="chat-input" :disabled="isChatting" />
          <button class="shadcn-btn-outline" @click="sendChatMessage" :disabled="isChatting || !chatInput.trim()">Send</button>
        </div>
      </div>
      
      <p class="disclaimer">This explanation describes model behavior and is not a diagnosis or treatment recommendation.</p>
    </div>
  </div>
</template>

<style scoped>
/* Shadcn UI Variables & Base */
.shadcn-container {
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --muted: 210 40% 96.1%;
  --muted-foreground: 215.4 16.3% 46.9%;
  --border: 214.3 31.8% 91.4%;
  --primary: 180 100% 25%;
  --destructive: 0 84.2% 60.2%;
  --radius: 0.5rem;
  
  font-family: ui-sans-serif, system-ui, sans-serif;
  color: hsl(var(--foreground));
}

/* Typography */
.text-muted { color: hsl(var(--muted-foreground)); }
.text-destructive { color: hsl(var(--destructive)); }
.text-primary { color: hsl(var(--primary)); }
.section-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: hsl(var(--muted-foreground)); margin: 1.5rem 0 0.75rem; }

/* Tabs */
.shadcn-tabs { display: inline-flex; height: 36px; align-items: center; justify-content: center; border-radius: var(--radius); background-color: hsl(var(--muted)); padding: 0.25rem; margin-bottom: 1rem; }
.shadcn-tabs button { display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; border-radius: calc(var(--radius) - 2px); padding: 0.25rem 0.75rem; font-size: 0.875rem; font-weight: 500; transition: all 0.2s; border: none; background: transparent; color: hsl(var(--muted-foreground)); cursor: pointer; }
.shadcn-tabs button.active { background-color: hsl(var(--background)); color: hsl(var(--foreground)); box-shadow: 0 1px 2px rgba(0,0,0,0.05); }

/* Card */
.shadcn-card { border-radius: var(--radius); border: 1px solid hsl(var(--border)); background-color: hsl(var(--background)); box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
.summary-card { margin-bottom: 1rem; }
.shadcn-card-header { padding: 1.25rem 1.25rem 0.5rem; }
.shadcn-card-title { font-size: 1rem; font-weight: 600; line-height: 1; margin: 0 0 0.375rem; letter-spacing: -0.025em; }
.shadcn-card-description { font-size: 0.875rem; color: hsl(var(--muted-foreground)); margin: 0; line-height: 1.4; }
.shadcn-card-content { padding: 0 1.25rem 1.25rem; }
.summary-row { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; border-bottom: 1px solid hsl(var(--border)); font-size: 0.875rem; }
.summary-row:last-child { border-bottom: none; padding-bottom: 0; }
.summary-label { font-weight: 500; }
.summary-val { color: hsl(var(--muted-foreground)); }

/* HTML Chart Layout */
.chart-container { position: relative; display: flex; flex-direction: column; gap: 0.5rem; padding: 0.5rem 0; transition: opacity 0.3s; }
.center-line { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background-color: hsl(var(--border)); z-index: 1; border-left: 1px dashed hsl(var(--muted-foreground)); opacity: 0.3; }

.chart-row { display: grid; grid-template-columns: minmax(120px, 1.5fr) 2fr minmax(120px, 1fr) auto; align-items: center; gap: 1rem; padding: 0.5rem; border-radius: var(--radius); transition: background-color 0.2s; }
.chart-row:hover { background-color: hsl(var(--muted) / 0.5); }

.row-label { font-size: 0.875rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; z-index: 2; }

.row-viz { position: relative; height: 1.25rem; width: 100%; display: flex; align-items: center; z-index: 2; }
.bar-fill { position: absolute; height: 100%; border-radius: 3px; transition: width 0.7s cubic-bezier(0.16, 1, 0.3, 1), left 0.7s cubic-bezier(0.16, 1, 0.3, 1), background-color 0.7s ease; }
.bar-fill.positive { background-color: hsl(var(--destructive) / 0.85); border: 1px solid hsl(var(--destructive)); }
.bar-fill.negative { background-color: hsl(var(--primary) / 0.85); border: 1px solid hsl(var(--primary)); }
.bar-fill.neutral { background-color: hsl(var(--muted-foreground) / 0.5); }
.chart-row:hover .bar-fill { filter: brightness(1.1); }

.row-value { font-size: 0.875rem; font-weight: 600; z-index: 2; white-space: nowrap; }

/* Buttons */
.shadcn-btn-outline { display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius); font-size: 0.75rem; font-weight: 500; height: 1.75rem; padding: 0 0.75rem; background: transparent; border: 1px solid hsl(var(--border)); color: hsl(var(--foreground)); cursor: pointer; transition: all 0.2s; white-space: nowrap; z-index: 2; }
.shadcn-btn-outline:hover { background-color: hsl(var(--muted)); color: hsl(var(--foreground)); }
.shadcn-btn-outline:disabled { opacity: 0.5; cursor: not-allowed; }

.shadcn-btn { display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius); font-size: 0.875rem; font-weight: 500; height: 2.25rem; padding: 0 1rem; background-color: hsl(var(--foreground)); color: hsl(var(--background)); border: none; cursor: pointer; transition: background-color 0.2s; width: 100%; }
.shadcn-btn:hover { background-color: hsl(var(--foreground) / 0.9); }

/* Dialog */
.shadcn-dialog-overlay { position: fixed; inset: 0; z-index: 100; background-color: rgba(255, 255, 255, 0.8); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; animation: fadeIn 0.2s ease-out; }
.shadcn-dialog-content { background-color: hsl(var(--background)); border: 1px solid hsl(var(--border)); border-radius: calc(var(--radius) + 2px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -4px rgba(0,0,0,0.1); width: 90%; max-width: 425px; padding: 1.5rem; animation: slideUp 0.2s ease-out; }
.shadcn-dialog-header { display: flex; flex-direction: column; gap: 0.375rem; margin-bottom: 1.25rem; }
.shadcn-dialog-title { font-size: 1.125rem; font-weight: 600; margin: 0; line-height: 1; letter-spacing: -0.025em; }
.shadcn-dialog-description { font-size: 0.875rem; color: hsl(var(--muted-foreground)); margin: 0; }
.shadcn-dialog-body { margin-bottom: 1.5rem; }
.expl-text { font-size: 0.875rem; color: hsl(var(--muted-foreground)); line-height: 1.5; margin-bottom: 1rem; margin-top: 0; font-style: italic; }
.stat-box { background-color: hsl(var(--muted) / 0.5); border-radius: var(--radius); padding: 0.75rem; display: flex; flex-direction: column; gap: 0.5rem; border: 1px solid hsl(var(--border)); }
.stat-row { display: flex; justify-content: space-between; font-size: 0.875rem; }
.stat-label { color: hsl(var(--muted-foreground)); }
.stat-val { font-weight: 600; color: hsl(var(--foreground)); }

/* Discussion */
.discussion-section { margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid hsl(var(--border)); }
.disc-title { font-size: 0.875rem; font-weight: 600; margin-bottom: 1rem; color: hsl(var(--foreground)); letter-spacing: -0.01em; }
.shadcn-list { margin: 0 0 1.5rem; padding-left: 0; list-style: none; font-size: 0.875rem; color: hsl(var(--muted-foreground)); line-height: 1.6; }
.shadcn-list li { margin-bottom: 0.5rem; display: flex; gap: 6px; }

.questions-section { margin-bottom: 1rem; padding: 1rem; background: hsl(var(--muted) / 0.3); border-radius: var(--radius); border: 1px solid hsl(var(--border)); }
.gen-btn { width: 100%; height: 2.25rem; font-size: 0.875rem; }
.questions-list ol { margin: 0; padding-left: 1.25rem; font-size: 0.875rem; color: hsl(var(--foreground)); line-height: 1.6; }
.questions-list li { margin-bottom: 0.75rem; font-weight: 500; }
.animate-q { opacity: 0; transform: translateY(5px); animation: qFadeIn 0.4s forwards; }

.chat-section { margin-bottom: 1.5rem; padding: 1rem; background: hsl(var(--background)); border-radius: var(--radius); border: 1px solid hsl(var(--border)); box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.chat-messages { max-height: 250px; overflow-y: auto; margin-bottom: 1rem; display: flex; flex-direction: column; gap: 0.5rem; padding-right: 0.25rem; }
.chat-message { display: flex; width: 100%; }
.chat-message.user { justify-content: flex-end; }
.chat-message.assistant { justify-content: flex-start; }
.msg-bubble { max-width: 85%; padding: 0.5rem 0.75rem; border-radius: 0.5rem; font-size: 0.875rem; line-height: 1.5; word-wrap: break-word; white-space: pre-wrap; }
.chat-message.user .msg-bubble { background: hsl(var(--foreground)); color: hsl(var(--background)); border-bottom-right-radius: 0; }
.chat-message.assistant .msg-bubble { background: hsl(var(--muted)); color: hsl(var(--foreground)); border-bottom-left-radius: 0; }
.chat-input-row { display: flex; gap: 0.5rem; }
.chat-input { flex: 1; padding: 0.5rem 0.75rem; border-radius: var(--radius); border: 1px solid hsl(var(--border)); font-size: 0.875rem; background: hsl(var(--background)); color: hsl(var(--foreground)); outline: none; transition: border-color 0.2s; }
.chat-input:focus { border-color: hsl(var(--muted-foreground)); }
.chat-input:disabled { opacity: 0.5; cursor: not-allowed; }

.disclaimer { font-size: 0.75rem; color: hsl(var(--muted-foreground)); font-style: italic; margin: 0; }

/* AI States */
.ai-loading { display: flex; align-items: center; justify-content: center; padding: 0.5rem; font-size: 0.75rem; color: hsl(var(--muted-foreground)); margin-bottom: 0.5rem; }
.ai-error { font-size: 0.75rem; color: hsl(var(--destructive)); padding: 0.5rem; background: hsl(var(--destructive) / 0.1); border-radius: var(--radius); margin-bottom: 0.5rem; text-align: center; }
.ai-loading-modal { font-size: 0.875rem; color: hsl(var(--muted-foreground)); text-align: center; padding: 2rem 0; animation: pulse 1.5s infinite; }

.dots .dot { animation: dot 1.4s infinite; opacity: 0; display: inline-block; font-weight: bold; margin-left: 2px; }
.dots .dot:nth-child(2) { animation-delay: 0.2s; }
.dots .dot:nth-child(3) { animation-delay: 0.4s; }
.dots .dot:nth-child(4) { animation-delay: 0.6s; }

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideUp { from { opacity: 0; transform: translateY(10px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes qFadeIn { to { opacity: 1; transform: translateY(0); } }
@keyframes dot { 0% { opacity: 0; } 50% { opacity: 1; } 100% { opacity: 0; } }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

/* Responsive adjustments */
@media (max-width: 768px) {
  .chart-row { grid-template-columns: 1fr; gap: 0.25rem; position: relative; padding-bottom: 1rem; border-bottom: 1px solid hsl(var(--border)); }
  .row-viz { margin: 0.5rem 0; height: 1rem; }
  .center-line { display: none; }
  .bar-fill.positive { left: 0 !important; }
  .bar-fill.negative { right: auto !important; left: 0 !important; }
  .outline-why { position: absolute; right: 0.5rem; bottom: 0.5rem; }
  .row-value { margin-bottom: 0.5rem; }
}
</style>
