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

function shortName(s) {
  if (!s) return '';
  const parts = String(s).trim().split(/\s+/);
  return parts[0].slice(0, 12);
}

// /users is cheap and users can be enrolled out-of-band via Flutter; always
// fetch fresh so the manual-tag dropdown reflects the current set.
async function getUsers() {
  return await api('/users');
}
function invalidateUsersCache() { /* no-op — kept for callers */ }

// Parse FastAPI's {"detail": "..."} out of api() throws.
function parseApiError(e) {
  const idx = (e?.message || '').indexOf('::');
  if (idx < 0) return e?.message || String(e);
  const rest = e.message.slice(idx + 2).trim();
  try { return JSON.parse(rest).detail || e.message; } catch { return e.message; }
}

// Toast helper — vanilla, brief.
function showToast(msg, kind = 'ok') {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = `toast ${kind} visible`;
  clearTimeout(t._hideTimer);
  t._hideTimer = setTimeout(() => t.classList.remove('visible'), 3000);
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
  if (hash === '#videos') { setActiveTab('videos'); await renderVideos(); return; }
  const m = hash.match(/^#trip\/(.+)$/);
  if (m) { setActiveTab('trips'); await renderTripDetail(m[1]); return; }
  const md = hash.match(/^#trip-day\/(.+)$/);
  if (md) { setActiveTab('trips'); await renderTripDay(md[1]); return; }
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
  document.getElementById('td-crumb').textContent = trip.name;
  document.getElementById('td-dates').textContent = `${fmtDate(trip.start_date)} – ${fmtDate(trip.end_date)}`;
  document.getElementById('td-members').textContent = `Members: ${trip.members.map(m => m.name).join(', ') || '—'}`;

  // Toggle "Add a day" form
  const dayFormEl = document.getElementById('day-form');
  document.getElementById('td-add-day-toggle').addEventListener('click', () => {
    dayFormEl.hidden = !dayFormEl.hidden;
    if (!dayFormEl.hidden) dayFormEl.querySelector('input[name=date]').focus();
  });
  document.getElementById('day-form-cancel').addEventListener('click', () => {
    dayFormEl.hidden = true;
    dayFormEl.reset();
  });

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

  // Days form + list
  const dayForm = document.getElementById('day-form');
  const daysList = document.getElementById('days-list');
  dayForm.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = dayForm.querySelector('button[type=submit]');
    btn.disabled = true; btn.textContent = 'Parsing with AI…';
    try {
      const fd = new FormData(dayForm);
      const body = {
        date: fd.get('date'),
        raw_text: fd.get('raw_text'),
        theme: fd.get('theme') || null,
        tour_manager: fd.get('tour_manager') || null,
      };
      await api(`/trips/${tripId}/days`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      dayForm.reset();
      dayForm.hidden = true;
      await loadDaysList(tripId, daysList);
    } catch (err) {
      alert('Day parse failed: ' + err.message);
    } finally {
      btn.disabled = false; btn.textContent = 'Parse with AI';
    }
  });
  await loadDaysList(tripId, daysList);

  await loadPhotos();
  startPolling();
}

async function loadDaysList(tripId, list) {
  const days = await api(`/trips/${tripId}/days`);
  if (!days.length) {
    list.innerHTML = '<div class="muted small" style="padding:8px 0;">No days yet. Click <strong>+ Add a day</strong> above to paste the day plan.</div>';
    return;
  }
  list.innerHTML = days.map(d => `
    <div class="trip-row" style="margin-bottom:8px;">
      <a href="#trip-day/${d.id}" style="display:flex;align-items:center;gap:12px;flex:1;text-decoration:none;color:inherit;">
        <div class="name">${fmtDate(d.date)} · ${escapeHtml(d.theme || 'Day')}</div>
        <span class="muted">${d.photo_count} photo${d.photo_count !== 1 ? 's' : ''}</span>
        <span class="pill ${d.has_approved_video ? 'ok' : ''}">
          ${d.has_approved_video ? '✓ video published' : 'no video yet'}
        </span>
      </a>
      <button onclick="deleteDay('${d.id}','${escapeHtml(d.theme || 'this day')}','${tripId}')"
        class="day-del" title="Delete day">×</button>
    </div>
  `).join('');
}

window.deleteDay = async (dayId, dayName, tripId) => {
  if (!confirm(`Delete "${dayName}"?\n\nThis removes the itinerary + voiceover script + any rendered videos for the day. Photos stay (they become un-linked).`)) return;
  try {
    await api(`/trip-days/${dayId}`, { method: 'DELETE' });
    const list = document.getElementById('days-list');
    if (list) await loadDaysList(tripId, list);
  } catch (err) { alert('Delete failed: ' + err.message); }
};

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

const _selectedPhotos = new Set();

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
    updateSelectionBar();
    return;
  }
  // Drop selections for photos no longer in view
  const visibleIds = new Set(photos.map(p => p.id));
  for (const id of Array.from(_selectedPhotos)) if (!visibleIds.has(id)) _selectedPhotos.delete(id);

  grid.innerHTML = photos.map(p => `
    <div class="photo-cell ${_selectedPhotos.has(p.id) ? 'selected' : ''}" data-photo-id="${p.id}" data-photo='${escapeHtml(JSON.stringify(p))}'>
      <input type="checkbox" class="photo-check" data-id="${p.id}" ${_selectedPhotos.has(p.id) ? 'checked' : ''}>
      <span class="photo-status ${p.status}">${p.status}</span>
      <img src="${p.url}" loading="lazy" alt="">
      <div class="photo-tags">
        ${p.faces.map(f => `<span class="tag-chip ${f.user_id ? '' : 'unknown'}">
          ${f.user_id ? escapeHtml(f.name) : '?'}${f.confidence != null ? ` · ${(f.confidence * 100).toFixed(0)}%` : ''}
        </span>`).join('')}
      </div>
    </div>
  `).join('');

  grid.querySelectorAll('.photo-check').forEach(cb => {
    cb.addEventListener('click', e => e.stopPropagation());
    cb.addEventListener('change', e => {
      const id = e.target.dataset.id;
      if (e.target.checked) _selectedPhotos.add(id); else _selectedPhotos.delete(id);
      e.target.closest('.photo-cell').classList.toggle('selected', e.target.checked);
      updateSelectionBar();
    });
  });
  grid.querySelectorAll('.photo-cell').forEach(cell => {
    cell.addEventListener('click', e => {
      if (e.target.classList.contains('photo-check')) return;
      openPhotoModal(JSON.parse(cell.dataset.photo));
    });
  });
  updateSelectionBar();
}

