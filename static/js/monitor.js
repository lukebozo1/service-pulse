let chart = null;
let lastCheckTs = null;
const CHECK_INTERVAL = 60;

const arrowUp   = `<svg viewBox="0 0 24 24" fill="none" stroke="#00e587" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>`;
const arrowDown = `<svg viewBox="0 0 24 24" fill="none" stroke="#ff4560" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>`;

// Countdown
setInterval(() => {
    if (lastCheckTs === null) return;
    const elapsed   = Math.floor(Date.now() / 1000) - lastCheckTs;
    const remaining = Math.max(0, CHECK_INTERVAL - elapsed);
    const pct       = (remaining / CHECK_INTERVAL) * 100;
    document.getElementById('countdown-value').textContent     = remaining + 's';
    document.getElementById('countdown-fill').style.width      = pct + '%';
    document.getElementById('countdown-fill').style.background =
        remaining < 10 ? 'var(--warn)' : 'var(--accent)';
}, 1000);

// Data polling
async function fetchData() {
    try {
        const res  = await fetch('/api/data');
        const data = await res.json();
        const st   = data.current_state;
        const hist = data.history;

        document.getElementById('ssh-dot').className  = 'status-dot' + (st.ssh_up  ? ' up' : '');
        document.getElementById('http-dot').className = 'status-dot' + (st.http_up ? ' up' : '');
        document.getElementById('ftp-dot').className  = 'status-dot' + (st.ftp_up  ? ' up-orange' : '');

        const latest = hist[hist.length - 1] || { ssh: 0, http: 0, ftp: 0 };
        document.getElementById('ssh-score').textContent    = latest.ssh;
        document.getElementById('http-score').textContent   = latest.http;
        document.getElementById('ftp-score').textContent    = latest.ftp;
        document.getElementById('current-user').textContent = st.current_user || '—';
        document.getElementById('last-check').textContent   = st.last_check  || '—';

        if (st.last_check_ts) lastCheckTs = st.last_check_ts;

        renderChart(hist);
        renderChecks(data.recent_checks || []);
    } catch (e) {
        console.error('Poll error', e);
    }
}

setInterval(fetchData, 5000);
window.addEventListener('DOMContentLoaded', fetchData);

// Chart
function renderChart(history) {
    const ctx    = document.getElementById('scoreChart');
    const labels = history.map(h => h.time);
    const ssh    = history.map(h => h.ssh);
    const http   = history.map(h => h.http);
    const ftp    = history.map(h => h.ftp ?? 0);

    if (chart) {
        chart.data.labels           = labels;
        chart.data.datasets[0].data = ssh;
        chart.data.datasets[1].data = http;
        chart.data.datasets[2].data = ftp;
        chart.update('none');
        return;
    }

    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'SSH',
                    data: ssh,
                    borderColor: '#00e587',
                    backgroundColor: 'rgba(0,229,135,0.07)',
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                },
                {
                    label: 'HTTP',
                    data: http,
                    borderColor: '#0099ff',
                    backgroundColor: 'rgba(0,153,255,0.07)',
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                },
                {
                    label: 'FTP',
                    data: ftp,
                    borderColor: '#ff9f40',
                    backgroundColor: 'rgba(255,159,64,0.07)',
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0e1117',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    titleColor: '#9ca3b0',
                    bodyColor: '#e8eaf0',
                    padding: 12,
                    callbacks: {
                        label: ctx => ` ${ctx.dataset.label}: ${ctx.raw} pts`
                    }
                }
            },
            scales: {
                y: {
                    grid:  { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#5a6478', font: { size: 12 } }
                },
                x: {
                    grid:  { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#5a6478', font: { size: 11 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 10 }
                }
            }
        }
    });
}

// Recent checks
function makeCircles(checks, key, service) {
    const slots = Array(10).fill(null);
    checks.forEach((c, i) => { slots[i] = c; });
    return slots.map((c, i) => {
        if (!c) return `<div class="check-circle empty"></div>`;
        const up = c[key];
        const onclick = !up ? `onclick="jumpToLog('${service}','${escHtml(c.time)}')"` : '';
        return `
            <div class="check-circle ${up ? 'up' : 'down'}" ${onclick} title="${escHtml(c.time)}${c.user ? ' · ' + escHtml(c.user) : ''}">
                ${up ? arrowUp : arrowDown}
                <span class="check-circle-time">${escHtml(c.time.slice(0, 5))}</span>
            </div>`;
    }).join('');
}

function renderChecks(checks) {
    document.getElementById('checks-ssh').innerHTML  = makeCircles(checks, 'ssh_up',  'SSH');
    document.getElementById('checks-http').innerHTML = makeCircles(checks, 'http_up', 'HTTP');
    document.getElementById('checks-ftp').innerHTML  = makeCircles(checks, 'ftp_up',  'FTP');
}

// Reset scores
async function resetScores() {
    if (!confirm('Reset all scores to zero? This cannot be undone.')) return;
    try {
        const res = await fetch('/api/reset-scores', { method: 'POST' });
        if ((await res.json()).ok) {
            toast('Scores reset to zero.', 'success');
            fetchData();
        }
    } catch (e) {
        toast('Reset failed.', 'error');
    }
}
