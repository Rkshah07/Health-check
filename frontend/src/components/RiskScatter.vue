<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as d3 from 'd3'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import * as TWEEN from 'three/addons/libs/tween.module.js'

const props = defineProps({ patients: Array, selected: Object, whatIf: Object, xFeature: Object, yFeature: Object, zFeature: Object, tiers: Object, filter: String, showLayers: Boolean, showNetwork: Boolean })
const emit = defineEmits(['pick'])
const container = ref(null)

let scene, camera, renderer, controls;
let nodesGroup = new THREE.Group();
let axesGroup = new THREE.Group();
let layersGroup = new THREE.Group();
let networkGroup = new THREE.Group();
let gridHelper;
let raycaster = new THREE.Raycaster();
let mouse = new THREE.Vector2();
let hoveredNode = null;

// Node data cache to map meshes to patient data
const nodeDataMap = new Map();
let meshMap = new Map(); // patient id -> mesh
let whatIfMesh = null;
let whatIfLine = null;
let haloMesh = null;
let floorTargetMesh = null;
let signalBeamMesh = null;
let gizmoCamera, gizmoScene;

const interactionHintVisible = ref(true);

const colors = {
  low: new THREE.Color(0x2e8b6a),
  moderate: new THREE.Color(0xd9992b),
  high: new THREE.Color(0xc8473f),
  critical: new THREE.Color(0xff1100),
  default: new THREE.Color(0x5b6b78),
  bg: new THREE.Color(0x0a1017),
  grid: 0x1e293b
};

// UI State
const tooltip = ref({ visible: false, x: 0, y: 0, text: '' });
const isAnimating = ref(true);

const SPACE_SIZE = 20; // -10 to 10
const getDomain = (feat) => feat.key === 'risk' ? [0, 1] : [feat.min, feat.max];

// Projection scales
let scX, scY, scZ;

function updateScales() {
  scX = d3.scaleLinear().domain(getDomain(props.xFeature)).range([-SPACE_SIZE/2, SPACE_SIZE/2]);
  scZ = d3.scaleLinear().domain(getDomain(props.yFeature)).range([-SPACE_SIZE/2, SPACE_SIZE/2]); // Y feature -> Z depth
  scY = d3.scaleLinear().domain(getDomain(props.zFeature)).range([-SPACE_SIZE/2, SPACE_SIZE/2]); // Z feature -> Y vertical
}

const getVal = (p, feat) => feat.key === 'risk' ? p.risk : p.features[feat.key];

function getTier(risk) {
  if (risk >= 0.7) return 'critical';
  if (risk >= props.tiers.high) return 'high';
  if (risk >= props.tiers.low) return 'moderate';
  return 'low';
}

function getPosition(p) {
  return new THREE.Vector3(
    scX(getVal(p, props.xFeature)),
    scY(getVal(p, props.zFeature)),
    scZ(getVal(p, props.yFeature))
  );
}

function initThree() {
  const width = container.value.clientWidth;
  const height = container.value.clientHeight;

  scene = new THREE.Scene();
  scene.background = colors.bg;
  scene.fog = new THREE.FogExp2(colors.bg, 0.004); // Reduced fog density so dots remain sharp

  camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
  camera.position.set(0, 40, 80); // Distant overview position

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.value.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.maxDistance = 150;
  controls.minDistance = 5;

  scene.add(nodesGroup);
  scene.add(axesGroup);
  scene.add(layersGroup);
  scene.add(networkGroup);

  // Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
  scene.add(ambientLight);
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(10, 20, 10);
  scene.add(dirLight);

  scene.add(dirLight);

  // Halo for selected patient
  const haloGeo = new THREE.RingGeometry(1.2, 1.6, 32);
  const haloMat = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide, transparent: true, opacity: 0.8 });
  haloMesh = new THREE.Mesh(haloGeo, haloMat);
  haloMesh.rotation.x = -Math.PI / 2; // Flat
  haloMesh.visible = false;
  scene.add(haloMesh);

  // Floor target
  const targetGeo = new THREE.RingGeometry(1.5, 2.0, 32);
  const targetMat = new THREE.MeshBasicMaterial({ color: 0x0ea5e9, side: THREE.DoubleSide, transparent: true, opacity: 0.6 });
  floorTargetMesh = new THREE.Mesh(targetGeo, targetMat);
  floorTargetMesh.rotation.x = -Math.PI / 2;
  floorTargetMesh.position.y = -SPACE_SIZE/2 + 0.1;
  floorTargetMesh.visible = false;
  scene.add(floorTargetMesh);

  // Signal beam
  const beamGeo = new THREE.CylinderGeometry(0.1, 0.1, SPACE_SIZE, 16);
  const beamMat = new THREE.MeshBasicMaterial({ color: 0x0ea5e9, transparent: true, opacity: 0.3 });
  signalBeamMesh = new THREE.Mesh(beamGeo, beamMat);
  signalBeamMesh.visible = false;
  scene.add(signalBeamMesh);

  window.addEventListener('resize', onWindowResize);
  container.value.addEventListener('mousemove', onMouseMove);
  container.value.addEventListener('click', onClick);

  setTimeout(() => { interactionHintVisible.value = false; }, 6000);

  updateData();
  cinematicIntro();
}

