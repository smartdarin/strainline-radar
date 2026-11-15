const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const state = { corridor: null, analysis: null, request: null, cases: [], catalog: [], productMetadata: null, temporalHistory: null, temporalObservations: null, robustness: null };
let radarEvidenceInfo = null;
let radarEvidenceLoading = false;
let radarFrameResizeObserver = null;
const today = new Date();
$('#dateTo').value = [today.getFullYear(), String(today.getMonth()+1).padStart(2,'0'), String(today.getDate()).padStart(2,'0')].join('-');

const map = L.map('map', { zoomControl: true }).setView([31.15, 77.2], 10);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
}).addTo(map);
const corridorLayer = L.geoJSON(null, { style: feature => ({ color: feature.properties?.lane==='control_a'?'#348b77':feature.properties?.lane==='control_b'?'#668b68':'#df724c', weight: feature.properties?.lane==='asset'?4:2, dashArray: feature.properties?.lane==='asset'?null:'6 6' }) }).addTo(map);
const laneLayer = L.geoJSON(null, { style: feature => { const support=feature.properties?.geometry_role==='nominal_sample_support'; return { color: ({asset:'#df724c',control_a:'#348b77',control_b:'#668b68'}[feature.properties?.lane] || '#888'), weight: support?1:(feature.properties?.lane==='asset'?4:2), fillOpacity:support ? 0.12 : 0, dashArray: !support&&feature.properties?.lane!=='asset'?'6 6':null }; } }).addTo(map);
const footprintLayer = L.geoJSON(null,{style:{color:'#627fa8',weight:1.5,fillColor:'#afc1dc',fillOpacity:.22,dashArray:'5 4'}}).addTo(map);
const caseLayer = L.layerGroup().addTo(map);

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail || payload));
  return payload;
}
api('/api/health').then(health => {
  $('#dataState').textContent = health.data_mode === 'packaged_real_evidence'
    ? 'PUBLIC API · REAL EVIDENCE PACKAGE'
    : health.real_nisar_loaded ? 'LOCAL API · NISAR READY' : 'LOCAL API · CONNECTED';
  $('#apiState').classList.toggle('api-ready', true);
}).catch(() => { $('#dataState').textContent = 'LOCAL API · OFFLINE'; $('#apiState').classList.add('api-offline'); });

