// Travel Seasons PoC2 — admin panel (vanilla JS)

const API = ''; // same origin
const root = document.getElementById('root');
const tabs = document.querySelectorAll('.tabs a');
const healthPill = document.getElementById('health-pill');

// ---------- helpers ----------
async function api(path, opts = {}) {
  const r = await fetch(API + path, opts);
  if (!r.ok) {
    const txt = await r.text().catch(() => '');
    throw new Error(`${r.status} ${r.statusText} :: ${txt}`);
  }
  if (r.status === 204) return null;
  return r.json();
}

function tpl(id) {
  return document.getElementById(id).content.cloneNode(true);
}

function setActiveTab(name) {
  tabs.forEach(a => a.classList.toggle('active', a.dataset.tab === name));
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function fmtDate(s) {
  if (!s) return '';
  try { return new Date(s).toLocaleDateString(); } catch { return s; }
}

// ---------- router ----------
async function route() {
  const hash = location.hash || '#trips';
  if (hash === '#users') { setActiveTab('users'); await renderUsers(); return; }
  if (hash === '#trips') { setActiveTab('trips'); await renderTrips(); return; }
  const m = hash.match(/^#trip\/(.+)$/);
  if (m) { setActiveTab('trips'); await renderTripDetail(m[1]); return; }
  location.hash = '#trips';
}
window.addEventListener('hashchange', route);

// ---------- health pill ----------
async function refreshHealth() {
  try {
    const h = await api('/health');
    healthPill.textContent = `${h.mode} · ${h.model} · t=${h.threshold}`;
    healthPill.classList.add('ok');
    healthPill.classList.remove('err');
  } catch (e) {
    healthPill.textContent = 'backend down';
    healthPill.classList.add('err');
    healthPill.classList.remove('ok');
  }
}

// ---------- users ----------
async function renderUsers() {
  root.innerHTML = '';
  root.appendChild(tpl('tpl-users'));
  const grid = document.getElementById('users-grid');
  const form = document.getElementById('enroll-form');

  // Show selected filename
  const fileInput = form.querySelector('input[type=file]');
  const fileLabel = form.querySelector('.file-input span');
  fileInput.addEventListener('change', () => {
    fileLabel.textContent = fileInput.files[0]?.name || 'Choose selfie…';
  });

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = form.querySelector('button');
    btn.disabled = true;
    btn.textContent = 'Enrolling…';
    try {
      const fd = new FormData(form);
      await api('/enrollments', { method: 'POST', body: fd });
      form.reset();
      fileLabel.textContent = 'Choose selfie…';
      await loadUsersGrid(grid);
    } catch (err) {
      alert('Enroll failed: ' + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Enroll';
    }
  });

  await loadUsersGrid(grid);
}

async function loadUsersGrid(grid) {
  const users = await api('/users');
  if (!users.length) {
    grid.innerHTML = '<div class="empty">No users enrolled yet.</div>';
    return;
  }
  grid.innerHTML = users.map(u => `
    <div class="user-card">
      ${u.selfie_url ? `<img src="${u.selfie_url}" alt="${escapeHtml(u.name)}">` : '<div style="aspect-ratio:1;background:var(--muted-bg);"></div>'}
      <div class="user-card-body">
        <strong>${escapeHtml(u.name)}</strong>
        <span class="muted small">${escapeHtml(u.email || '')}</span>
        <span class="uid">${u.id.slice(0, 8)}…</span>
      </div>
      <div class="actions">
        <button data-uid="${u.id}" data-name="${escapeHtml(u.name)}">Delete</button>
      </div>
    </div>
  `).join('');
  grid.querySelectorAll('button[data-uid]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm(`Delete ${btn.dataset.name}?`)) return;
      await api(`/users/${btn.dataset.uid}`, { method: 'DELETE' });
      await loadUsersGrid(grid);
    });
  });
}

