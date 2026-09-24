<script setup>
import { ref, watch, onMounted } from 'vue'
import * as d3 from 'd3'

const props = defineProps({ risk: Number, patientId: String })
const el = ref(null)
const tooltip = ref({ visible: false, x: 0, y: 0, day: '', risk: 0 })

function draw() {
  const svg = d3.select(el.value)
  svg.selectAll('*').remove()
  
  if (!props.risk) return;
  
  // Synthetic data generation for demo purposes
  const currentRisk = props.risk * 100;
  // Generate past 4 days leading to current risk
  const data = [
    { day: 'Day 1', val: Math.max(0, currentRisk - 25 + Math.random()*10) },
    { day: 'Day 3', val: Math.max(0, currentRisk - 15 + Math.random()*10) },
    { day: 'Day 5', val: Math.max(0, currentRisk - 5 + Math.random()*5) },
    { day: 'Day 7 (Now)', val: currentRisk }
  ]
  
  const W = 300, H = 150, M = { t: 20, r: 20, b: 30, l: 40 };
  svg.attr('viewBox', `0 0 ${W} ${H}`)
  
  const x = d3.scalePoint().domain(data.map(d => d.day)).range([M.l, W - M.r])
  const y = d3.scaleLinear().domain([0, Math.max(100, currentRisk + 10)]).range([H - M.b, M.t])
  
  const line = d3.line().x(d => x(d.day)).y(d => y(d.val)).curve(d3.curveMonotoneX)
  
  // Axes
  svg.append('g').attr('transform', `translate(0,${H - M.b})`).call(d3.axisBottom(x)).attr('color', '#94a3b8')
  svg.append('g').attr('transform', `translate(${M.l},0)`).call(d3.axisLeft(y).ticks(4).tickFormat(d => d + '%')).attr('color', '#94a3b8')
  
  // Path with transition
  const path = svg.append('path')
    .datum(data)
    .attr('fill', 'none')
    .attr('stroke', '#3b82f6')
    .attr('stroke-width', 2.5)
    .attr('d', line)
    
  const totalLength = path.node().getTotalLength();
  
  path
    .attr('stroke-dasharray', totalLength + ' ' + totalLength)
    .attr('stroke-dashoffset', totalLength)
    .transition()
    .duration(1000)
    .attr('stroke-dashoffset', 0);
    
  // Points
  svg.selectAll('circle.pt').data(data).join('circle').attr('class', 'pt')
    .attr('cx', d => x(d.day)).attr('cy', d => y(d.val)).attr('r', 4)
    .attr('fill', '#0f172a').attr('stroke', '#3b82f6').attr('stroke-width', 2)
    .attr('opacity', 0)
    .transition().delay((d,i) => i*250).duration(500)
    .attr('opacity', 1)
    
  svg.selectAll('circle.pt')
    .on('mouseenter', function(e, d) {
      d3.select(this).transition().duration(200).attr('r', 6).attr('fill', '#3b82f6')
      const rect = el.value.getBoundingClientRect();
      tooltip.value = {
        visible: true,
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        day: d.day,
        risk: Math.round(d.val)
      }
    })
    .on('mouseleave', function() {
      d3.select(this).transition().duration(200).attr('r', 4).attr('fill', '#0f172a')
      tooltip.value.visible = false
    })
}

onMounted(draw)
watch(() => props.patientId, draw)
</script>

<template>
  <div class="journey-container">
    <div v-if="tooltip.visible" class="journey-tooltip" :style="{ left: tooltip.x + 15 + 'px', top: tooltip.y + 15 + 'px' }">
      <div style="font-weight: bold; margin-bottom: 4px; font-size: 12px; color:#f8fafc;">{{ tooltip.day.toUpperCase() }}</div>
      <div style="font-size: 11px; color:#cbd5e1;">Predicted risk: <b style="color:#fff;">{{ tooltip.risk }}%</b></div>
      <div style="font-size: 11px; color:#cbd5e1; margin-top:4px;">Factors: Admissions: 2, ED visits: 1</div>
    </div>
    <svg ref="el" width="100%" height="150px"></svg>
    <p class="disclaimer">Synthetic demo data. Not actual patient history.</p>
  </div>
</template>

<style scoped>
.journey-container { width: 100%; position: relative; }
.disclaimer { font-size: 11px; color: #64748b; text-align: center; margin-top: 5px; }
.journey-tooltip {
  position: absolute;
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid #3b82f6;
  padding: 8px 12px;
  border-radius: 6px;
  pointer-events: none;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  backdrop-filter: blur(4px);
  min-width: 140px;
}
</style>