function updateSelectionBar() {
  const bar = document.getElementById('selection-bar');
  if (!bar) return;
  const n = _selectedPhotos.size;
  bar.hidden = n === 0;
  bar.querySelector('#selection-count').textContent = `${n} selected`;
}

window.bulkDeleteSelectedPhotos = async () => {
  const ids = Array.from(_selectedPhotos);
  if (!ids.length) return;
  if (!confirm(`Delete ${ids.length} photo${ids.length === 1 ? '' : 's'}?\n\nThis removes them from the trip + storage. Cannot be undone.`)) return;
  const btn = document.getElementById('selection-delete');
  btn.disabled = true; btn.textContent = `Deleting ${ids.length}…`;
  let failed = 0;
  for (const id of ids) {
    try { await api(`/photos/${id}`, { method: 'DELETE' }); }
    catch { failed++; }
  }
  _selectedPhotos.clear();
  btn.disabled = false; btn.textContent = 'Delete selected';
  if (failed) alert(`${failed} delete${failed === 1 ? '' : 's'} failed.`);
  await loadPhotos();
};

window.clearPhotoSelection = () => {
  _selectedPhotos.clear();
  document.querySelectorAll('.photo-check').forEach(cb => { cb.checked = false; });
  document.querySelectorAll('.photo-cell.selected').forEach(c => c.classList.remove('selected'));
  updateSelectionBar();
};

// ---------- modal ----------
const modal = document.getElementById('modal');
const modalBody = document.getElementById('modal-body');

// Per-modal state for the draw-bbox flow.
let _modalState = null;  // { photo, users, drawing, dragOrigin, dragRect, resizeObserver }

function closeModal() {
  if (_modalState?.resizeObserver) _modalState.resizeObserver.disconnect();
  _modalState = null;
  modal.hidden = true;
}
document.getElementById('modal-close').addEventListener('click', closeModal);
modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if (!_modalState || modal.hidden) return;
  if (_modalState.drawing) { e.preventDefault(); cancelDraw(); return; }
  closeModal();
});

async function openPhotoModal(photo) {
  modal.hidden = false;
  modalBody.innerHTML = `<div>Loading…</div>`;
  const users = await getUsers();
  renderModalBody(photo, users);
}