// ---------- trips ----------
async function renderTrips() {
  root.innerHTML = '';
  root.appendChild(tpl('tpl-trips'));
  const list = document.getElementById('trips-list');
  const form = document.getElementById('trip-form');

  // Load users for membership picker
  const users = await api('/users');

  // Add a multi-select for members below the form
  const membersDiv = document.createElement('div');
  membersDiv.className = 'card';
  membersDiv.style.marginBottom = '24px';
  membersDiv.innerHTML = `
    <div class="muted small" style="margin-bottom:8px">Members (optional, for reference only — face matching works regardless):</div>
    <div id="member-pickers" style="display:flex;flex-wrap:wrap;gap:8px;">
      ${users.map(u => `
        <label style="display:flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid var(--border);border-radius:8px;background:white;cursor:pointer;">
          <input type="checkbox" value="${u.id}" />
          <span>${escapeHtml(u.name)}</span>
        </label>`).join('')}
    </div>
  `;
  form.parentNode.insertBefore(membersDiv, form.nextSibling);

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const member_user_ids = Array.from(membersDiv.querySelectorAll('input[type=checkbox]:checked')).map(c => c.value);
    const body = {
      name: fd.get('name'),
      start_date: fd.get('start_date') || null,
      end_date: fd.get('end_date') || null,
      member_user_ids,
    };
    await api('/trips', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    form.reset();
    membersDiv.querySelectorAll('input[type=checkbox]').forEach(c => c.checked = false);
    await loadTripList(list);
  });

  await loadTripList(list);
}

async function loadTripList(list) {
  const trips = await api('/trips');
  if (!trips.length) {
    list.innerHTML = '<div class="empty">No trips yet. Create one above.</div>';
    return;
  }
  list.innerHTML = trips.map(t => `
    <a class="trip-row" href="#trip/${t.id}">
      <div class="name">${escapeHtml(t.name)}</div>
      <span class="muted">${t.photo_count} photos</span>
      <span class="muted">${t.members.length} members</span>
      <span class="muted">${fmtDate(t.start_date)} – ${fmtDate(t.end_date)}</span>
    </a>
  `).join('');
}

// ---------- trip detail ----------
let tripDetailState = { tripId: null, polling: null };

async function renderTripDetail(tripId) {
  root.innerHTML = '';
  root.appendChild(tpl('tpl-trip-detail'));
  tripDetailState.tripId = tripId;
  if (tripDetailState.polling) clearInterval(tripDetailState.polling);

  const trips = await api('/trips');
  const trip = trips.find(t => t.id === tripId);
  if (!trip) { location.hash = '#trips'; return; }
  document.getElementById('td-name').textContent = trip.name;
  document.getElementById('td-dates').textContent = `${fmtDate(trip.start_date)} – ${fmtDate(trip.end_date)}`;
  document.getElementById('td-members').textContent = `Members: ${trip.members.map(m => m.name).join(', ') || '—'}`;

  const users = await api('/users');
  const meSelect = document.getElementById('me-user');
  meSelect.innerHTML = users.map(u => `<option value="${u.id}">${escapeHtml(u.name)}</option>`).join('');

  const filterSel = document.getElementById('filter-select');
  filterSel.addEventListener('change', () => {
    meSelect.hidden = filterSel.value !== 'me';
    loadPhotos();
  });
  meSelect.addEventListener('change', loadPhotos);

  // Upload zone
  const zone = document.getElementById('upload-zone');
  const input = document.getElementById('upload-input');
  zone.addEventListener('click', () => input.click());
  ['dragenter', 'dragover'].forEach(ev => zone.addEventListener(ev, e => {
    e.preventDefault(); zone.classList.add('dragging');
  }));
  ['dragleave', 'drop'].forEach(ev => zone.addEventListener(ev, e => {
    e.preventDefault(); zone.classList.remove('dragging');
  }));
  zone.addEventListener('drop', e => uploadFiles(e.dataTransfer.files));
  input.addEventListener('change', () => uploadFiles(input.files));

  await loadPhotos();
  startPolling();
}

async function uploadFiles(fileList) {
  const files = Array.from(fileList).filter(f => f.type.startsWith('image/'));
  if (!files.length) return;
  const tripId = tripDetailState.tripId;

  const chunkSize = 10;
  for (let i = 0; i < files.length; i += chunkSize) {
    const chunk = files.slice(i, i + chunkSize);
    const fd = new FormData();
    chunk.forEach(f => fd.append('files', f));
    await api(`/trips/${tripId}/photos`, { method: 'POST', body: fd });
  }
  await loadPhotos();
  startPolling();
}

