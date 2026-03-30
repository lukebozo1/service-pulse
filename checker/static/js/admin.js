// Load current config into form fields on page load
document.addEventListener('DOMContentLoaded', () => {
    fetch('/api/admin/config')
        .then(r => r.json())
        .then(cfg => {
            document.getElementById('cfg-host').value     = cfg.target_host    || '';
            document.getElementById('cfg-search').value   = cfg.search_text    || '';
            document.getElementById('cfg-attacker').value = cfg.attacker_url   || '';
            document.getElementById('comp-target').textContent = cfg.target_host || '—';
            setCompStatus(cfg.competition_active);
        })
        .catch(() => toast('Failed to load config', 'error'));
});

function setCompStatus(active) {
    const badge = document.getElementById('comp-status-badge');
    const btn   = document.getElementById('btn-start');
    if (active) {
        badge.textContent = 'Active';
        badge.className   = 'comp-badge comp-badge-active';
        btn.disabled      = true;
        btn.innerHTML     = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Competition Running';
    } else {
        badge.textContent = 'Waiting';
        badge.className   = 'comp-badge comp-badge-waiting';
        btn.disabled      = false;
        btn.innerHTML     = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Start Competition';
    }
}

function startCompetition() {
    const btn = document.getElementById('btn-start');
    btn.disabled = true;
    btn.textContent = 'Sending signal…';

    fetch('/api/admin/start', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                setCompStatus(true);
                toast('Competition started — signal sent to attacker machine', 'success');
            } else {
                btn.disabled = false;
                btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Start Competition';
                toast('Error: ' + (data.error || 'Unknown error'), 'error');
            }
        })
        .catch(err => {
            btn.disabled = false;
            btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Start Competition';
            toast('Signal failed: ' + err.message, 'error');
        });
}

function saveConfig() {
    const host     = document.getElementById('cfg-host').value.trim();
    const search   = document.getElementById('cfg-search').value.trim();
    const attacker = document.getElementById('cfg-attacker').value.trim();

    if (!host) {
        toast('Target Host cannot be empty', 'error');
        return;
    }
    if (!attacker) {
        toast('Attacker URL cannot be empty', 'error');
        return;
    }

    fetch('/api/admin/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_host: host, search_text: search, attacker_url: attacker })
    })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                document.getElementById('comp-target').textContent = host;
                toast('Configuration saved', 'success');
            } else {
                toast('Save failed: ' + (data.error || 'Unknown error'), 'error');
            }
        })
        .catch(err => toast('Save failed: ' + err.message, 'error'));
}

function resetScores() {
    if (!confirm('Reset all scores? This cannot be undone.')) return;
    fetch('/api/reset-scores', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.ok) toast('Scores reset', 'success');
            else toast('Reset failed', 'error');
        })
        .catch(() => toast('Reset failed', 'error'));
}

function resetLogs() {
    if (!confirm('Clear all logs? This cannot be undone.')) return;
    fetch('/api/reset-logs', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.ok) toast('Logs cleared', 'success');
            else toast('Reset failed', 'error');
        })
        .catch(() => toast('Reset failed', 'error'));
}


// ── Custom Services ────────────────────────────────────────

const SVC_COLORS = ['#a78bfa','#f472b6','#fb923c','#facc15','#34d399','#60a5fa','#f87171','#e879f9'];

document.addEventListener('DOMContentLoaded', loadServices);

function loadServices() {
    fetch('/api/admin/services')
        .then(r => r.json())
        .then(renderServicesTable)
        .catch(() => toast('Failed to load services', 'error'));
}

