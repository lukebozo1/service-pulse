let logFilter        = 'all';
let pendingHighlight = null;

function jumpToLog(service, time) {
    pendingHighlight = time;
    const btn = document.querySelector(`.filter-btn.f-${service.toLowerCase()}`);
    if (btn) setLogFilter(btn, service);
    else fetchLogs();
    document.getElementById('log-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function setLogFilter(btn, filter) {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    logFilter = filter;
    fetchLogs();
}

async function fetchLogs() {
    try {
        let url = '/api/logs';
        const params = [];
        if (logFilter === 'err') {
            params.push('errors=1');
        } else if (logFilter !== 'all') {
            params.push('service=' + logFilter);
        }
        if (params.length) url += '?' + params.join('&');

        const res  = await fetch(url);
        const logs = await res.json();
        renderLogs(logs);
    } catch (e) {
        console.error('Log fetch error', e);
    }
}

function renderLogs(logs) {
    const el = document.getElementById('log-console');
    if (!logs.length) {
        el.innerHTML = '<div class="log-empty">No log entries found.</div>';
        return;
    }
    el.innerHTML = logs.map(l => `
        <div class="log-entry ${l.status}" data-time="${escHtml(l.time)}">
            <span class="log-time">${escHtml(l.time)}</span>
            <span class="log-badge ${escHtml(l.service)}">${escHtml(l.service)}</span>
            <span class="log-status ${l.status}">${l.status.toUpperCase()}</span>
            <span class="log-msg" title="${escHtml(l.message)}">${escHtml(l.message)}</span>
        </div>
    `).join('');

    if (pendingHighlight) {
        const target = [...el.querySelectorAll('.log-entry')]
            .find(e => e.dataset.time.includes(pendingHighlight));
        if (target) {
            target.classList.add('log-highlight');
            target.scrollIntoView({ block: 'nearest' });
        }
        pendingHighlight = null;
    }
}

async function resetLogs() {
    if (!confirm('Clear all log entries?')) return;
    try {
        const res = await fetch('/api/reset-logs', { method: 'POST' });
        if ((await res.json()).ok) {
            toast('Logs cleared.', 'success');
            fetchLogs();
        }
    } catch (e) {
        toast('Reset failed.', 'error');
    }
}

setInterval(fetchLogs, 5000);
window.addEventListener('DOMContentLoaded', fetchLogs);