function buildAxes() {
  while(axesGroup.children.length > 0){ 
    axesGroup.remove(axesGroup.children[0]); 
  }
  
  // Large floor grid instead of a box
  gridHelper = new THREE.GridHelper(100, 40, 0x1e293b, 0x0f172a);
  gridHelper.position.y = -SPACE_SIZE/2;
  axesGroup.add(gridHelper);

  // We only keep the floor, no wireframe cube.
  axesGroup.position.y = -30; // start low for animation
  new TWEEN.Tween(axesGroup.position).to({ y: 0 }, 2000).easing(TWEEN.Easing.Cubic.Out).start();
}

function buildLayers() {
  while(layersGroup.children.length > 0){ layersGroup.remove(layersGroup.children[0]); }
  if (!props.showLayers) return;

  const thresholds = [
    { name: 'low', yMin: 0, yMax: props.tiers.low },
    { name: 'moderate', yMin: props.tiers.low, yMax: props.tiers.high },
    { name: 'high', yMin: props.tiers.high, yMax: 0.7 },
    { name: 'critical', yMin: 0.7, yMax: 1.0 }
  ];

  thresholds.forEach(t => {
    // Determine Y positions for the plane (using scY for vertical Z-feature)
    // Wait, risk is usually on Y-axis in UI (which is Z feature in props). If Z feature is risk:
    if (props.zFeature.key === 'risk') {
      const yMid = scY((t.yMin + t.yMax) / 2);
      const height = scY(t.yMax) - scY(t.yMin);
      
      const geo = new THREE.PlaneGeometry(SPACE_SIZE, SPACE_SIZE);
      geo.rotateX(-Math.PI / 2); // Make it horizontal
      const mat = new THREE.MeshBasicMaterial({
        color: colors[t.name],
        transparent: true,
        opacity: 0.05,
        side: THREE.DoubleSide,
        depthWrite: false
      });
      const plane = new THREE.Mesh(geo, mat);
      plane.position.y = yMid;
      layersGroup.add(plane);
    }
  });
}

function updateData() {
  updateScales();
  buildAxes();
  buildLayers();

  // Remove existing
  while(nodesGroup.children.length > 0){ 
    nodesGroup.remove(nodesGroup.children[0]); 
  }
  nodeDataMap.clear();
  meshMap.clear();

  props.patients.forEach((p, i) => {
    const customTier = getTier(p.risk);
    const baseSize = customTier === 'critical' ? 0.7 : (customTier === 'high' ? 0.55 : (customTier === 'moderate' ? 0.45 : 0.35));
    const sphereGeo = new THREE.SphereGeometry(baseSize, 32, 32);
    
    const mat = new THREE.MeshPhongMaterial({
      color: colors[customTier] || colors.default,
      emissive: colors[customTier] || colors.default,
      emissiveIntensity: customTier === 'critical' ? 0.9 : 0.6,
      transparent: true,
      opacity: 0 
    });
    const mesh = new THREE.Mesh(sphereGeo, mat);
    const pos = getPosition(p);
    
    // Start position slightly below final for pop-up effect
    mesh.position.set(pos.x, pos.y - 2, pos.z);
    
    nodesGroup.add(mesh);
    nodeDataMap.set(mesh.uuid, p);
    meshMap.set(p.id, mesh);

    // Staggered animation
    setTimeout(() => {
      new TWEEN.Tween(mesh.position).to({ y: pos.y }, 800).easing(TWEEN.Easing.Back.Out).start();
      new TWEEN.Tween(mat).to({ opacity: 0.9 }, 800).start(); // Increased base opacity
    }, 1000 + i * (1000 / props.patients.length));
  });
}