function startPolling() {
  if (tripDetailState.polling) clearInterval(tripDetailState.polling);
  tripDetailState.polling = setInterval(async () => {
    if (!tripDetailState.tripId) return;
    try {
      const status = await api(`/trips/${tripDetailState.tripId}/photos/status`);
      const progressDiv = document.getElementById('progress');
      const fill = document.getElementById('progress-fill');
      const text = document.getElementById('progress-text');
      const remaining = status.pending + status.processing;
      if (status.total > 0 && remaining > 0) {
        progressDiv.hidden = false;
        fill.style.width = status.percent + '%';
        text.textContent = `${status.done}/${status.total} processed${status.failed ? ` · ${status.failed} failed` : ''}`;
      } else {
        progressDiv.hidden = true;
        clearInterval(tripDetailState.polling);
        tripDetailState.polling = null;
        await loadPhotos();
      }
    } catch (e) { /* swallow */ }
  }, 2000);
}

async function loadPhotos() {
  const tripId = tripDetailState.tripId;
  if (!tripId) return;
  const filter = document.getElementById('filter-select').value;
  let url = `/trips/${tripId}/photos?filter=${filter}`;
  const opts = {};
  if (filter === 'me') {
    const uid = document.getElementById('me-user').value;
    if (!uid) return;
    opts.headers = { 'X-User-Id': uid };
  }
  const photos = await api(url, opts);
  const grid = document.getElementById('photos-grid');
  document.getElementById('photo-count').textContent = `${photos.length} photo${photos.length !== 1 ? 's' : ''}`;

  if (!photos.length) {
    grid.innerHTML = '<div class="empty">No photos in this view yet.</div>';
    return;
  }
  grid.innerHTML = photos.map(p => `
    <div class="photo-cell" data-photo='${escapeHtml(JSON.stringify(p))}'>
      <span class="photo-status ${p.status}">${p.status}</span>
      <img src="${p.url}" loading="lazy" alt="">
      <div class="photo-tags">
        ${p.faces.map(f => `<span class="tag-chip ${f.user_id ? '' : 'unknown'}">
          ${f.user_id ? escapeHtml(f.name) : '?'}${f.confidence != null ? ` · ${(f.confidence * 100).toFixed(0)}%` : ''}
        </span>`).join('')}
      </div>
    </div>
  `).join('');

  grid.querySelectorAll('.photo-cell').forEach(cell => {
    cell.addEventListener('click', () => openPhotoModal(JSON.parse(cell.dataset.photo)));
  });
}

// ---------- modal ----------
const modal = document.getElementById('modal');
const modalBody = document.getElementById('modal-body');
document.getElementById('modal-close').addEventListener('click', () => modal.hidden = true);
modal.addEventListener('click', e => { if (e.target === modal) modal.hidden = true; });

async function openPhotoModal(photo) {
  modal.hidden = false;
  modalBody.innerHTML = `<div>Loading…</div>`;
  const users = await api('/users');
  renderModalBody(photo, users);
}

function renderModalBody(photo, users) {
  modalBody.innerHTML = `
    <h2 style="margin:0">Photo · ${photo.status}</h2>
    <div class="muted small">${photo.id}</div>
    <div class="modal-img-wrap">
      <img src="${photo.url}" alt="">
    </div>
    <h3 style="margin:0 0 8px">Detected faces</h3>
    <div class="modal-faces">
      ${photo.faces.length === 0 ? '<div class="muted">No faces detected.</div>' : ''}
      ${photo.faces.map(f => `
        <div class="face-row">
          <span class="name">${f.user_id ? escapeHtml(f.name) : 'Unmatched face'}</span>
          <span class="conf">${f.confidence != null ? (f.confidence * 100).toFixed(0) + '%' : '—'} · ${f.source}</span>
          <button class="remove" data-face-id="${f.id}">Remove</button>
        </div>
      `).join('')}
    </div>
    <div class="add-tag-row">
      <select id="add-user-select">
        ${users.map(u => `<option value="${u.id}">${escapeHtml(u.name)}</option>`).join('')}
      </select>
      <button id="add-tag-btn">Add tag</button>
    </div>
  `;
  modalBody.querySelectorAll('button[data-face-id]').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const updated = await api(`/photos/${photo.id}/faces`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ remove_face_ids: [btn.dataset.faceId] }),
      });
      renderModalBody(updated, users);
      await loadPhotos();
    });
  });
  modalBody.querySelector('#add-tag-btn').addEventListener('click', async () => {
    const uid = modalBody.querySelector('#add-user-select').value;
    const updated = await api(`/photos/${photo.id}/faces`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ add: [{ user_id: uid }] }),
    });
    renderModalBody(updated, users);
    await loadPhotos();
  });
}

// ---------- boot ----------
refreshHealth();
route();
setInterval(refreshHealth, 30000);
