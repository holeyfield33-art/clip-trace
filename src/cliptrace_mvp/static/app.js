const $ = (s) => document.querySelector(s);
let exported = null;
function message(title, value, isError = false) {
  $('#results-card').hidden = false;
  $('#result-title').textContent = title;
  $('#result-json').textContent = JSON.stringify(value, null, 2);
  const summary = $('#result-summary');
  summary.textContent = '';
  const box = document.createElement('div');
  box.className = 'summary' + (isError ? ' bad' : '');
  if (isError) box.textContent = value.detail || String(value);
  else if (value.receipt) {
    const claims = value.receipt.payload.claims;
    box.textContent = `Candidate ${value.candidate_id}: C1 ${claims.C1_exact_asset.state}; C2 ${claims.C2_signed_lineage.state}; C3 ${claims.C3_visual_derivation.state}; C4 ${claims.C4_audio_derivation.state}; C7 ${claims.C7_authorization.state}. ${value.receipt.payload.review_leads.length} experimental leads for review.`;
  } else if (value.asset_id) box.textContent = `Registered ${value.asset_id}. Exact conflict count: ${value.exact_conflicts.length}. Feature status: ${value.fingerprint_status}.`;
  else if (value.payload) box.textContent = `${value.payload.document_type} signed. The statement is an operator assertion.`;
  else box.textContent = 'Recorded.';
  summary.append(box);
  exported = isError ? null : (value.receipt || value.manifest || value);
  $('#download-json').hidden = !exported;
  $('#results-card').scrollIntoView({behavior:'smooth', block:'start'});
}
async function send(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw body;
  return body;
}
async function refresh() {
  const [assets, candidates] = await Promise.all([send('/api/assets'), send('/api/candidates')]);
  $('#asset-count').textContent = assets.length;
  $('#candidate-count').textContent = candidates.length;
  const assetList = $('#assets-list'); assetList.textContent = '';
  for (const a of assets) {
    const row = document.createElement('div'); row.className = 'row';
    const name = document.createElement('strong'); name.textContent = a.filename;
    const id = document.createElement('code'); id.textContent = a.asset_id;
    const detail = document.createElement('small'); detail.textContent = `${a.sha256.slice(0, 18)}… · ${a.fingerprint_status}`;
    row.append(name,id,detail); assetList.append(row);
  }
  if (!assets.length) assetList.textContent = 'No sources registered yet.';
  document.querySelectorAll('.asset-select').forEach(select => {
    const selected = select.value; select.textContent = '';
    for (const a of assets) select.add(new Option(`${a.filename} · ${a.asset_id.slice(-8)}`, a.asset_id));
    if (assets.some(a => a.asset_id === selected)) select.value = selected;
  });
  const candidateList = $('#candidates-list'); candidateList.textContent = '';
  for (const c of candidates) {
    const row = document.createElement('div'); row.className = 'row';
    const name = document.createElement('strong'); name.textContent = c.filename;
    const link = document.createElement('a'); link.href = `/api/candidates/${c.id}/receipt`; link.textContent = c.id;
    const detail = document.createElement('small'); detail.textContent = c.sha256.slice(0, 18) + '…';
    row.append(name, link, detail); candidateList.append(row);
  }
  if (!candidates.length) candidateList.textContent = 'No candidates checked yet.';
}
function upload(formId, url, title) {
  const form = $(formId);
  form.addEventListener('submit', async event => {
    event.preventDefault(); const button = form.querySelector('button'); button.disabled = true;
    try {
      const data = new FormData(form);
      for (const check of form.querySelectorAll('input[type=checkbox]')) data.set(check.name, check.checked ? 'true' : 'false');
      const value = await send(url, {method:'POST',body:data}); message(title,value); await refresh();
    } catch (error) { message('Could not complete request',error,true); }
    finally {button.disabled = false;}
  });
}
function jsonForm(formId, url, title, transform) {
  const form = $(formId);
  form.addEventListener('submit', async event => {
    event.preventDefault(); const button = form.querySelector('button'); button.disabled = true;
    try {
      const raw = Object.fromEntries(new FormData(form).entries());
      const value = await send(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(transform(raw))});
      message(title,value); await refresh();
    } catch (error) { message('Could not complete request',error,true); }
    finally {button.disabled = false;}
  });
}
function intervals(text) { return text.trim() ? JSON.parse(text) : []; }
upload('#register-form','/api/assets','Origin registered');
upload('#verify-form','/api/candidates','Candidate checked');
jsonForm('#review-form','/api/reviews','Review signed',raw => ({...raw,source_intervals_s:intervals(raw.source_intervals_s)}));
jsonForm('#auth-form','/api/authorizations','Authorization signed',raw => ({...raw,valid_from:new Date(raw.valid_from).toISOString(),valid_until:new Date(raw.valid_until).toISOString()}));
jsonForm('#derivative-form','/api/derivatives','Lineage signed',raw => ({...raw,source_intervals_s:intervals(raw.source_intervals_s),declared_transformations:raw.declared_transformations.split(',').map(x=>x.trim()).filter(Boolean),authorization_id:raw.authorization_id||null}));
$('#download-json').addEventListener('click', () => {
  if (!exported) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(exported,null,2)],{type:'application/json'}));
  const a = document.createElement('a'); a.href=url; a.download='cliptrace-signed-statement.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
});
refresh().catch(error=>message('Could not load workspace',error,true));
