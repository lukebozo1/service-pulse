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