function cinematicIntro() {
  isAnimating.value = true;
  // Dynamic framing above cohort
  new TWEEN.Tween(camera.position)
    .to({ x: 0, y: 18, z: 35 }, 2500)
    .easing(TWEEN.Easing.Cubic.InOut)
    .onComplete(() => { isAnimating.value = false; updateSelection(); })
    .start();
}

function resetView() {
  new TWEEN.Tween(camera.position).to({ x: 0, y: 18, z: 35 }, 1200).easing(TWEEN.Easing.Cubic.InOut).start();
  new TWEEN.Tween(controls.target).to({ x: 0, y: 0, z: 0 }, 1200).easing(TWEEN.Easing.Cubic.InOut).start();
}

function zoomIn() {
  const target = camera.position.clone().lerp(controls.target, 0.3);
  new TWEEN.Tween(camera.position).to({ x: target.x, y: target.y, z: target.z }, 500).easing(TWEEN.Easing.Cubic.Out).start();
}

function zoomOut() {
  const dir = camera.position.clone().sub(controls.target).multiplyScalar(1.4);
  const target = controls.target.clone().add(dir);
  new TWEEN.Tween(camera.position).to({ x: target.x, y: target.y, z: target.z }, 500).easing(TWEEN.Easing.Cubic.Out).start();
}

function onWindowResize() {
  if(!container.value) return;
  camera.aspect = container.value.clientWidth / container.value.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(container.value.clientWidth, container.value.clientHeight);
}

function onMouseMove(event) {
  const rect = container.value.getBoundingClientRect();
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  
  raycaster.setFromCamera(mouse, camera);
  const intersects = raycaster.intersectObjects(nodesGroup.children);
  
  if (intersects.length > 0) {
    const mesh = intersects[0].object;
    if (hoveredNode !== mesh) {
      if (hoveredNode && (!props.selected || meshMap.get(props.selected.id) !== hoveredNode)) {
        new TWEEN.Tween(hoveredNode.scale).to({x:1, y:1, z:1}, 200).start();
      }
      hoveredNode = mesh;
      new TWEEN.Tween(hoveredNode.scale).to({x:1.5, y:1.5, z:1.5}, 200).start();
      document.body.style.cursor = 'pointer';
      
      const p = nodeDataMap.get(mesh.uuid);
      tooltip.value = {
        visible: true,
        x: event.clientX,
        y: event.clientY,
        text: `${p.id}\nRisk: ${Math.round(p.risk * 100)}%`
      };
    }
  } else {
    if (hoveredNode) {
      if (!props.selected || meshMap.get(props.selected.id) !== hoveredNode) {
        new TWEEN.Tween(hoveredNode.scale).to({x:1, y:1, z:1}, 200).start();
      }
      hoveredNode = null;
      document.body.style.cursor = 'default';
      tooltip.value.visible = false;
    }
  }
}

function onClick() {
  if (hoveredNode) {
    const p = nodeDataMap.get(hoveredNode.uuid);
    emit('pick', p);
  }
}

function updateSelection() {
  if (!props.selected) return;
  const selMesh = meshMap.get(props.selected.id);
  if (!selMesh) return;

  // Dim others, highlight selected
  nodesGroup.children.forEach(mesh => {
    const p = nodeDataMap.get(mesh.uuid);
    const isSel = (mesh === selMesh);
    const targetScale = isSel ? 1.8 : 1.0;
    const targetOpacity = isSel ? 1.0 : 0.4; // Increased dimmed opacity from 0.2 to 0.4 so they don't look blurry
    
    new TWEEN.Tween(mesh.scale).to({x: targetScale, y: targetScale, z: targetScale}, 400).start();
    new TWEEN.Tween(mesh.material).to({opacity: targetOpacity}, 400).start();
  });

  // Position halo and target
  haloMesh.position.copy(selMesh.position);
  haloMesh.visible = true;

  floorTargetMesh.position.x = selMesh.position.x;
  floorTargetMesh.position.z = selMesh.position.z;
  floorTargetMesh.visible = true;

  const beamHeight = selMesh.position.y - (-SPACE_SIZE/2);
  signalBeamMesh.scale.y = beamHeight / SPACE_SIZE;
  signalBeamMesh.position.set(selMesh.position.x, selMesh.position.y - beamHeight/2, selMesh.position.z);
  signalBeamMesh.visible = true;

  // Animate camera to focus
  const targetPos = selMesh.position.clone();
  
  // Calculate offset position for camera (slightly above and back)
  const camOffset = new THREE.Vector3(5, 4, 12);
  const newCamPos = targetPos.clone().add(camOffset);
  
  new TWEEN.Tween(controls.target).to({x: targetPos.x, y: targetPos.y, z: targetPos.z}, 1000).easing(TWEEN.Easing.Cubic.InOut).start();
  new TWEEN.Tween(camera.position).to({x: newCamPos.x, y: newCamPos.y, z: newCamPos.z}, 1000).easing(TWEEN.Easing.Cubic.InOut).start();

  buildNetwork(selMesh);
}