$$('.nav').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
$$('[data-goto]').forEach(button => button.addEventListener('click', () => showView(button.dataset.goto)));
function showView(view) {
  $$('.view').forEach(section => section.classList.toggle('active', section.id === `view-${view}`));
  $$('.nav').forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  const names = { corridor:'CORRIDOR INVESTIGATION', compare:'GROUND CONTEXT', robustness:'ROBUSTNESS LAB', cases:'FIELD CASES', evidence:'DATA & PROVENANCE', radar:'RADAR EVIDENCE' };
  $('#workspaceName').textContent = names[view] || 'STRAINLINE WORKSPACE';
  if (view === 'corridor') setTimeout(() => map.invalidateSize(), 20);
  if (view === 'radar' && !radarEvidenceInfo && !radarEvidenceLoading) loadRadarEvidence();
  else if (view === 'radar' && radarEvidenceInfo) requestAnimationFrame(() => fitRadarFrame(radarEvidenceInfo.preview.width, radarEvidenceInfo.preview.height));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function formatBytes(value) {
  if (!Number.isFinite(Number(value))) return 'unavailable';
  const number = Number(value);
  return `${(number / 1e9).toFixed(3)} GB (${number.toLocaleString()} bytes)`;
}
function formatLongDate(value) {
  const date = String(value || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return 'date unavailable';
  return new Date(`${date}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
}
function fitRadarFrame(width, height) {
  const stage = $('#radarImageStage');
  const frame = $('#radarImageFrame');
  const fit = () => {
    const style = getComputedStyle(stage);
    const availableWidth = stage.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const availableHeight = stage.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
    const scale = Math.min(availableWidth / width, availableHeight / height);
    frame.style.width = `${Math.floor(width * scale)}px`;
    frame.style.height = `${Math.floor(height * scale)}px`;
  };
  fit();
  if (!radarFrameResizeObserver) {
    radarFrameResizeObserver = new ResizeObserver(fit);
    radarFrameResizeObserver.observe(stage);
  }
}
function setRadarGuideStep(step) {
  for (const button of $$('[data-radar-guide]')) {
    const active = button.dataset.radarGuide === step;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  }
}
function setRadarMetadata(info) {
  const referenceDate = String(info.reference_start || 'date unavailable').slice(0, 10);
  const secondaryDate = String(info.secondary_start || 'date unavailable').slice(0, 10);
  $('#instrumentDates').textContent = `${referenceDate} → ${secondaryDate} · L-band ${info.polarization}`;
  $('#radarProductSummary').textContent = `${info.cmr_concept_id} · ${info.maturity.toUpperCase()} · ${formatLongDate(info.reference_start)} → ${formatLongDate(info.secondary_start)} · L-band ${info.polarization}`;
  $('#radarReferenceDate').textContent = formatLongDate(info.reference_start).toUpperCase();
  $('#radarSecondaryDate').textContent = formatLongDate(info.secondary_start).toUpperCase();
  $('#radarPairIdentity').textContent = `${info.maturity.toUpperCase()} · NISAR L-BAND · ${info.polarization}`;
  const root = $('#radarMetadataGrid'); root.replaceChildren();
  const cards = [
    ['Acquisition pair', `Reference ${referenceDate} → secondary ${secondaryDate}. One 12-day interferometric pair.`],
    ['Product status', `${info.maturity} · ${info.polarization} polarization · L-band frequency ${info.frequency}.`],
    ['Orbit geometry', `${info.orbit_pass_direction} pass · ${info.look_direction}-looking · track ${info.track_number} · frame ${info.frame_number} · orbit ${info.absolute_orbit_number ?? 'not available'}.`],
    ['Grid', `EPSG:${info.projection_epsg} · ${info.grid_resolution_m.x} m × ${info.grid_resolution_m.y} m · ${info.shape[0].toLocaleString()} × ${info.shape[1].toLocaleString()} cells.`],
  ];
  for (const [title, description] of cards) {
    const card = document.createElement('article'); card.className = 'panel radar-meta-card';
    const heading = document.createElement('b'); heading.textContent = title;
    const body = document.createElement('span'); body.textContent = description;
    card.append(heading, body); root.append(card);
  }
  $('#radarIds').textContent = `${info.cmr_concept_id} · ${info.granule_id}`;
  $('#radarFilename').textContent = info.provenance.filename;
  $('#radarSize').textContent = `${formatBytes(info.provenance.actual_size_bytes)} · ${info.provenance.size_matches_cmr ? 'matches CMR' : 'CMR size mismatch'}`;
  $('#radarMd5').textContent = `${info.provenance.cmr_md5 || 'unavailable'} · ${info.provenance.cmr_checksum_algorithm || 'CMR checksum'}`;
  $('#radarSha').textContent = info.provenance.sha256_recorded || 'unavailable';
  const integrityOkay = info.provenance.hdf5_readable && info.provenance.granule_identity_matches && info.provenance.size_matches_cmr && info.provenance.sha256_receipt_matches_phase4_record;
  const packageOkay = Boolean(info.provenance.evidence_package_verified);
  $('#radarIntegrityStatus').textContent = packageOkay ? 'PACKAGE SHA-256 VERIFIED · HDF5 LOCAL ONLY'
    : integrityOkay ? 'IDENTITY · SIZE VERIFIED · SHA-256 RECEIPT' : 'INTEGRITY REVIEW REQUIRED';
  $('#radarIntegrityStatus').className = `badge ${integrityOkay || packageOkay ? 'loaded' : 'candidate'}`;
  const list = $('#radarLimitations'); list.replaceChildren();
  for (const limitation of info.limitations) { const item = document.createElement('li'); item.textContent = limitation; list.append(item); }
  const coverage = info.route_coverage;
  $('#coverageValue').textContent = `${coverage.valid_percent.toFixed(2)}%`;
  $('#coverageSummary').textContent = `${coverage.cells_valid.toLocaleString()} of ${coverage.cells_total.toLocaleString()} railway-touched cells pass.`;
  $('#coverageLength').textContent = `${(coverage.route_length_m / 1000).toFixed(2)} km mapped centerline`;
  $('#coverageValid').style.width = `${coverage.valid_percent}%`;
  $('#coverageInvalid').style.width = `${100 - coverage.valid_percent}%`;
  $('#coverageValidLabel').textContent = `Valid ${coverage.cells_valid.toLocaleString()} · ${coverage.valid_percent.toFixed(2)}%`;
  $('#coverageInvalidLabel').textContent = `Invalid ${coverage.cells_invalid.toLocaleString()} · ${(100 - coverage.valid_percent).toFixed(2)}%`;
}
async function loadRadarLayer() {
  if (!radarEvidenceInfo) return;
  const layer = $('#radarLayer').value;
  const packaged = Boolean(radarEvidenceInfo.provenance.evidence_package_verified);
  const loading = $('#radarLoading'); loading.hidden = false; loading.textContent = packaged ? 'Loading packaged real NISAR evidence…' : 'Rendering actual HDF5 cells…';
  try {
    const response = await fetch(`/api/radar-evidence/preview/${encodeURIComponent(layer)}`);
    if (!response.ok) throw new Error(await response.text());
    const blob = await response.blob(); const oldUrl = $('#radarImage').dataset.objectUrl;
    if (oldUrl) URL.revokeObjectURL(oldUrl);
    const url = URL.createObjectURL(blob); const image = $('#radarImage'); image.dataset.objectUrl = url;
    const titles = {phase:'Unwrapped phase · radians',coherence:'Coherence magnitude',components:'Connected-component labels',validity:'Combined validity screen'};
    const explanations = {
      phase:'Unwrapped interferometric phase in radians. Colours show numeric phase only; physical toward/away sign is unresolved, and phase is not ground displacement.',
      coherence:'Interferometric coherence magnitude from 0 to 1. Higher values indicate stronger phase consistency; coherence is observability/quality evidence, not movement.',
      components:'Connected-component display classes identify unwrapped phase regions and fill. Colours are label classes, not movement intensity or magnitude.',
      validity:'Combined screen: finite phase, coherence in range, nonzero component, valid reference and secondary subswaths, and clear anomaly flags. Valid means observable under this screen, not ground movement.'
    };
    $('#radarLayerTitle').textContent = titles[layer];
    $('#radarLayerExplanation').textContent = explanations[layer];
    const low = response.headers.get('X-Value-Min'), high = response.headers.get('X-Value-Max');
    $('#radarLegendText').textContent = layer === 'phase' ? `Displayed range ${low} to ${high} radians · numerical phase, not toward/away` : layer === 'coherence' ? `Displayed range ${low} to ${high} · coherence magnitude, dimensionless` : layer === 'components' ? '0 = no component · green = nonzero component label · magenta = fill; labels are not movement intensity' : 'Green = passes the combined quality screen · dark = does not pass';
    $('#radarPreviewStatus').textContent = packaged
      ? `Actual NISAR ${layer} preview packaged from the source HDF5; display samples every ${infoFactor()} source pixels. Exact railway-touched source cells can be inspected. Arbitrary raster-cell values and full-product operations require the original HDF5 locally.`
      : layer === 'phase'
      ? `Actual HDF5 phase cells, sampled every ${infoFactor()} pixels for display · clipped to the preview 2nd–98th percentile · radians. Color does not encode displacement sign.`
      : `Actual HDF5 ${layer} cells, sampled every ${infoFactor()} pixels for display. Click to inspect a source-grid cell.`;
    const loaded = new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; });
    image.src = url;
    await loaded;
    loading.hidden = true;
  } catch (error) { loading.textContent = `Radar preview unavailable: ${error.message}`; }
}
function infoFactor() { return radarEvidenceInfo?.preview?.sample_factor || 1; }
async function loadRadarEvidence() {
  if (radarEvidenceLoading) return;
  radarEvidenceLoading = true;
  $('#radarLoading').hidden = false;
  try {
    radarEvidenceInfo = await api('/api/radar-evidence');
    const {width, height} = radarEvidenceInfo.preview;
    fitRadarFrame(width, height);
    const overlay = $('#radarOverlay'); overlay.setAttribute('viewBox', `0 0 ${width} ${height}`);
    overlay.setAttribute('preserveAspectRatio', 'none');
    for (const segment of radarEvidenceInfo.route_segments) {
      const line = document.createElementNS('http://www.w3.org/2000/svg','polyline');
      line.setAttribute('points', segment.map(point=>`${point[0]},${point[1]}`).join(' '));
      line.setAttribute('class','radar-route-line'); overlay.append(line);
    }
    setRadarMetadata(radarEvidenceInfo);
    for (const button of $$('[data-radar-guide]')) {
      button.disabled = false;
      button.addEventListener('click', async () => {
        if (!radarEvidenceInfo) return;
        const step = button.dataset.radarGuide;
        const guide = $('#radarGuideHint');
        setRadarGuideStep(step);
        if (step === 'phase') {
          $('#radarLayer').value = 'phase';
          guide.textContent = 'Phase is displayed in radians. Its physical toward/away sign remains unresolved.';
          await loadRadarLayer();
        } else if (step === 'quality') {
          $('#radarLayer').value = 'validity';
          guide.textContent = 'The green cells pass the combined quality screen; this describes radar observability only.';
          await loadRadarLayer();
        } else {
          guide.textContent = 'Click the gold railway line to inspect its nearest real source-grid cell. Click elsewhere to inspect any raster cell.';
        }
        $('#radarImageStage').scrollIntoView({behavior:'smooth',block:'center'});
      });
    }
    await loadRadarLayer();
    $('#radarImageStage').addEventListener('click', async event => {
      const rect = $('#radarImageFrame').getBoundingClientRect();
      const x = Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width));
      const y = Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height));
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) return;
      const col = Math.min(radarEvidenceInfo.shape[1]-1,Math.floor(x*radarEvidenceInfo.shape[1]));
      const row = Math.min(radarEvidenceInfo.shape[0]-1,Math.floor(y*radarEvidenceInfo.shape[0]));
      const routeSelected = Boolean(event.target.closest?.('.radar-route-line'));
      $('#radarSamplePrompt').textContent = routeSelected ? 'Snapping to the mapped railway and reading the source cell…' : 'Reading source cell…';
      try {
        const endpoint = routeSelected ? 'route-location' : 'sample';
        const sample = await api(`/api/radar-evidence/${endpoint}?row=${row}&col=${col}`);
        const sourceX = sample.column / (radarEvidenceInfo.shape[1]-1) * width;
        const sourceY = sample.row / (radarEvidenceInfo.shape[0]-1) * height;
        $('#radarSelection').setAttribute('cx', String(sourceX)); $('#radarSelection').setAttribute('cy', String(sourceY)); $('#radarSelection').style.display='block';
        $('#sampleCell').textContent = `${sample.row}, ${sample.column}`;
        $('#sampleXY').textContent = `${sample.x_m.toFixed(2)} m E · ${sample.y_m.toFixed(2)} m N`;
        $('#sampleLonLat').textContent = `${sample.latitude.toFixed(6)}° N, ${sample.longitude.toFixed(6)}° E`;
        $('#sampleChainage').textContent = sample.distance_along_segment_m === undefined
          ? 'Not on railway overlay'
          : `OSM segment ${sample.route_segment} · ${(sample.distance_along_segment_m/1000).toFixed(3)} km from segment start · ${(sample.distance_to_railway_m).toFixed(1)} m offset`;
        $('#samplePhase').textContent = sample.phase_radians === null ? 'missing' : `${sample.phase_radians.toFixed(6)} rad`;
        $('#sampleCoherence').textContent = sample.coherence === null ? 'missing' : sample.coherence.toFixed(6);
        $('#sampleComponent').textContent = String(sample.connected_component);
        $('#sampleMask').textContent = String(sample.raw_mask);
        $('#sampleValid').textContent = sample.validity_screen ? 'Passes combined validity screen' : 'Fails combined validity screen';
        $('#radarSamplePanel').classList.add('has-selection');
        $('#radarSamplePrompt').textContent = sample.interpretation;
        setRadarGuideStep('cell');
        $('#radarGuideHint').textContent = routeSelected
          ? 'A railway location is selected. The inspector shows values from its nearest real source-grid cell.'
          : 'A real radar-grid cell is selected. Its location and all layer values are synchronized in the inspector.';
      } catch (error) { $('#radarSamplePrompt').textContent = `Cell inspection failed: ${error.message}`; }
    });
    $('#radarLayer').addEventListener('change', () => {
      const layer = $('#radarLayer').value;
      const step = layer === 'phase' ? 'phase' : layer === 'validity' ? 'quality' : null;
      setRadarGuideStep(step);
      if (!step) $('#radarGuideHint').textContent = `${$('#radarLayer').selectedOptions[0].textContent} is displayed. The phase, quality, and cell inspection path remains available above.`;
      loadRadarLayer();
    });
  } catch (error) {
    $('#radarLoading').textContent = `Real NISAR evidence unavailable: ${error.message}`;
    radarEvidenceInfo = null;
  } finally { radarEvidenceLoading = false; }
}
function getLineCoordinates(g) {
  const out = [];
  const walk = item => {
    if (!item) return;
    if (item.type === 'FeatureCollection') item.features.forEach(walk);
    else if (item.type === 'Feature') walk(item.geometry);
    else if (item.type === 'LineString') out.push(...item.coordinates);
    else if (item.type === 'MultiLineString') item.coordinates.forEach(line => out.push(...line));
    else throw new Error('Choose GeoJSON with LineString or MultiLineString geometry.');
  };
  walk(g);
  if (out.length < 2 || out.some(c => !Array.isArray(c) || !Number.isFinite(c[0]) || !Number.isFinite(c[1]) || Math.abs(c[0]) > 180 || Math.abs(c[1]) > 90)) throw new Error('The WGS84 route coordinates are invalid or incomplete.');
  return out;
}
function geojsonFootprint(umm){
  const polygons=umm?.SpatialExtent?.HorizontalSpatialDomain?.Geometry?.GPolygons||[];
  const features=[];
  for(const item of polygons){const points=item?.Boundary?.Points||[];const coords=points.filter(p=>Number.isFinite(Number(p.Longitude))&&Number.isFinite(Number(p.Latitude))).map(p=>[Number(p.Longitude),Number(p.Latitude)]);if(coords.length>=3){if(coords[0][0]!==coords.at(-1)[0]||coords[0][1]!==coords.at(-1)[1])coords.push(coords[0]);features.push({type:'Feature',properties:{source:'NASA CMR UMM'},geometry:{type:'Polygon',coordinates:[coords]}});}}
  return {type:'FeatureCollection',features};
}

function showCorridor(geo, label) {
  getLineCoordinates(geo);
  state.corridor = geo;
  corridorLayer.clearLayers().addData(geo);
  laneLayer.clearLayers();
  const bounds = corridorLayer.getBounds(); if (bounds.isValid()) map.fitBounds(bounds.pad(.12));
  $('#corridorLabel').textContent = label;
  $('#mapStatus').textContent = `${label} · WGS84 corridor · archive candidates still require exact footprint review`;
  $('#analysisStatus').textContent = 'Load compatible lane observations and their provenance separately.';
}

$('#demoVersionBtn').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true; button.textContent = 'Loading real-data demo…';
  try {
    const corridor = await api('/api/demo-corridor');
    showCorridor(corridor, 'Kalka–Shimla railway · included demo');
    $('#corridorName').value = 'Kalka–Shimla Railway';
    $('#catalogCollection').value = 'provisional';
    showView('radar');
    $('#radarSamplePrompt').textContent = 'Demo corridor loaded. Select its railway overlay to inspect a packaged full-resolution source cell.';
    $('#radarLoading').textContent = 'Real NISAR evidence is packaged and ready; the source HDF5 is not needed for this demo.';
  } catch (error) {
    $('#mapStatus').textContent = `Demo corridor unavailable: ${error.message}`;
  } finally {
    button.disabled = false; button.innerHTML = 'Open demo version <span>↗</span>';
  }
});

$('#corridorFile').addEventListener('change', async event => {
  try {
    const file = event.target.files[0]; if (!file) return;
    const geo = JSON.parse(await file.text());
    showCorridor(geo, file.name);
  } catch (error) { $('#mapStatus').textContent = error.message; }
});

$('#searchBtn').addEventListener('click', async event => {
  if (!state.corridor) { $('#catalogResults').innerHTML = '<p class="catalog-error">Load the WGS84 centerline first; a broad default rectangle is not a verified route.</p>'; return; }
  const coords = getLineCoordinates(state.corridor);
  const lons = coords.map(c=>c[0]), lats = coords.map(c=>c[1]), pad = .02;
  const request = { west: Math.max(-180,Math.min(...lons)-pad), east: Math.min(180,Math.max(...lons)+pad), south: Math.max(-90,Math.min(...lats)-pad), north: Math.min(90,Math.max(...lats)+pad), start: $('#dateFrom').value, end: $('#dateTo').value, collection: $('#catalogCollection').value, corridor_geojson: state.corridor };
  const button = event.currentTarget; button.disabled = true; button.textContent = 'Searching NASA CMR…';
  $('#catalogResults').replaceChildren(Object.assign(document.createElement('p'), { className:'catalog-empty', textContent:'Metadata search only. Exact centerline intersection and product QA remain a separate review.' }));
  try {
    const result = await api('/api/catalog', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) }); state.catalog = result.results;
    const box = $('#catalogResults'); box.replaceChildren();
    const status = document.createElement('p');
    if (result.outcome === 'no_products') {
      status.className = 'catalog-empty'; status.textContent = 'No products found for this collection, date range, and search envelope.'; box.append(status); return;
    }
    if (result.outcome === 'products_no_intersection') {
      status.className = 'catalog-empty'; status.textContent = `Products found (${result.result_count}), but none intersect the railway centerline.`;
    } else if (result.outcome === 'footprint_unavailable') {
      status.className = 'catalog-error'; status.textContent = `Products found, but CMR did not provide usable footprint polygons for ${result.footprint_unavailable_count} record(s); exact route coverage is unverified.`;
    } else {
      status.className = 'catalog-empty'; status.textContent = `Found ${result.result_count} products; ${result.intersection_count} exact CMR footprint(s) intersect the railway.`;
    }
    box.append(status);
    for (const item of state.catalog) {
      const row=document.createElement('div'); row.className='granule';
      const name=document.createElement('b'); name.textContent=item.title || item.id || 'NISAR GUNW';
      const overlap=item.footprint_intersection==='intersects'?'exact railway intersection':item.footprint_intersection==='no_intersection'?'no railway intersection':'footprint unavailable';
      const time=document.createElement('small'); time.textContent=`${item.start || 'Date unavailable'} → ${item.end || ''} · ${item.collection_maturity || result.collection_maturity} · ${overlap}`;
      const metadata=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Review CMR metadata, maturity and coverage record';const pre=document.createElement('pre');pre.textContent=JSON.stringify(item.umm,null,2).slice(0,16000);metadata.append(summary,pre);
      const link=document.createElement('a'); link.href=`https://cmr.earthdata.nasa.gov/search/concepts/${encodeURIComponent(item.id)}`; link.target='_blank'; link.rel='noreferrer'; link.textContent='Inspect NASA metadata ↗';
      const check=document.createElement('button');check.className='secondary';check.textContent='Check exact corridor overlap';
      check.addEventListener('click',async()=>{check.disabled=true;check.textContent='Checking…';try{const out=await api('/api/footprint-check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({corridor_geojson:state.corridor,umm:item.umm})});const footprint=geojsonFootprint(item.umm);if(footprint.features.length)footprintLayer.clearLayers().addData(footprint);check.textContent=`${out.status.replaceAll('_',' ')} · ${out.note||out.reason}`;if(out.status==='intersects')$('#mapStatus').textContent=`${item.title||item.id} UMM footprint intersects imported route; radar pixel QA remains unverified.`;}catch(error){check.textContent=`Check unavailable · ${error.message}`;}finally{check.disabled=false;}});
      const dataLink=(item.links||[]).find(l=>l.rel?.includes('/data#')&&l.href?.startsWith('https://'));
      row.append(name,time,metadata,link,check);
      if(dataLink){const download=document.createElement('button');download.className='secondary';download.textContent='Download to local backend';download.addEventListener('click',async()=>{
        const expectedGranuleId=item.umm?.GranuleUR||item.title||'';
        const filename=`${expectedGranuleId.replace(/[^A-Za-z0-9._-]/g,'_')}.h5`.slice(0,180);
        if(!window.confirm(`Download ${filename} to this project's data/raw folder? NISAR granules may be several gigabytes.`))return;
        download.disabled=true;download.textContent='Downloading through backend…';
        try{const receipt=await api('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:dataLink.href,filename,expected_granule_id:expectedGranuleId,cmr_record:item})});download.textContent=`Saved ${receipt.size_bytes} bytes · SHA-256 ${receipt.sha256.slice(0,12)}… · HDF5 identity verified`;
          const inspect=document.createElement('button');inspect.className='secondary';inspect.textContent='Inspect local HDF5';inspect.addEventListener('click',async()=>{
            inspect.disabled=true;inspect.textContent='Inspecting HDF5…';
            try{const metadata=await api('/api/inspect-gunw',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename,polarization:'HH',corridor_geojson:state.corridor})});state.productMetadata=metadata;
              $('#inspectionMetadata').textContent=JSON.stringify(metadata,null,2);$('#inspectionStatus').textContent=`HDF5 structure inspected: ${metadata.granule_id||filename} · ${metadata.phase_shape.join(' × ')} pixels · EPSG:${metadata.projection_epsg}. ${metadata.phase_sign_status}.`;
              if(metadata.product_footprint_geojson){footprintLayer.clearLayers().addData({type:'Feature',geometry:metadata.product_footprint_geojson,properties:{source:'HDF5 product footprint'}});$('#mapStatus').textContent=`HDF5 product footprint: ${metadata.footprint_intersection} imported corridor. Radar pixel QA remains separate.`;}
              $('#productId').textContent=metadata.granule_id||filename;$('#provenanceState').textContent='HDF5 metadata read · maturity requires CMR review';$('#provenanceSummary').textContent=`Reference ${metadata.reference_start||'unknown'} → secondary ${metadata.secondary_start||'unknown'} · ${metadata.orbit_pass_direction||'orbit unknown'} · ${metadata.look_direction||'look unknown'} · ${metadata.center_frequency_hz} Hz.`;showView('evidence');
            }catch(error){$('#inspectionStatus').textContent=`HDF5 inspection unavailable: ${error.message}`;}
            finally{inspect.disabled=false;inspect.textContent='Inspect local HDF5';}
          });row.append(inspect);
        }
        catch(error){download.textContent=`Download unavailable · ${error.message}`;}
        finally{download.disabled=false;}
      });row.append(download);}
      box.append(row);
    }
  } catch (error) { const message=document.createElement('p'); message.className='catalog-error'; message.textContent=`Search failed because of a network/API error: ${error.message}`; $('#catalogResults').replaceChildren(message); }
  finally { button.disabled=false; button.innerHTML='Search NASA L-band archive <span>↗</span>'; }
});

$('#analysisFile').addEventListener('change', async event => {
  const file = event.target.files[0]; if (!file) return;
  try {
    let request = JSON.parse(await file.text());
    if (!request.provenance || !Array.isArray(request.samples) || !request.samples.length) throw new Error('Expected a JSON request containing provenance and lane samples. See README schema.');
    if(request.lane_pixels){
      const match=await api('/api/terrain-match',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lane_pixels:request.lane_pixels,matching_thresholds:request.matching_thresholds,coherence_threshold:request.provenance.min_coherence_screen})});
      request={...request,terrain_matches:match.sections};
      $('#analysisStatus').textContent=`Section-wise terrain matching: ${match.matched_sections}/${match.sections.length} · submitting Three-Lane analysis…`;
    }
    state.request=request;
    const analysisRequest={...request};delete analysisRequest.lane_pixels;
    const result=await api('/api/three-lane',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(analysisRequest)});
    state.analysis=result; state.cases=result.cases || []; state.robustness=null; attachTemporalHistory();
    $('#runRobustness').disabled=false;
    $('#analysisStatus').textContent=`${result.status.replaceAll('_',' ')} · ${result.usable_section_count}/${result.section_count} usable · ${file.name}`;
    $('#resultBadge').textContent=result.status.replaceAll('_',' ').toUpperCase(); $('#resultBadge').className=`badge ${result.status.includes('candidate')?'candidate':'loaded'}`;
    $('#comparisonStatus').textContent=`${result.status.replaceAll('_',' ').toUpperCase()} · ${result.no_call_count} NO-CALL · ${result.ambiguous_count} AMBIGUOUS`;
    $('#comparisonStatus').className='badge loaded';
    $('#dataState').textContent='PROCESSED INPUT · PROVENANCE REQUIRES REVIEW';
    $('#productId').textContent=result.granule_id;
    $('#provenanceState').textContent=Object.keys(result.provenance || {}).length?'Record supplied · not independently authenticated':'Missing';
    $('#provenanceSummary').textContent=JSON.stringify(result.provenance || {});
    const matchChecks=['elevation','slope','aspect','land_cover','radar_observability'].map(k=>result.terrain_matches.length>0&&result.terrain_matches.every(section=>Object.values(section.controls).every(control=>control.checks[k])));
    $('#qualityDetails').textContent=`${result.usable_section_count} usable, ${result.ambiguous_count} ambiguous and ${result.no_call_count} no-call sections. Terrain and radar matching was evaluated at ${result.terrain_matches.length} chainage sections; per-section metrics and limits are in the result record.`;
    $$('.matching-grid input').forEach((input,i)=>input.checked=matchChecks[i]);
    renderComparison(result); renderCases(state.cases); renderCaseMarkers(result);
    runRobustness();
    $$('.export-set button').forEach(b=>b.disabled=false); $('#exportCsv').disabled=false;
    if (result.status==='shared_or_no_material_difference') $('#resultBadge').textContent='SHARED / NO MATERIAL DIFFERENCE';
  } catch (error) { $('#analysisStatus').textContent=error.message; }
});
$('#advancedEvidenceFile').addEventListener('change', async event=>{
  const file=event.target.files[0];if(!file)return;
  try{
    const input=JSON.parse(await file.text());
    if(input.l_band||input.s_band){const r=await api('/api/dual-band',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)});$('#dualBandState').textContent=r.status.replaceAll('_',' ');$('#dualBandText').textContent=r.reason||`Difference: ${fmt(r.difference_mm)} mm · ${r.note}`;}
    if(Array.isArray(input.observations)){const r=await api('/api/temporal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)});$('#temporalState').textContent=r.status.replaceAll('_',' ');$('#temporalText').textContent=r.reason||`${r.count} compatible observations · ${fmt(r.net_change_mm)} mm net change over ${fmt(r.elapsed_days)} days · descriptive rate ${fmt(r.rate_mm_per_year)} mm/year. ${r.note}`;}
    $('#advancedStatus').textContent=`Compatibility checks evaluated from ${file.name}. Supplied summaries are not independently authenticated.`;
  }catch(error){$('#advancedStatus').textContent=error.message;}
});
$('#temporalHistoryFiles').addEventListener('change', async event=>{
  const files=[...event.target.files];if(!files.length)return;
  $('#historyStatus').textContent=`Reading ${files.length} processed observation exports…`;
  try{
    state.temporalObservations=await Promise.all(files.map(async file=>JSON.parse(await file.text())));
    await runTemporalHistory();
  }catch(error){$('#historyStatus').textContent=`Temporal reconstruction unavailable: ${error.message}`;$('#temporalState').textContent='Unavailable';}
});
['temporalCandidate','temporalMaterial'].forEach(id=>$('#'+id).addEventListener('change',()=>{if(state.temporalObservations)runTemporalHistory();}));
async function runTemporalHistory(){
  const observations=state.temporalObservations;if(!observations)return;
  try{
    const history=await api('/api/temporal-processed',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({observations,candidate_threshold_mm:Number($('#temporalCandidate').value),material_change_mm:Number($('#temporalMaterial').value)})});
    state.temporalHistory=history;attachTemporalHistory();$$('[data-temporal-export]').forEach(button=>button.disabled=false);
    $('#temporalState').textContent=history.status.replaceAll('_',' ');
    $('#temporalText').textContent=history.reason||`${history.count} compatible processed observations · ${history.histories.length} chainage histories. Rates are descriptive only.`;
    $('#historyStatus').textContent=history.reason||`${history.count} compatible observations for ${history.corridor_name}. Shared master: ${history.compatibility.reference_start} · phase reference: ${history.compatibility.phase_reference_id} · support: ${history.effective_support_m} m · supplied provenance is completeness-checked, not independently authenticated.`;
    const host=$('#historyResults');host.replaceChildren();
    if(history.histories.length){
      const table=document.createElement('table');table.innerHTML='<thead><tr><th>Chainage</th><th>History</th><th>Usable pairs</th><th>Absolute LOS change</th><th>Relative LOS change</th><th>Relative range</th><th>Gaps</th></tr></thead>';
      const body=document.createElement('tbody');
      for(const item of history.histories){const tr=document.createElement('tr');
        const cells=[`${(item.chainage_m/1000).toFixed(3)} km`,item.status.replaceAll('_',' '),String(item.valid_observations),`${fmt(item.asset_absolute_net_change_mm)} mm`,`${fmt(item.asset_relative_net_change_mm)} mm`,`${fmt(item.asset_relative_range_mm)} mm`,item.missing_observations?.length?`${item.missing_observations.length} missing`:'—'];
        cells.forEach((value,i)=>{const td=document.createElement('td');td.textContent=value;if(i===1)td.className='status';tr.append(td)});body.append(tr);
      }
      table.append(body);host.append(table);
      const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Observation dates and granule IDs';const pre=document.createElement('pre');pre.textContent=JSON.stringify(history.granules,null,2);details.append(summary,pre);host.append(details);
    }else{
      const note=document.createElement('p');note.className='empty';note.textContent=history.reason||'No eligible chainage histories.';host.append(note);
    }
  }catch(error){$('#historyStatus').textContent=`Temporal reconstruction unavailable: ${error.message}`;$('#temporalState').textContent='Unavailable';}
}
$$('[data-temporal-export]').forEach(button=>button.addEventListener('click',async()=>{
  if(!state.temporalHistory)return;
  const kind=button.dataset.temporalExport;button.disabled=true;
  try{
    const response=await fetch(`/api/temporal-export/${kind}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({history:state.temporalHistory})});
    if(!response.ok){const payload=await response.json().catch(()=>({}));throw new Error(payload.detail||'Temporal export failed.');}
    const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`strainline-temporal-history.${kind}`;link.click();URL.revokeObjectURL(url);
  }catch(error){$('#historyStatus').textContent=error.message;}finally{button.disabled=false;}
}));
$('#runRobustness').addEventListener('click', runRobustness);
['robustMinPixels','robustCandidate','robustMaterial','robustDisagreement','robustRadiusFloor'].forEach(id => $('#'+id).addEventListener('change', () => {
  if (state.request) runRobustness();
}));
async function runRobustness() {
  const button=$('#runRobustness');
  if(!state.request) return;
  button.disabled=true; button.textContent='Recalculating…';
  try {
    const result=await api('/api/reference-robustness',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      samples:state.request.samples, terrain_matches:state.request.terrain_matches || [],
      min_valid_pixels:Number($('#robustMinPixels').value),
      candidate_threshold_mm:Number($('#robustCandidate').value),
      material_change_mm:Number($('#robustMaterial').value),
      max_control_disagreement_mm:Number($('#robustDisagreement').value),
      min_sections:state.request.min_sections || 3,
      lane_pixels:state.request.lane_pixels || {},
      matching_thresholds:state.request.matching_thresholds || {},
      coherence_threshold:state.request.provenance?.min_coherence_screen,
      base_radius_m:state.request.provenance?.lane_radius_m,
      radius_floor_fraction:Number($('#robustRadiusFloor').value)
    })});
    state.robustness=result;attachRobustness();
    $('#robustnessBadge').textContent=result.classification.replaceAll('_',' ').toUpperCase();
    $('#robustnessBadge').className='badge '+(result.classification==='consistent'?'loaded':result.classification==='reference_sensitive'?'candidate':'unavailable');
    $('#robustnessTitle').textContent=result.median_signal_spread_mm===null?'Insufficient eligible comparisons':`Median signal spread · ${fmt(result.median_signal_spread_mm)} mm`;
    $('#robustnessMethod').textContent=result.tested_radii_m?.length?`${result.method} Tested radii: ${result.tested_radii_m.map(r=>`${fmt(r)} m`).join(', ')}.`:result.method;
    const list=$('#robustnessScenarios');list.replaceChildren();
    for(const scenario of result.scenarios){
      const card=document.createElement('article');card.className='robustness-scenario';
      const title=document.createElement('b');title.textContent=scenario.configuration.replaceAll('_',' ');
      const value=document.createElement('strong');value.textContent=scenario.median_asset_relative_mm===null?'—':`${fmt(scenario.median_asset_relative_mm)} mm`;
      const detail=document.createElement('span');detail.textContent=`${scenario.status.replaceAll('_',' ')} · ${scenario.usable_sections} usable · ${scenario.rejected_sections} rejected · ${scenario.control_disagreement_sections} control disagreements · ${scenario.candidate_sections} candidate sections`;
      card.append(title,value,detail);list.append(card);
    }
  } catch(error) { $('#robustnessBadge').textContent='ANALYSIS UNAVAILABLE';$('#robustnessMethod').textContent=error.message; }
  finally {button.disabled=!state.request;button.textContent='Recalculate references';}
}
function renderComparison(result) {
  const body=$('#comparisonRows'); body.replaceChildren();
  for (const row of result.sections) {
    const tr=document.createElement('tr');
    const values=[`${(row.chainage_m/1000).toFixed(3)} km`,fmt(row.asset_los_mm),fmt(row.control_a_los_mm),fmt(row.control_b_los_mm),fmt(row.common_motion_mm),fmt(row.asset_relative_mm)];
    values.forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.append(td)});
    tr.tabIndex=0;tr.title='Select this chainage on the corridor map';
    tr.addEventListener('click',()=>focusChainage(row));
    tr.addEventListener('keydown',e=>{if(e.key==='Enter')focusChainage(row)});
    const td=document.createElement('td');td.className='status';const pill=document.createElement('span');pill.className=`status-pill ${row.status}`;pill.textContent=row.status==='no_call'?`No call · ${row.reasons.join(', ')}`:row.status==='ambiguous'?`Ambiguous · ${row.reasons.join(', ')}`:'Usable';td.append(pill);tr.append(td);body.append(tr);
  }
}
function focusChainage(row){if(Number.isFinite(row.latitude)&&Number.isFinite(row.longitude)){showView('corridor');map.setView([row.latitude,row.longitude],Math.max(15,map.getZoom()));L.circleMarker([row.latitude,row.longitude],{radius:8,color:'#b55e3c',fillColor:'#ef8050',fillOpacity:.9}).addTo(map).bindPopup(`Chainage ${(row.chainage_m/1000).toFixed(3)} km · ${row.status}`).openPopup();}else{showView('compare');}}
function renderCases(cases) {
  const list=$('#caseList'); list.replaceChildren(); $('#caseCount').textContent=String(cases.length);
  if (!cases.length) { list.innerHTML='<div class="panel empty-case"><b>No field cases generated</b><p>Every section passed without an asset-relative candidate, ambiguity, or no-call. Continue to review the evidence record.</p></div>'; return; }
  for (const item of cases) {
    const card=document.createElement('article'); card.className='panel case-card'; card.tabIndex=0; card.setAttribute('role','button');
    const top=document.createElement('div');top.className='case-top';top.textContent=`${item.status.toUpperCase()} · ${(item.chainage_m/1000).toFixed(3)} KM`;
    const title=document.createElement('h2');title.textContent=`${item.corridor} · ${(item.chainage_m/1000).toFixed(3)} km`;
    const desc=document.createElement('p');desc.textContent=item.reason?.length?item.reason.join(', ').replaceAll('_',' '):'Asset-relative movement differs from the configured matched-background screen.';
    const vals=document.createElement('div');vals.className='case-values';[['Railway LOS',item.asset_los_mm],['Control A',item.control_a_los_mm],['Control B',item.control_b_los_mm],['Difference',item.asset_relative_mm]].forEach(([label,value])=>{const s=document.createElement('span');s.textContent=`${label}: ${fmt(value)} mm`;vals.append(s)});
    card.append(top,title,desc,vals); card.addEventListener('click',()=>openCase(item)); card.addEventListener('keydown',e=>{if(e.key==='Enter')openCase(item)}); list.append(card);
  }
}
function attachTemporalHistory() {
  if (!state.analysis) return;
  const history=state.temporalHistory;
  if(history){
    const compatible=history.corridor_name===state.analysis.corridor_name && Array.isArray(history.histories);
    const reason=compatible ? (history.reason || 'No compatible temporal history exists for this chainage.')
      : 'The imported temporal history belongs to a different corridor or is not chainage-compatible.';
    const byChainage=new Map(compatible ? history.histories.map(row=>[Number(row.chainage_m).toFixed(3),row]) : []);
    state.analysis.cases=(state.analysis.cases||[]).map(item=>({...item,temporal_history:byChainage.get(Number(item.chainage_m).toFixed(3)) || {status:'unsupported',reason}}));
  }
  state.cases=state.analysis.cases;
  renderCases(state.cases);renderCaseMarkers(state.analysis);
}
function attachRobustness() {
  if(!state.analysis||!state.robustness)return;
  const result=state.robustness;
  state.analysis.cases=(state.analysis.cases||[]).map(item=>{
    const perCase=(result.scenarios||[]).map(scenario=>{
      const section=(scenario.sections||[]).find(row=>Math.abs(Number(row.chainage_m)-Number(item.chainage_m))<0.001);
      return {configuration:scenario.configuration,status:section?'evaluated':'not_evaluated',asset_relative_mm:section?.asset_relative_mm??null};
    });
    return {...item,reference_robustness:{classification:result.classification,median_signal_spread_mm:result.median_signal_spread_mm,material_change_mm:result.material_change_mm,scenarios:perCase,method:result.method,limitations:result.limitations}};
  });
  state.cases=state.analysis.cases;attachTemporalHistory();
}
function openCase(item) {
  const detail=$('#caseDetail'); detail.replaceChildren(); const wrap=document.createElement('div');wrap.className='case-detail';
  const h=document.createElement('h2');h.textContent=`Field evidence case · ${(item.chainage_m/1000).toFixed(3)} km`;
  const p=document.createElement('p');const location=item.latitude!=null&&item.longitude!=null?` · ${Number(item.latitude).toFixed(6)}, ${Number(item.longitude).toFixed(6)}`:'';p.textContent=`${item.status.replaceAll('_',' ')} · Granule ${item.granule_id}${location}. ${item.caveat}`;
  const grid=document.createElement('div');grid.className='case-values';[['Railway LOS',item.asset_los_mm],['Nearby A',item.control_a_los_mm],['Nearby B',item.control_b_los_mm],['Asset-relative',item.asset_relative_mm]].forEach(([label,value])=>{const s=document.createElement('span');s.textContent=`${label}: ${fmt(value)} mm`;grid.append(s)});
  const history=item.temporal_history;const historyTitle=document.createElement('h3');historyTitle.textContent='Observation history';
  const historySummary=document.createElement('p');
  if(history && history.observations){historySummary.textContent=`${history.status.replaceAll('_',' ')} · ${history.valid_observations} usable observations · absolute asset change ${fmt(history.asset_absolute_net_change_mm)} mm · asset-relative change ${fmt(history.asset_relative_net_change_mm)} mm · relative range ${fmt(history.asset_relative_range_mm)} mm.`;}
  else historySummary.textContent=history?.reason||'No compatible multi-observation history is available for this chainage.';
  const historyList=document.createElement('ul');for(const observation of history?.observations||[]){const li=document.createElement('li');li.textContent=`${observation.date} · ${observation.granule_id} · asset ${fmt(observation.asset_los_mm)} mm · background ${fmt(observation.background_los_mm)} mm · relative ${fmt(observation.asset_relative_mm)} mm`;historyList.append(li);}
  for(const missing of history?.missing_observations||[]){const li=document.createElement('li');li.textContent=`${missing.date} · ${missing.granule_id} · no call: ${missing.reason}`;historyList.append(li);}
  const robustness=item.reference_robustness;const robustnessTitle=document.createElement('h3');robustnessTitle.textContent='Reference robustness';
  const robustnessSummary=document.createElement('p');robustnessSummary.textContent=robustness?`${robustness.classification.replaceAll('_',' ')} · portfolio median signal spread ${fmt(robustness.median_signal_spread_mm)} mm. ${robustness.method}`:'No robustness assessment has been attached to this case.';
  const robustnessList=document.createElement('ul');for(const scenario of robustness?.scenarios||[]){const li=document.createElement('li');li.textContent=`${scenario.configuration.replaceAll('_',' ')} · ${scenario.status==='evaluated'?`${fmt(scenario.asset_relative_mm)} mm asset-relative`:'not eligible at this chainage'}`;robustnessList.append(li);}
  const h3=document.createElement('h3');h3.textContent='Proposed field verification';const ul=document.createElement('ul');(item.verification_plan||[]).forEach(plan=>{const li=document.createElement('li');const coords=plan.latitude!=null&&plan.longitude!=null?` · ${Number(plan.latitude).toFixed(6)}, ${Number(plan.longitude).toFixed(6)}`:'';const chainage=plan.chainage_m!=null?` · ${(Number(plan.chainage_m)/1000).toFixed(3)} km`:'';li.textContent=`${plan.location}: ${plan.measure}${chainage}${coords}`;ul.append(li)});
  const contextTitle=document.createElement('h3');contextTitle.textContent='Other documented context';const context=document.createElement('p');context.textContent=item.context?.length?item.context.map(c=>`${c.title||c.type||'Context'} (${c.date||'date unavailable'}): ${c.description||'source record supplied'}`).join(' · '):'No rainfall or incident context was supplied for this chainage.';
  const note=document.createElement('p');note.textContent='These locations are proposed measurements for investigation. They do not diagnose a defect or prescribe repairs.';
  wrap.append(h,p,grid,robustnessTitle,robustnessSummary,robustnessList,historyTitle,historySummary,historyList,contextTitle,context,h3,ul,note); detail.append(wrap); $('#caseDialog').showModal();
}
function renderCaseMarkers(result) {
  caseLayer.clearLayers();
  laneLayer.clearLayers();
  const coords=new Map((result.sections||[]).filter(s=>Number.isFinite(s.longitude)&&Number.isFinite(s.latitude)).map(s=>[s.chainage_m,[s.latitude,s.longitude]]));
  for (const item of state.cases) {const ll=coords.get(item.chainage_m);if(ll)L.circleMarker(ll,{radius:7,color:'#a86e2e',fillColor:'#e3ad56',fillOpacity:.9}).bindPopup(`${(item.chainage_m/1000).toFixed(3)} km · ${item.status}`).addTo(caseLayer);}
  const lineFeatures=(state.request?.lane_geojson?.features)||[];
  if(lineFeatures.length){laneLayer.addData(state.request.lane_geojson);$('#mapStatus').textContent='Three lane centerlines and nominal sampled windows shown. Window polygons are not usable-pixel footprints; GUNW masks and quality screens determine measurement support.';}
}
$$('[data-export]').forEach(button=>button.addEventListener('click',()=>exportFile(button.dataset.export,button)));
$('#exportCsv').addEventListener('click',()=>exportFile('csv',$('#exportCsv')));
async function exportFile(kind,button) {
  if(!state.analysis) return;
  const old=button.textContent;button.disabled=true;button.textContent='Preparing…';
  try {
    const response=await fetch(`/api/export/${kind}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({corridor_name:state.analysis.corridor_name,granule_id:state.analysis.granule_id,provenance:state.analysis.provenance,result:state.analysis,corridor_geojson:state.corridor})});
    if(!response.ok)throw new Error(await response.text());const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=({'report':'strainline-field-cases.pdf','geojson':'strainline-field-cases.geojson','json':'strainline-provenance.json','csv':'strainline-three-lane.csv'})[kind];a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  } catch(error) { alert(`Export failed: ${error.message}`); }
  finally {button.disabled=false;button.textContent=old;}
}
function fmt(value) { return Number.isFinite(value)?Number(value).toFixed(2):'—'; }
function escapeHtml(value) { return value.replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }

$('#caseDialog').addEventListener('click',event=>{if(event.target.id==='caseDialog')$('#caseDialog').close()});
$$('.science summary').forEach(s=>s.addEventListener('click',()=>{}));

// Lead with the local real-data evidence workspace; the other five workspaces remain one click away.
loadRadarEvidence();