function renderModalBody(photo, users) {
  if (_modalState?.resizeObserver) _modalState.resizeObserver.disconnect();
  _modalState = { photo, users, drawing: false, dragOrigin: null, dragRect: null, resizeObserver: null };

  modalBody.innerHTML = `
    <h2 style="margin:0">Photo · ${photo.status}</h2>
    <div class="muted small">${photo.id}</div>
    <div class="modal-img-wrap" id="img-wrap">
      <img id="modal-img" src="${photo.url}" alt="">
      <div id="face-overlay" class="overlay"></div>
    </div>
    <h3 style="margin:0 0 8px">Detected faces</h3>
    <div class="modal-faces">
      ${photo.faces.length === 0 ? '<div class="muted">No faces detected.</div>' : ''}
      ${photo.faces.map(f => `
        <div class="face-row">
          <span class="name">${f.user_id ? escapeHtml(f.name) : 'Unmatched face'}</span>
          <span class="conf">${f.confidence != null ? Number(f.confidence).toFixed(0) + '%' : '—'} · ${f.source}</span>
          <button class="remove" data-face-id="${f.id}">Remove</button>
        </div>
      `).join('')}
    </div>
    <div class="modal-add-tag">
      <button id="enter-draw-mode" class="btn primary">+ Add manual tag</button>
      <div id="save-panel" class="save-panel" hidden>
        <span class="muted small">Tag this face as:</span>
        <select id="tag-user-select">
          ${users.map(u => `<option value="${u.id}">${escapeHtml(u.name)}</option>`).join('')}
        </select>
        <button id="save-tag" class="btn primary">Save tag</button>
        <button id="cancel-tag" class="btn">Cancel</button>
        <div id="save-error" class="error" hidden></div>
      </div>
    </div>
  `;

  // Remove handlers (existing detected faces)
  modalBody.querySelectorAll('button[data-face-id]').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const updated = await api(`/photos/${photo.id}/faces`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ remove_face_ids: [btn.dataset.faceId] }),
        });
        renderModalBody(updated, users);
        await loadPhotos();
      } catch (e) {
        btn.disabled = false;
        showToast('Remove failed: ' + parseApiError(e), 'err');
      }
    });
  });

  // Overlay rendering — defer until image actually has dimensions
  const img = modalBody.querySelector('#modal-img');
  const overlay = modalBody.querySelector('#face-overlay');
  const layoutOverlay = () => layoutFaceOverlay(img, overlay, photo);
  if (img.complete && img.naturalWidth > 0) layoutOverlay();
  else img.addEventListener('load', layoutOverlay);

  // ResizeObserver — handle modal resize / font-load relayout / devtools open
  _modalState.resizeObserver = new ResizeObserver(layoutOverlay);
  _modalState.resizeObserver.observe(img);

  // Draw-mode entry
  modalBody.querySelector('#enter-draw-mode').addEventListener('click', enterDrawMode);
  modalBody.querySelector('#cancel-tag').addEventListener('click', cancelDraw);
  modalBody.querySelector('#save-tag').addEventListener('click', () => submitManualTag(photo, img, overlay));
  bindDrawHandlers(overlay);
}

function layoutFaceOverlay(img, overlay, photo) {
  const rect = img.getBoundingClientRect();
  // Anchor overlay over the displayed image — wrap is position:relative
  overlay.style.width = rect.width + 'px';
  overlay.style.height = rect.height + 'px';
  // Wipe + redraw face boxes
  overlay.querySelectorAll('.face-box').forEach(n => n.remove());
  (photo.faces || []).forEach(f => {
    if (f.bbox_space && f.bbox_space !== 'normalised') {
      // Legacy pixel rows — silently hide (current DB has 0)
      console.warn('skipping pixel-space face row', f.id);
      return;
    }
    const [x, y, w, h] = f.bbox || [];
    if (!Number.isFinite(x) || w <= 0 || h <= 0) return;
    const box = document.createElement('div');
    box.className = `face-box source-${f.source}`;
    box.style.left = (x * rect.width) + 'px';
    box.style.top = (y * rect.height) + 'px';
    box.style.width = (w * rect.width) + 'px';
    box.style.height = (h * rect.height) + 'px';
    const nameLabel = f.user_id ? (shortName(f.name) || '?') : '?';
    const full = (f.user_id ? f.name : 'Unmatched') + ` · ${f.source}` + (f.confidence != null ? ` · ${Number(f.confidence).toFixed(0)}%` : '');
    box.innerHTML = `<span class="label" title="${escapeHtml(full)}">${escapeHtml(nameLabel)}</span>`;
    overlay.appendChild(box);
  });
}

function enterDrawMode() {
  if (!_modalState) return;
  _modalState.drawing = true;
  const overlay = modalBody.querySelector('#face-overlay');
  overlay.classList.add('drawing');
  modalBody.querySelector('#enter-draw-mode').hidden = true;
}

function cancelDraw() {
  if (!_modalState) return;
  const overlay = modalBody.querySelector('#face-overlay');
  overlay.classList.remove('drawing');
  if (_modalState.dragRect) { _modalState.dragRect.remove(); _modalState.dragRect = null; }
  _modalState.dragOrigin = null;
  _modalState.drawing = false;
  const panel = modalBody.querySelector('#save-panel');
  if (panel) panel.hidden = true;
  modalBody.querySelector('#enter-draw-mode').hidden = false;
  const err = modalBody.querySelector('#save-error');
  if (err) { err.hidden = true; err.textContent = ''; }
}