function buildNetwork(selMesh) {
  while(networkGroup.children.length > 0){ networkGroup.remove(networkGroup.children[0]); }
  if (!props.showNetwork || !selMesh) return;

  const sourcePos = selMesh.position;
  const distances = [];
  
  nodesGroup.children.forEach(mesh => {
    if (mesh !== selMesh) {
      const d = mesh.position.distanceTo(sourcePos);
      distances.push({ mesh, d });
    }
  });
  
  distances.sort((a, b) => a.d - b.d);
  const nearest = distances.slice(0, 3); // Connect to 3 nearest
  
  const mat = new THREE.LineBasicMaterial({ color: 0x0ea5e9, transparent: true, opacity: 0.4 });
  nearest.forEach(n => {
    const geo = new THREE.BufferGeometry().setFromPoints([sourcePos, n.mesh.position]);
    const line = new THREE.Line(geo, mat);
    networkGroup.add(line);
  });
}

function updateWhatIf() {
  if (!props.whatIf || !props.selected) {
    if (whatIfMesh) whatIfMesh.visible = false;
    if (whatIfLine) whatIfLine.visible = false;
    if (haloMesh) haloMesh.visible = false;
    if (floorTargetMesh) floorTargetMesh.visible = false;
    if (signalBeamMesh) signalBeamMesh.visible = false;
    return;
  }

  const origMesh = meshMap.get(props.selected.id);
  if (!origMesh) return;

  // Create whatif mesh if doesn't exist
  if (!whatIfMesh) {
    const geo = new THREE.SphereGeometry(0.4, 16, 16);
    const mat = new THREE.MeshPhongMaterial({ color: 0xffffff, transparent: true, opacity: 0.9 });
    whatIfMesh = new THREE.Mesh(geo, mat);
    scene.add(whatIfMesh);
    
    const lineMat = new THREE.LineDashedMaterial({ color: 0x0ea5e9, dashSize: 0.5, gapSize: 0.2 });
    const lineGeo = new THREE.BufferGeometry();
    whatIfLine = new THREE.Line(lineGeo, lineMat);
    scene.add(whatIfLine);
  }

  const p = props.selected;
  let vx = props.xFeature.key === 'risk' ? props.whatIf.risk : props.whatIf.features[props.xFeature.key] ?? getVal(p, props.xFeature);
  let vy = props.zFeature.key === 'risk' ? props.whatIf.risk : props.whatIf.features[props.zFeature.key] ?? getVal(p, props.zFeature);
  let vz = props.yFeature.key === 'risk' ? props.whatIf.risk : props.whatIf.features[props.yFeature.key] ?? getVal(p, props.yFeature);

  const targetPos = new THREE.Vector3(scX(vx), scY(vy), scZ(vz));

  whatIfMesh.visible = true;
  whatIfLine.visible = true;
  whatIfMesh.material.color = colors[props.whatIf.tier];

  // Animate node
  if (!whatIfMesh.position.equals(targetPos)) {
    // If just created, start at original
    if(whatIfMesh.position.length() === 0) whatIfMesh.position.copy(origMesh.position);

    new TWEEN.Tween(whatIfMesh.position).to({x: targetPos.x, y: targetPos.y, z: targetPos.z}, 800).easing(TWEEN.Easing.Quadratic.Out).onUpdate(() => {
      whatIfLine.geometry.setFromPoints([origMesh.position, whatIfMesh.position]);
      whatIfLine.computeLineDistances();
    }).start();
  } else {
    whatIfLine.geometry.setFromPoints([origMesh.position, whatIfMesh.position]);
    whatIfLine.computeLineDistances();
  }
}

