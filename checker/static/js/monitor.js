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
        const customSvcs   = data.custom_services       || [];
        const customRecent = data.custom_recent_checks  || {};

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

        renderChart(hist, customSvcs);
        renderChecks(data.recent_checks || [], customSvcs, customRecent);
        renderCustomStatuses(customSvcs);
        renderChartLegend(customSvcs);
    } catch (e) {
        console.error('Poll error', e);
    }
}

setInterval(fetchData, 5000);
window.addEventListener('DOMContentLoaded', fetchData);

// Chart helpers
function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1,3), 16);
    const g = parseInt(hex.slice(3,5), 16);
    const b = parseInt(hex.slice(5,7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
}

function makeDataset(label, data, color, extra) {
    return {
        label,
        data,
        borderColor: color,
        backgroundColor: hexToRgba(color, 0.07),
        borderWidth: 2.5,
        fill: true,
        tension: 0.35,
        pointRadius: 0,
        pointHoverRadius: 5,
        ...extra,
    };
}

// Chart
function renderChart(history, customSvcs) {
    const ctx    = document.getElementById('scoreChart');
    const labels = history.map(h => h.time);
    const ssh    = history.map(h => h.ssh);
    const http   = history.map(h => h.http);
    const ftp    = history.map(h => h.ftp ?? 0);

    if (!chart) {
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    makeDataset('SSH',  ssh,  '#00e587'),
                    makeDataset('HTTP', http, '#0099ff'),
                    makeDataset('FTP',  ftp,  '#ff9f40'),
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
    } else {
        chart.data.labels           = labels;
        chart.data.datasets[0].data = ssh;
        chart.data.datasets[1].data = http;
        chart.data.datasets[2].data = ftp;
    }

    // Sync custom service datasets (indices 3+)
    const customIds = customSvcs.map(s => s.id);

    // Remove datasets for deleted services
    chart.data.datasets = chart.data.datasets.filter((ds, i) => i < 3 || customIds.includes(ds._svcId));

    // Add or update a dataset per custom service
    customSvcs.forEach(svc => {
        const pts      = history.map(h => (h.custom && h.custom[String(svc.id)] != null) ? h.custom[String(svc.id)] : null);
        const existing = chart.data.datasets.find(ds => ds._svcId === svc.id);
        if (existing) {
            existing.data        = pts;
            existing.borderColor = svc.color;
            existing.backgroundColor = hexToRgba(svc.color, 0.07);
        } else {
            const ds = makeDataset(svc.name, pts, svc.color);
            ds._svcId = svc.id;
            chart.data.datasets.push(ds);
        }
    });

    chart.update('none');
}

// Chart legend (static + dynamic custom services)
function renderChartLegend(customSvcs) {
    const legend = document.getElementById('chart-legend');
    if (!legend) return;
    let html = `
        <div class="legend-item"><div class="legend-pip" style="background:#00e587"></div>SSH</div>
        <div class="legend-item"><div class="legend-pip" style="background:#0099ff"></div>HTTP</div>
        <div class="legend-item"><div class="legend-pip" style="background:#ff9f40"></div>FTP</div>
    `;
    customSvcs.forEach(svc => {
        html += `<div class="legend-item"><div class="legend-pip" style="background:${escHtml(svc.color)}"></div>${escHtml(svc.name)}</div>`;
    });
    legend.innerHTML = html;
}

// Custom service status rows in the status panel
function renderCustomStatuses(customSvcs) {
    const container = document.getElementById('custom-service-rows');
    if (!container) return;
    container.innerHTML = customSvcs.map(svc => {
        const dotStyle = svc.up
            ? `background:${escHtml(svc.color)};box-shadow:0 0 0 3px ${escHtml(svc.color)}33`
            : '';
        return `
            <div class="service-row">
                <div class="service-label">
                    <span class="status-dot" style="${dotStyle}"></span>
                    ${escHtml(svc.name)}
                </div>
                <div class="service-right">
                    <div class="score-value" style="color:${escHtml(svc.color)}">${svc.score}</div>
                    <div class="score-label">points</div>
                </div>
            </div>`;
    }).join('');
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

function renderChecks(checks, customSvcs, customRecent) {
    document.getElementById('checks-ssh').innerHTML  = makeCircles(checks, 'ssh_up',  'SSH');
    document.getElementById('checks-http').innerHTML = makeCircles(checks, 'http_up', 'HTTP');
    document.getElementById('checks-ftp').innerHTML  = makeCircles(checks, 'ftp_up',  'FTP');

    const container = document.getElementById('custom-checks-rows');
    if (!container) return;
    container.innerHTML = customSvcs.map(svc => {
        // API returns newest-first; makeCircles expects newest at index 0
        const svcChecks = (customRecent[String(svc.id)] || []).map(c => ({ ...c, _up: c.up }));
        const slots     = Array(10).fill(null);
        svcChecks.forEach((c, i) => { slots[i] = c; });
        const circles = slots.map(c => {
            if (!c) return `<div class="check-circle empty"></div>`;
            return `<div class="check-circle ${c.up ? 'up' : 'down'}" title="${escHtml(c.time)}">
                ${c.up ? arrowUp : arrowDown}
                <span class="check-circle-time">${escHtml(c.time.slice(0,5))}</span>
            </div>`;
        }).join('');
        return `<div class="check-row">
            <div class="check-row-label" style="color:${escHtml(svc.color)};width:auto;max-width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(svc.name)}">${escHtml(svc.name)}</div>
            <div class="check-circles">${circles}</div>
        </div>`;
    }).join('');
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