function bindDrawHandlers(overlay) {
  overlay.addEventListener('pointerdown', e => {
    if (!_modalState?.drawing) return;
    e.preventDefault();
    overlay.setPointerCapture(e.pointerId);
    const rect = overlay.getBoundingClientRect();
    _modalState.dragOrigin = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    // Clear previous draw-rect if any
    if (_modalState.dragRect) _modalState.dragRect.remove();
    const r = document.createElement('div');
    r.className = 'draw-rect';
    _modalState.dragRect = r;
    overlay.appendChild(r);
  });

  overlay.addEventListener('pointermove', e => {
    if (!_modalState?.dragOrigin) return;
    const rect = overlay.getBoundingClientRect();
    const cur = {
      x: Math.max(0, Math.min(rect.width, e.clientX - rect.left)),
      y: Math.max(0, Math.min(rect.height, e.clientY - rect.top)),
    };
    const o = _modalState.dragOrigin;
    Object.assign(_modalState.dragRect.style, {
      left: Math.min(o.x, cur.x) + 'px',
      top: Math.min(o.y, cur.y) + 'px',
      width: Math.abs(cur.x - o.x) + 'px',
      height: Math.abs(cur.y - o.y) + 'px',
    });
  });

  overlay.addEventListener('pointerup', e => {
    if (!_modalState?.dragOrigin || !_modalState?.dragRect) return;
    overlay.releasePointerCapture(e.pointerId);
    const w = parseFloat(_modalState.dragRect.style.width || '0');
    const h = parseFloat(_modalState.dragRect.style.height || '0');
    _modalState.dragOrigin = null;
    if (Math.hypot(w, h) < 5) {
      // Stray click — discard
      _modalState.dragRect.remove();
      _modalState.dragRect = null;
      return;
    }
    // Show pinned save panel
    modalBody.querySelector('#save-panel').hidden = false;
  });
}

async function submitManualTag(photo, img, overlay) {
  if (!_modalState?.dragRect) return;
  const saveBtn = modalBody.querySelector('#save-tag');
  const saveErr = modalBody.querySelector('#save-error');
  const userSel = modalBody.querySelector('#tag-user-select');
  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving…';
  saveErr.hidden = true;
  saveErr.textContent = '';
  const rect = overlay.getBoundingClientRect();
  const x = parseFloat(_modalState.dragRect.style.left) / rect.width;
  const y = parseFloat(_modalState.dragRect.style.top) / rect.height;
  const w = parseFloat(_modalState.dragRect.style.width) / rect.width;
  const h = parseFloat(_modalState.dragRect.style.height) / rect.height;
  const userName = userSel.selectedOptions[0]?.textContent || 'user';
  try {
    const res = await api(`/photos/${photo.id}/manual-tag`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userSel.value, bbox: [x, y, w, h] }),
    });
    const n = res.propagated_count;
    showToast(`Tagged ${userName} · linked to ${n} other photo${n === 1 ? '' : 's'}`);
    renderModalBody(res.photo, _modalState.users);
    loadPhotos();  // async grid refresh
  } catch (e) {
    saveErr.textContent = parseApiError(e);
    saveErr.hidden = false;
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save tag';
  }
}

// ---------- trip day · recap-photos curation ----------

function _debounce(fn, ms) {
  let t, lastArgs, hasArgs = false;
  const wrapped = (...args) => {
    lastArgs = args;
    hasArgs = true;
    clearTimeout(t);
    t = setTimeout(() => { t = null; fn(...lastArgs); }, ms);
  };
  wrapped.flush = () => {
    if (t) { clearTimeout(t); t = null; }
    if (hasArgs) fn(...lastArgs);
  };
  wrapped.cancel = () => {
    if (t) { clearTimeout(t); t = null; }
  };
  return wrapped;
}

let _recapState = null;  // { dayId, selectedIds: [], unselectedIds: [], byId: Map, saveAbort, sortable, lastSavedOrder }

function _setRecapStatus(state, retryHandler) {
  const el = document.getElementById('recap-photos-status');
  if (!el) return;
  el.className = `muted small status-${state}`;
  if (state === 'saving') el.textContent = 'Saving…';
  else if (state === 'saved') {
    el.textContent = 'Saved';
    const tag = Date.now(); el.dataset.savedTag = tag;
    setTimeout(() => { if (el.dataset.savedTag == tag) el.textContent = ''; }, 2000);
  } else if (state === 'failed') {
    el.innerHTML = 'Save failed — <a href="#" class="retry">retry</a>';
    el.style.color = 'var(--red, #c0392b)';
    el.querySelector('.retry').addEventListener('click', (e) => {
      e.preventDefault();
      el.style.color = '';
      if (retryHandler) retryHandler();
    });
  } else {
    el.textContent = '';
    el.style.color = '';
  }
}

function _renderRecapCard(photo, selected) {
  const cls = `photo-cell recap-card ${selected ? 'selected' : 'unselected'}`;
  const facesHtml = (photo.faces || []).map(f => `
    <span class="tag-chip ${f.user_id ? '' : 'unknown'}">
      ${f.user_id ? escapeHtml(f.name || '?') : '?'}
    </span>
  `).join('');
  if (selected) {
    return `
      <div class="${cls}" data-photo-id="${photo.id}" data-photo='${escapeHtml(JSON.stringify(photo))}'>
        <div class="drag-handle" title="Drag to reorder">⋮⋮</div>
        <input type="checkbox" class="photo-check recap-check" data-id="${photo.id}" checked>
        <span class="photo-num">${photo.recap_position ?? '?'}</span>
        <img src="${photo.url}" loading="lazy" alt="">
        <div class="photo-tags">${facesHtml}</div>
      </div>
    `;
  }
  return `
    <div class="${cls}" data-photo-id="${photo.id}" data-photo='${escapeHtml(JSON.stringify(photo))}'>
      <button class="peek-icon" title="Preview" data-photo-id="${photo.id}">🔍</button>
      <img src="${photo.url}" loading="lazy" alt="">
      <button class="add-btn" data-id="${photo.id}">+ Add</button>
      <div class="photo-tags">${facesHtml}</div>
    </div>
  `;
}