function animate(time) {
  requestAnimationFrame(animate);
  TWEEN.update(time);
  controls.update();

  if (haloMesh.visible) {
    haloMesh.rotation.z -= 0.02; // spin
    floorTargetMesh.rotation.z += 0.02;
    const s = 1 + Math.sin(time * 0.005) * 0.1;
    haloMesh.scale.set(s, s, s);
  }

  // Update Gizmo Overlay manually
  const gizmoElement = document.getElementById('gizmo-cube');
  if (gizmoElement) {
    // Extract rotation from camera relative to scene
    const x = Math.round(camera.rotation.x * (180 / Math.PI));
    const y = Math.round(camera.rotation.y * (180 / Math.PI));
    const z = Math.round(camera.rotation.z * (180 / Math.PI));
    gizmoElement.style.transform = `rotateX(${x}deg) rotateY(${y}deg) rotateZ(${z}deg)`;
  }

  renderer.render(scene, camera);
}

onMounted(() => {
  initThree();
  animate();
});

watch(() => [props.patients, props.xFeature, props.yFeature, props.zFeature], () => {
  // Axis changed, re-map data smoothly
  updateScales();
  buildLayers();
  
  props.patients.forEach(p => {
    const mesh = meshMap.get(p.id);
    if(mesh) {
      const pos = getPosition(p);
      new TWEEN.Tween(mesh.position).to({x: pos.x, y: pos.y, z: pos.z}, 1000).easing(TWEEN.Easing.Cubic.InOut).start();
    }
  });
  updateWhatIf();
  if (props.selected) buildNetwork(meshMap.get(props.selected.id));
}, { deep: true });

watch(() => props.filter, (newFilter) => {
  let isSelectedStillVisible = false;
  nodesGroup.children.forEach(mesh => {
    const p = nodeDataMap.get(mesh.uuid);
    const visible = newFilter === 'all' || p.tier === newFilter;
    if (visible && props.selected && props.selected.id === p.id) {
      isSelectedStillVisible = true;
    }
    const isSel = (props.selected && p.id === props.selected.id);
    const targetOpacity = visible ? (isSel ? 1.0 : (props.selected ? 0.4 : 0.9)) : 0.0;
    // Animate visibility
    new TWEEN.Tween(mesh.material).to({opacity: targetOpacity}, 400).start();
  });
  
  if (props.selected && !isSelectedStillVisible) {
    emit('pick', null);
  }
});

watch(() => props.showLayers, buildLayers);
watch(() => props.showNetwork, () => {
  if (props.selected) {
    buildNetwork(meshMap.get(props.selected.id));
  } else {
    while(networkGroup.children.length > 0){ networkGroup.remove(networkGroup.children[0]); }
  }
});

watch(() => props.selected, updateSelection);
watch(() => props.whatIf, updateWhatIf, { deep: true });

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize);
  container.value.removeEventListener('mousemove', onMouseMove);
  container.value.removeEventListener('click', onClick);
  renderer.dispose();
});

</script>

<template>
  <div class="canvas-container" ref="container">
    <div v-if="tooltip.visible" class="tooltip" :style="{ left: tooltip.x + 15 + 'px', top: tooltip.y + 15 + 'px' }">
      {{ tooltip.text }}
    </div>
    
    <div v-if="interactionHintVisible" class="interaction-hint">
      Drag to rotate • Scroll to zoom • Click a patient
    </div>

    <div class="hud-overlay top-left">
      <div class="hud-title">CLINICAL RISK LANDSCAPE</div>
    </div>
    
    <div class="hud-overlay top-right">
      <div>LIVE COHORT: {{ patients.length }} PATIENTS</div>
      <div class="status-indicator"><span class="dot"></span> MODEL ONLINE</div>
    </div>
    
    <div class="hud-overlay bottom-left axis-hud">
      <div><span class="x-label">X</span> {{ xFeature.label.toUpperCase() }}</div>
      <div><span class="y-label">Y</span> {{ zFeature.label.toUpperCase() }}</div>
      <div><span class="z-label">Z</span> {{ yFeature.label.toUpperCase() }}</div>
    </div>
    
    <div class="gizmo-container">
      <div class="gizmo-cube" id="gizmo-cube">
        <div class="face front">Z</div>
        <div class="face back"></div>
        <div class="face right">X</div>
        <div class="face left"></div>
        <div class="face top">Y</div>
        <div class="face bottom"></div>
      </div>
    </div>
    
    <div class="hud-controls">
      <button @click="zoomIn" title="Zoom In">+</button>
      <button @click="zoomOut" title="Zoom Out">−</button>
      <button @click="resetView">Reset View</button>
    </div>
  </div>