function renderServicesTable(svcs) {
    const empty = document.getElementById('svc-empty');
    const table = document.getElementById('svc-table');
    const tbody = document.getElementById('svc-tbody');

    if (!svcs.length) {
        empty.style.display = '';
        table.style.display = 'none';
        return;
    }
    empty.style.display = 'none';
    table.style.display = '';
    tbody.innerHTML = svcs.map(s => `
        <tr>
            <td><span class="svc-color-dot" style="background:${escHtml(s.color)}"></span></td>
            <td class="svc-mono">${escHtml(s.name)}</td>
            <td class="svc-mono">${escHtml(s.type.toUpperCase())}</td>
            <td class="svc-mono">${escHtml(s.host)}</td>
            <td class="svc-mono">${s.port != null ? escHtml(String(s.port)) : '—'}</td>
            <td class="svc-mono">${s.search_text ? escHtml(s.search_text) : '—'}</td>
            <td class="svc-actions">
                <button class="btn-danger-outline" style="padding:5px 12px;font-size:0.77rem"
                    onclick="deleteService(${s.id}, '${escHtml(s.name).replace(/'/g,"\\'")}')">Remove</button>
            </td>
        </tr>
    `).join('');
}

function openAddServiceModal() {
    document.getElementById('svc-name').value   = '';
    document.getElementById('svc-type').value   = 'http';
    document.getElementById('svc-host').value   = '';
    document.getElementById('svc-port').value   = '';
    document.getElementById('svc-search').value = '';
    onSvcTypeChange();
    buildColorSwatches();
    document.getElementById('svc-modal').classList.add('open');
    document.getElementById('svc-name').focus();
}

function closeSvcModal() {
    document.getElementById('svc-modal').classList.remove('open');
}

function onSvcTypeChange() {
    const type       = document.getElementById('svc-type').value;
    const portGroup  = document.getElementById('svc-port-group');
    const searchGroup = document.getElementById('svc-search-group');
    const portHint   = document.getElementById('svc-port-hint');
    if (type === 'tcp') {
        portHint.textContent  = '(required)';
        searchGroup.style.display = 'none';
    } else {
        portHint.textContent  = '(optional, defaults to 80)';
        searchGroup.style.display = '';
    }
}

function buildColorSwatches() {
    const container  = document.getElementById('color-swatches');
    const current    = document.getElementById('svc-color').value || SVC_COLORS[0];
    container.innerHTML = SVC_COLORS.map(c => `
        <div class="color-swatch ${c === current ? 'selected' : ''}"
             style="background:${c}"
             onclick="selectColor('${c}', this)"
             title="${c}"></div>
    `).join('');
}

function selectColor(color, el) {
    document.getElementById('svc-color').value = color;
    document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('selected'));
    el.classList.add('selected');
}

async function submitAddService() {
    const name   = document.getElementById('svc-name').value.trim();
    const type   = document.getElementById('svc-type').value;
    const host   = document.getElementById('svc-host').value.trim();
    const port   = document.getElementById('svc-port').value.trim();
    const search = document.getElementById('svc-search').value.trim();
    const color  = document.getElementById('svc-color').value || SVC_COLORS[0];

    if (!name) { toast('Name is required', 'error'); return; }
    if (!host) { toast('Host is required', 'error');  return; }
    if (type === 'tcp' && !port) { toast('Port is required for TCP checks', 'error'); return; }

    try {
        const res  = await fetch('/api/admin/services', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ name, type, host, port: port ? Number(port) : null, search_text: search, color }),
        });
        const data = await res.json();
        if (!res.ok) { toast(data.error || 'Failed to add service', 'error'); return; }
        closeSvcModal();
        toast(`Service "${name}" added`, 'success');
        loadServices();
    } catch (e) {
        toast('Request failed: ' + e.message, 'error');
    }
}

async function deleteService(id, name) {
    if (!confirm(`Remove service "${name}" and its history?`)) return;
    try {
        const res  = await fetch(`/api/admin/services/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.ok) { toast(`Service "${name}" removed`, 'success'); loadServices(); }
        else toast(data.error || 'Failed to remove service', 'error');
    } catch (e) {
        toast('Request failed: ' + e.message, 'error');
    }
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeSvcModal();
});