function _renumberSelected() {
  const grid = document.getElementById('recap-selected-grid');
  if (!grid) return;
  grid.querySelectorAll('.photo-cell').forEach((el, i) => {
    const b = el.querySelector('.photo-num');
    if (b) b.textContent = i + 1;
  });
  const countEl = document.getElementById('recap-selected-count');
  if (countEl) countEl.textContent = grid.querySelectorAll('.photo-cell').length;
}

function _refreshUnselectedHeader() {
  const grid = document.getElementById('recap-unselected-grid');
  const wrap = document.getElementById('recap-unselected-wrap');
  if (!grid || !wrap) return;
  const n = grid.querySelectorAll('.photo-cell').length;
  wrap.hidden = n === 0;
  const countEl = document.getElementById('recap-unselected-count');
  if (countEl) countEl.textContent = n;
}

function _currentSelectedOrder() {
  return [...document.getElementById('recap-selected-grid')
    .querySelectorAll('.photo-cell')].map(el => el.dataset.photoId);
}

function _snapshotOrder() {
  return _recapState ? [..._recapState.lastSavedOrder] : [];
}

function _rollbackToSnapshot() {
  if (!_recapState || !_recapState.sortable) return;
  _recapState.sortable.sort(_recapState.lastSavedOrder, true);
  _renumberSelected();
}

async function initRecapPhotosSection(dayId, photos) {
  const empty = document.getElementById('recap-photos-empty');
  const selectedWrap = document.getElementById('recap-selected-wrap');
  const selectedGrid = document.getElementById('recap-selected-grid');
  const unselectedGrid = document.getElementById('recap-unselected-grid');

  if (!photos.length) {
    empty.hidden = false;
    selectedWrap.hidden = true;
    document.getElementById('recap-unselected-wrap').hidden = true;
    return;
  }
  empty.hidden = true;
  selectedWrap.hidden = false;

  const selected = photos.filter(p => p.recap_position != null);
  const unselected = photos.filter(p => p.recap_position == null);

  selectedGrid.innerHTML = selected.map(p => _renderRecapCard(p, true)).join('');
  unselectedGrid.innerHTML = unselected.map(p => _renderRecapCard(p, false)).join('');

  _renumberSelected();
  _refreshUnselectedHeader();

  // State
  _recapState = {
    dayId,
    saveAbort: null,
    sortable: null,
    lastSavedOrder: selected.map(p => p.id),
  };

  // Autosave (debounced) — tracks the in-flight promise so Generate can await it.
  const _doSave = async () => {
    if (!_recapState) return;
    if (_recapState.saveAbort) _recapState.saveAbort.abort();
    _recapState.saveAbort = new AbortController();
    const ordered = _currentSelectedOrder();
    _setRecapStatus('saving');
    try {
      await api(`/trip-days/${dayId}/recap-photos`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ordered_photo_ids: ordered }),
        signal: _recapState.saveAbort.signal,
      });
      _recapState.lastSavedOrder = ordered;
      _setRecapStatus('saved');
    } catch (e) {
      if (e.name === 'AbortError') return;
      _setRecapStatus('failed', () => _saveImmediate());
      _rollbackToSnapshot();
    }
  };
  const _save = _debounce(_doSave, 600);

  // Force-fire helper: cancel any pending debounce + run immediately + return promise.
  const _saveImmediate = () => {
    _save.cancel?.();  // cancel pending debounce if any
    const p = _doSave();
    if (_recapState) _recapState.lastSavePromise = p;
    return p;
  };
  _recapState.saveImmediate = _saveImmediate;

  // Init Sortable on selected grid
  _recapState.sortable = new Sortable(selectedGrid, {
    handle: '.drag-handle',
    animation: 200,
    ghostClass: 'card-ghost',
    chosenClass: 'card-chosen',
    dataIdAttr: 'data-photo-id',
    onUpdate: () => {
      _renumberSelected();
      const order = _currentSelectedOrder();
      console.log('[recap] drag end | new DOM order:', order);
      _setRecapStatus('failed', () => { /* prompt user */ });
      const el = document.getElementById('recap-photos-status');
      if (el) {
        el.textContent = 'Unsaved — click "Set order" to apply';
        el.style.color = 'var(--red, #c0392b)';
      }
    },
  });

  // Checkbox handlers (deselect → move card to unselected grid)
  selectedGrid.addEventListener('change', (e) => {
    const cb = e.target.closest('.recap-check');
    if (!cb) return;
    if (cb.checked) return;
    const cell = cb.closest('.photo-cell');
    const photo = JSON.parse(cell.dataset.photo);
    cell.remove();
    // Mark photo as no longer in recap, re-render as unselected card
    photo.recap_position = null;
    unselectedGrid.insertAdjacentHTML('beforeend', _renderRecapCard(photo, false));
    _renumberSelected();
    _refreshUnselectedHeader();
    _save();
  });

  // Click handlers on selected grid (modal-open + checkbox stopPropagation)
  selectedGrid.addEventListener('click', (e) => {
    if (e.target.closest('.photo-check') || e.target.closest('.drag-handle')) {
      e.stopPropagation();
      return;
    }
    const cell = e.target.closest('.photo-cell');
    if (cell) openPhotoModal(JSON.parse(cell.dataset.photo));
  });

  // "+ Add" and peek handlers on unselected grid
  unselectedGrid.addEventListener('click', (e) => {
    const peek = e.target.closest('.peek-icon');
    if (peek) {
      const cell = peek.closest('.photo-cell');
      openPhotoModal(JSON.parse(cell.dataset.photo));
      return;
    }
    const addBtn = e.target.closest('.add-btn');
    if (addBtn) {
      const cell = addBtn.closest('.photo-cell');
      const photo = JSON.parse(cell.dataset.photo);
      cell.remove();
      // Append to selected list, recap_position will be set by server
      photo.recap_position = selectedGrid.querySelectorAll('.photo-cell').length + 1;
      selectedGrid.insertAdjacentHTML('beforeend', _renderRecapCard(photo, true));
      _renumberSelected();
      _refreshUnselectedHeader();
      _save();
    }
  });

  // "Set order" button — explicit save of the current DOM order
  const setOrderBtn = document.getElementById('recap-set-order');
  if (setOrderBtn) {
    setOrderBtn.addEventListener('click', async () => {
      const order = _currentSelectedOrder();
      console.log('[recap] SET ORDER clicked | sending order:', order);
      setOrderBtn.disabled = true;
      setOrderBtn.textContent = 'Saving…';
      const el = document.getElementById('recap-photos-status');
      if (el) { el.textContent = ''; el.style.color = ''; }
      try {
        const res = await api(`/trip-days/${dayId}/recap-photos`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ordered_photo_ids: order }),
        });
        console.log('[recap] SET ORDER response:', res);
        if (_recapState) _recapState.lastSavedOrder = order;
        _setRecapStatus('saved');
        // Read back from server to verify
        const day = await api(`/trip-days/${dayId}`);
        const serverOrder = (day.photos || [])
          .filter(p => p.recap_position != null)
          .sort((a, b) => a.recap_position - b.recap_position)
          .map(p => p.id);
        console.log('[recap] SERVER ORDER after save:', serverOrder);
        if (JSON.stringify(serverOrder) !== JSON.stringify(order)) {
          console.error('[recap] MISMATCH! Sent vs server:', { sent: order, server: serverOrder });
        } else {
          console.log('[recap] ✓ Server order matches what we sent');
        }
      } catch (e) {
        console.error('[recap] SET ORDER failed:', e);
        if (el) { el.textContent = 'Save failed: ' + parseApiError(e); el.style.color = 'var(--red, #c0392b)'; }
      } finally {
        setOrderBtn.disabled = false;
        setOrderBtn.textContent = '✓ Set order';
      }
    });
  }

  // "Add all" button
  const addAllBtn = document.getElementById('recap-add-all');
  if (addAllBtn) {
    addAllBtn.addEventListener('click', () => {
      [...unselectedGrid.querySelectorAll('.photo-cell')].forEach(cell => {
        const photo = JSON.parse(cell.dataset.photo);
        cell.remove();
        photo.recap_position = selectedGrid.querySelectorAll('.photo-cell').length + 1;
        selectedGrid.insertAdjacentHTML('beforeend', _renderRecapCard(photo, true));
      });
      _renumberSelected();
      _refreshUnselectedHeader();
      _save();
    });
  }
}