</template>

<style scoped>
.canvas-container { 
  position: relative; 
  width: 100%; 
  height: 600px; 
  overflow: hidden; 
  border-radius: 12px;
  background: #0a1017;
  border: 1px solid #1e293b;
  box-shadow: inset 0 0 40px rgba(0,0,0,0.5);
}
.tooltip {
  position: fixed;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid #0ea5e9;
  color: #fff;
  padding: 8px 12px;
  border-radius: 4px;
  pointer-events: none;
  font-family: monospace;
  font-size: 13px;
  white-space: pre-line;
  z-index: 100;
  backdrop-filter: blur(4px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.hud-overlay {
  position: absolute;
  pointer-events: none;
  color: #0ea5e9;
  font-family: monospace;
  font-size: 12px;
  letter-spacing: 1px;
}
.top-left { top: 16px; left: 16px; }
.top-right { top: 16px; right: 16px; text-align: right; }
.bottom-left { bottom: 16px; left: 16px; }
.hud-title { font-size: 14px; font-weight: 600; color: #f8fafc; letter-spacing: 2px; }
.axis-hud div { margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }
.axis-hud span { display: inline-block; width: 18px; height: 18px; text-align: center; line-height: 18px; border-radius: 4px; font-weight: bold; font-size: 10px; color: #0a1017; }
.x-label { background: #ef4444; }
.y-label { background: #22c55e; }
.z-label { background: #3b82f6; }
.status-indicator { margin-top: 6px; display: flex; align-items: center; gap: 6px; justify-content: flex-end; }
.dot { width: 6px; height: 6px; background: #10b981; border-radius: 50%; box-shadow: 0 0 6px #10b981; animation: pulse 2s infinite; }
.hud-controls {
  position: absolute;
  bottom: 16px;
  right: 16px;
}
.hud-controls button {
  background: rgba(15, 23, 42, 0.7);
  color: #0ea5e9;
  border: 1px solid #0ea5e9;
  padding: 6px 12px;
  font-family: monospace;
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
}
.hud-controls button:hover {
  background: rgba(14, 165, 233, 0.2);
  box-shadow: 0 0 10px rgba(14, 165, 233, 0.4);
}
@keyframes pulse {
  0% { opacity: 0.5; }
  50% { opacity: 1; }
  100% { opacity: 0.5; }
}

.interaction-hint {
  position: absolute; top: 80px; left: 50%; transform: translateX(-50%);
  background: rgba(15,23,42,0.8); color: #cbd5e1; padding: 8px 16px; border-radius: 20px;
  font-size: 12px; pointer-events: none; border: 1px solid rgba(255,255,255,0.1);
  animation: fadeout 6s forwards;
}
@keyframes fadeout { 0% { opacity: 1; } 80% { opacity: 1; } 100% { opacity: 0; } }

.gizmo-container {
  position: absolute; bottom: 80px; left: 24px; width: 40px; height: 40px;
  perspective: 200px; pointer-events: none;
}
.gizmo-cube {
  width: 100%; height: 100%; position: absolute; transform-style: preserve-3d;
  transition: transform 0.1s;
}
.gizmo-cube .face {
  position: absolute; width: 40px; height: 40px;
  background: rgba(14, 165, 233, 0.2); border: 1px solid #0ea5e9;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: bold; color: #0ea5e9;
}
.gizmo-cube .front  { transform: rotateY(  0deg) translateZ(20px); background: rgba(59, 130, 246, 0.3); } /* Z */
.gizmo-cube .right  { transform: rotateY( 90deg) translateZ(20px); background: rgba(239, 68, 68, 0.3); } /* X */
.gizmo-cube .back   { transform: rotateY(180deg) translateZ(20px); }
.gizmo-cube .left   { transform: rotateY(-90deg) translateZ(20px); }
.gizmo-cube .top    { transform: rotateX( 90deg) translateZ(20px); background: rgba(34, 197, 94, 0.3); } /* Y */
.gizmo-cube .bottom { transform: rotateX(-90deg) translateZ(20px); }
</style>