// ---------- trip day ----------
let tripDayPollTimer = null;

async function renderTripDay(dayId) {
  root.innerHTML = '';
  root.appendChild(tpl('tpl-trip-day'));
  if (tripDayPollTimer) clearInterval(tripDayPollTimer);

  const data = await api(`/trip-days/${dayId}`);
  const trips = await api('/trips');
  const trip = trips.find(t => t.id === data.trip_id);
  const tripName = trip ? trip.name : 'Trip';

  document.getElementById('tday-trip-crumb').href = `#trip/${data.trip_id}`;
  document.getElementById('tday-trip-crumb').textContent = tripName;
  document.getElementById('tday-day-crumb').textContent = `${fmtDate(data.date)} · ${data.theme || 'Day'}`;
  document.getElementById('tday-title').textContent = data.theme || `Day · ${fmtDate(data.date)}`;
  document.getElementById('tday-meta').textContent =
    [fmtDate(data.date), data.tour_manager && `TM ${data.tour_manager}`, data.weather]
      .filter(Boolean).join(' · ');

  const scriptArea = document.getElementById('tday-script');
  scriptArea.value = data.voiceover_script || '';

  document.getElementById('tday-save-script').addEventListener('click', async () => {
    const btn = document.getElementById('tday-save-script');
    btn.disabled = true; btn.textContent = 'Saving…';
    try {
      await api(`/trip-days/${dayId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voiceover_script: scriptArea.value }),
      });
      document.getElementById('tday-script-status').textContent = 'Saved.';
      setTimeout(() => { document.getElementById('tday-script-status').textContent = ''; }, 2000);
    } catch (err) { alert('Save failed: ' + err.message); }
    finally { btn.disabled = false; btn.textContent = 'Save script'; }
  });

  // Disable Remotion option if renderer offline
  try {
    const rh = await api('/health/renderer');
    const remoOpt = document.querySelector('#tday-engine option[value="remotion"]');
    if (remoOpt && !rh.renderer_available) {
      remoOpt.textContent = 'Remotion (offline — start renderer)';
      remoOpt.disabled = true;
      // Auto-fallback to shotstack if remotion was default
      const sel = document.getElementById('tday-engine');
      if (sel.value === 'remotion') sel.value = 'shotstack';
    }
  } catch (_) {}

  document.getElementById('tday-generate-recap').addEventListener('click', async () => {
    // Gate: must have at least one photo selected
    const selectedCount = document
      .getElementById('recap-selected-grid')
      .querySelectorAll('.photo-cell').length;
    if (selectedCount === 0) {
      alert('Add photos to the recap before generating.');
      return;
    }
    const btn = document.getElementById('tday-generate-recap');
    const engine = document.getElementById('tday-engine').value;
    btn.disabled = true; btn.textContent = `Queued (${engine})…`;
    try {
      // Log what we believe the server order should be right before generate.
      const localOrder = _currentSelectedOrder();
      console.log('[generate] local DOM order:', localOrder);
      const dayBefore = await api(`/trip-days/${dayId}`);
      const serverOrder = (dayBefore.photos || [])
        .filter(p => p.recap_position != null)
        .sort((a, b) => a.recap_position - b.recap_position)
        .map(p => p.id);
      console.log('[generate] server order (recap_position):', serverOrder);
      if (JSON.stringify(localOrder) !== JSON.stringify(serverOrder)) {
        console.error('[generate] ⚠️ MISMATCH — DOM differs from server. Click "Set order" first.');
        alert('Your reorder has not been saved yet. Click "✓ Set order" first, then Generate.');
        return;
      }
      console.log('[generate] ✓ DOM matches server. Submitting render with order:', serverOrder);
      await api(`/trip-days/${dayId}/generate-recap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ renderer: engine }),
      });
      await loadRenderHistory(dayId);
      startRenderPolling(dayId);
    } catch (err) { alert('Generate failed: ' + parseApiError(err)); }
    finally { btn.disabled = false; btn.textContent = '▶ Generate recap video'; }
  });

  // Photos-in-recap section
  await initRecapPhotosSection(dayId, data.photos || []);

  // Items table
  const tbody = document.querySelector('#tday-items tbody');
  if (!data.items.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">No items yet.</td></tr>';
  } else {
    tbody.innerHTML = data.items.map(it => `
      <tr data-item-id="${it.id}">
        <td class="time-cell">
          <input type="time" class="time-input start" data-field="start_time" value="${(it.start_time||'').slice(0,5)}">
          <span class="muted">–</span>
          <input type="time" class="time-input end" data-field="end_time" value="${(it.end_time||'').slice(0,5)}">
          <span class="time-status muted small"></span>
        </td>
        <td>
          <strong>${escapeHtml(it.title)}</strong>
          ${it.description ? `<div class="muted small" style="margin-top:2px;">${escapeHtml(it.description)}</div>` : ''}
        </td>
        <td><span class="muted small">${it.importance}/10</span> ${'★'.repeat(Math.min(5, Math.round(it.importance / 2)))}</td>
        <td class="num photo-count-cell">${it.photo_count}</td>
      </tr>
    `).join('');

    // Wire up inline edits
    tbody.querySelectorAll('input.time-input').forEach(inp => {
      inp.addEventListener('change', async e => {
        const tr = e.target.closest('tr');
        const itemId = tr.dataset.itemId;
        const field = e.target.dataset.field;
        const newValue = e.target.value;
        const status = tr.querySelector('.time-status');
        status.textContent = 'saving…';
        try {
          const updated = await api(`/itinerary-items/${itemId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [field]: newValue }),
          });
          status.textContent = 'saved';
          tr.querySelector('.photo-count-cell').textContent = updated.photo_count;
          setTimeout(() => { status.textContent = ''; }, 1500);
        } catch (err) {
          status.textContent = '❌ ' + err.message;
        }
      });
    });
  }

  await loadRenderHistory(dayId);
  // If there's a render in flight, start polling
  if (data.latest_video && ['queued','rendering'].includes(data.latest_video.status)) {
    startRenderPolling(dayId);
  }
}

async function loadRenderHistory(dayId) {
  const renders = await api(`/video-renders`);
  const mine = renders.filter(r => r.trip_day_id === dayId);
  const el = document.getElementById('tday-renders');
  if (!mine.length) { el.innerHTML = '<div class="muted small">No renders yet.</div>'; return; }
  el.innerHTML = mine.map(r => `
    <div class="card" style="margin-bottom:10px;padding:12px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <div>
          <strong>v${r.version}</strong>
          <span class="pill ${statusPillClass(r.status)}" style="margin-left:8px;">${r.status.replace('_',' ')}</span>
          <span class="pill" style="margin-left:6px;background:var(--muted-bg);">${r.engine || 'shotstack'}</span>
          <div class="muted small" style="margin-top:4px;">${new Date(r.created_at).toLocaleString()}</div>
          ${r.error ? `<div class="muted small" style="color:var(--red, #c0392b);margin-top:4px;">Error: ${escapeHtml(r.error)}</div>` : ''}
        </div>
        ${r.mp4_url ? `<video src="${r.mp4_url}" controls style="max-width:240px;border-radius:8px;"></video>` : ''}
      </div>
      ${r.status === 'pending_review' ? `
        <div style="margin-top:10px;display:flex;gap:8px;">
          <button onclick="approveVideo('${r.id}','${dayId}')">Approve</button>
          <button onclick="rejectVideo('${r.id}','${dayId}')" style="background:var(--red);">Reject</button>
        </div>` : ''}
    </div>
  `).join('');
}

function statusPillClass(status) {
  if (status === 'approved') return 'ok';
  if (status === 'failed' || status === 'rejected') return 'err';
  return '';
}

function startRenderPolling(dayId) {
  if (tripDayPollTimer) clearInterval(tripDayPollTimer);
  tripDayPollTimer = setInterval(async () => {
    try {
      await loadRenderHistory(dayId);
      const renders = await api(`/video-renders`);
      const mine = renders.filter(r => r.trip_day_id === dayId);
      const inFlight = mine.some(r => ['queued','rendering'].includes(r.status));
      if (!inFlight) {
        clearInterval(tripDayPollTimer);
        tripDayPollTimer = null;
      }
    } catch (_) {}
  }, 5000);
}

window.approveVideo = async (renderId, dayId) => {
  await api(`/video-renders/${renderId}/approve`, { method: 'POST' });
  await loadRenderHistory(dayId);
};
window.rejectVideo = async (renderId, dayId) => {
  await api(`/video-renders/${renderId}/reject`, { method: 'POST' });
  await loadRenderHistory(dayId);
};

// ---------- videos section ----------
let _videosCache = null;

async function renderVideos() {
  root.innerHTML = '';
  root.appendChild(tpl('tpl-videos'));
  _videosCache = await api('/video-renders');
  const select = document.getElementById('videos-filter');
  select.addEventListener('change', () => drawVideos(select.value));
  drawVideos(select.value);
}

function drawVideos(filter) {
  const list = document.getElementById('videos-list');
  const count = document.getElementById('videos-count');
  let rows = _videosCache || [];
  if (filter !== 'all') rows = rows.filter(r => r.status === filter);
  count.textContent = `${rows.length} of ${(_videosCache||[]).length} videos`;
  if (!rows.length) {
    list.innerHTML = `<div class="empty">No videos in this filter.</div>`;
    return;
  }
  list.innerHTML = rows.map(r => `
    <div class="card" style="margin-bottom:12px;">
      <div style="display:flex;gap:16px;align-items:flex-start;">
        <div style="flex:1;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
            <strong>v${r.version}</strong>
            <span class="pill ${statusPillClass(r.status)}">${r.status.replace('_',' ')}</span>
            <span class="pill" style="background:var(--muted-bg);">${r.engine || 'shotstack'}</span>
          </div>
          <div class="muted small">trip-day ${r.trip_day_id.slice(0,8)}… · ${new Date(r.created_at).toLocaleString()}</div>
          ${r.admin_notes ? `<div class="muted small" style="margin-top:6px;">${escapeHtml(r.admin_notes)}</div>` : ''}
          <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;">
            ${r.status === 'pending_review' ? `
              <button onclick="approveVideoTop('${r.id}')">Approve</button>
              <button onclick="rejectVideoTop('${r.id}')" style="background:var(--red);">Reject</button>
            ` : ''}
            ${r.status === 'approved' ? `
              <button onclick="rejectVideoTop('${r.id}')" class="ghost" style="background:white;color:var(--red);border:1px solid var(--border);">Unpublish</button>
            ` : ''}
            <a href="#trip-day/${r.trip_day_id}" class="link" style="padding:8px 14px;text-decoration:none;color:var(--brand);font-weight:600;">Open day →</a>
          </div>
        </div>
        ${r.mp4_url ? `<video src="${r.mp4_url}" controls preload="metadata" style="max-width:320px;border-radius:8px;"></video>` : '<div class="muted small">(no mp4 yet)</div>'}
      </div>
    </div>
  `).join('');
}

window.approveVideoTop = async (renderId) => {
  await api(`/video-renders/${renderId}/approve`, { method: 'POST' });
  _videosCache = await api('/video-renders');
  drawVideos(document.getElementById('videos-filter').value);
};
window.rejectVideoTop = async (renderId) => {
  await api(`/video-renders/${renderId}/reject`, { method: 'POST' });
  _videosCache = await api('/video-renders');
  drawVideos(document.getElementById('videos-filter').value);
};

// ---------- boot ----------
refreshHealth();
route();
setInterval(refreshHealth, 30000);
