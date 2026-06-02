/* Nexus-Debug Dashboard — Application + Animations */
const API_BASE = '';

// ─── State ─────────────────────────────────────────────────────────────────
let state = {
    tasks: [],
    health: null,
    chartBugs: null,
    chartPriority: null,
    chartStatus: null,
    chartVersion: null,
    chartFixTime: null,
    animating: false,
};

// ─── API Calls ──────────────────────────────────────────────────────────────
async function apiGet(path) {
    const resp = await fetch(`${API_BASE}${path}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
    return resp.json();
}

async function loadHealth() {
    try {
        state.health = await apiGet('/health');
        const dot = document.getElementById('status-dot');
        const txt = document.getElementById('status-text');
        dot.className = 'status-dot online';
        txt.textContent = `🧬 ${state.health.llm?.provider || '?'} • ${state.health.version}`;
        return true;
    } catch (e) {
        document.getElementById('status-dot').className = 'status-dot offline';
        document.getElementById('status-text').textContent = '❌ Hors ligne';
        return false;
    }
}

async function loadTasks() {
    try {
        const statusFilter = document.getElementById('filter-status')?.value || '';
        const priorityFilter = document.getElementById('filter-priority')?.value || '';
        const versionFilter = document.getElementById('filter-version')?.value?.toLowerCase() || '';

        const data = await apiGet('/tasks?limit=100');
        let tasks = data.tasks || [];

        if (statusFilter) tasks = tasks.filter(t => t.status === statusFilter);
        if (priorityFilter) tasks = tasks.filter(t => t.priority === priorityFilter);
        if (versionFilter) {
            tasks = tasks.filter(t => {
                const v = (t.result?.version || '').toLowerCase();
                const b = (t.brief || '').toLowerCase();
                return v.includes(versionFilter) || b.includes(versionFilter);
            });
        }

        state.tasks = tasks;
        return tasks;
    } catch (e) {
        console.error('loadTasks error:', e);
        state.tasks = [];
        return [];
    }
}

// ─── Counter Animation ─────────────────────────────────────────────────────
function animateCounter(el, target, duration = 800) {
    if (!el) return;
    const start = performance.now();
    const from = 0;

    function update(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(from + (target - from) * eased);
        el.textContent = target > 0 && !el.dataset.isPercent ? current : (current + '%');
        if (target === current && progress >= 1) {
            el.textContent = target;
            if (el.dataset.isPercent) el.textContent = target + '%';
            // Count pulse
            el.style.animation = 'none';
            el.offsetHeight; // reflow
            el.style.animation = 'countPulse 0.4s ease forwards';
        }
        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }
    requestAnimationFrame(update);
}

// ─── Staggered Entrance ────────────────────────────────────────────────────
function applyStagger() {
    const staggerEls = document.querySelectorAll('.stagger');
    staggerEls.forEach((el, i) => {
        const delay = 0.15 + (parseInt(el.dataset.index || i) * 0.08);
        el.style.animationDelay = `${delay}s`;
        el.classList.add('animate-fade-up');
    });
}

// ─── Skeleton Loading ──────────────────────────────────────────────────────
function showSkeleton(container, type = 'rows', count = 5) {
    const el = typeof container === 'string' ? document.getElementById(container) : container;
    if (!el) return;
    if (type === 'rows') {
        el.innerHTML = Array(count).fill(0).map(() => 
            '<div class="skeleton skeleton-row"></div>'
        ).join('');
    } else {
        el.innerHTML = Array(count).fill(0).map(() => 
            '<div class="skeleton skeleton-card"></div>'
        ).join('');
    }
}

// ─── Stats with Counter ────────────────────────────────────────────────────
function updateStats(tasks) {
    const total = tasks.length;
    const fixed = tasks.filter(t => t.status === 'termine').length;
    const open = tasks.filter(t => t.status === 'en_attente' || t.status === 'en_cours').length;
    const rate = total > 0 ? Math.round((fixed / total) * 100) : 0;

    const totalEl = document.getElementById('stat-total');
    const fixedEl = document.getElementById('stat-fixed');
    const rateEl = document.getElementById('stat-rate');
    const openEl = document.getElementById('stat-open');

    animateCounter(totalEl, total);
    animateCounter(fixedEl, fixed);
    rateEl.dataset.isPercent = '1';
    animateCounter(rateEl, rate);
    animateCounter(openEl, open);

    const rateCard = rateEl.parentElement;
    rateCard.className = `stat-card ${rate >= 70 ? 'success' : rate >= 40 ? 'warning' : 'danger'}`;

    // Bordure animée conditionnelle
    if (rate >= 70) {
        rateCard.style.setProperty('--card-accent', 'var(--accent-cyan)');
    } else if (rate >= 40) {
        rateCard.style.setProperty('--card-accent', 'var(--accent-warm)');
    } else {
        rateCard.style.setProperty('--card-accent', '#ff4444');
    }
}

// ─── Charts ─────────────────────────────────────────────────────────────────
function renderBugsChart(tasks) {
    const ctx = document.getElementById('chart-bugs').getContext('2d');
    if (state.chartBugs) { state.chartBugs.destroy(); }

    const days = {};
    for (let i = 6; i >= 0; i--) {
        const d = new Date(Date.now() - i * 86400000);
        const key = d.toISOString().split('T')[0];
        days[key] = { submitted: 0, fixed: 0 };
    }

    tasks.forEach(t => {
        const created = t.created_at?.split('T')[0];
        if (created && days[created]) days[created].submitted++;
        if (t.status === 'termine') {
            const completed = t.completed_at?.split('T')[0];
            if (completed && days[completed]) days[completed].fixed++;
        }
    });

    const labels = Object.keys(days);
    state.chartBugs = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels.map(d => d.slice(5)),
            datasets: [
                { 
                    label: 'Soumis', 
                    data: Object.values(days).map(d => d.submitted), 
                    borderColor: '#139ce5', 
                    backgroundColor: 'rgba(19, 156, 229, 0.05)',
                    tension: 0.4, 
                    fill: true,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    borderWidth: 2,
                },
                { 
                    label: 'Résolus', 
                    data: Object.values(days).map(d => d.fixed), 
                    borderColor: '#0de7ff', 
                    backgroundColor: 'rgba(13, 231, 255, 0.05)',
                    tension: 0.4, 
                    fill: true,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    borderWidth: 2,
                },
            ]
        },
        options: {
            responsive: true,
            animation: {
                duration: 1000,
                easing: 'easeOutQuart',
            },
            plugins: { 
                legend: { 
                    labels: { color: 'rgba(255,255,255,0.5)', font: { family: 'Inter Tight' } } 
                } 
            },
            scales: {
                x: { 
                    ticks: { color: 'rgba(255,255,255,0.3)', font: { family: 'Inter Tight' } }, 
                    grid: { color: 'rgba(255,255,255,0.03)' } 
                },
                y: { 
                    ticks: { color: 'rgba(255,255,255,0.3)', font: { family: 'Inter Tight' } }, 
                    grid: { color: 'rgba(255,255,255,0.03)' }, 
                    beginAtZero: true 
                },
            }
        }
    });
}

function renderAnalyticsCharts(tasks) {
    // Priority chart
    const prioCtx = document.getElementById('chart-priority');
    if (prioCtx) {
        if (state.chartPriority) state.chartPriority.destroy();
        const counts = {};
        tasks.forEach(t => { counts[t.priority || 'P2'] = (counts[t.priority || 'P2'] || 0) + 1; });
        const colors = { P0: '#ef5350', P1: '#ffa726', P2: '#139ce5', P3: '#6b7280' };
        state.chartPriority = new Chart(prioCtx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: Object.keys(counts),
                datasets: [{ 
                    data: Object.values(counts), 
                    backgroundColor: Object.keys(counts).map(k => colors[k] || '#139ce5'),
                    borderColor: 'rgba(8,8,7,0.5)',
                    borderWidth: 2,
                }]
            },
            options: { 
                responsive: true,
                animation: { duration: 800, easing: 'easeOutQuart' },
                plugins: { 
                    legend: { labels: { color: 'rgba(255,255,255,0.5)', font: { family: 'Inter Tight' } } } 
                } 
            }
        });
    }

    // Status chart
    const statusCtx = document.getElementById('chart-status');
    if (statusCtx) {
        if (state.chartStatus) state.chartStatus.destroy();
        const counts = { en_attente: 0, en_cours: 0, termine: 0, erreur: 0, awaiting_approval: 0 };
        tasks.forEach(t => { if (counts[t.status] !== undefined) counts[t.status]++; });
        const colors = { en_attente: '#ffa726', en_cours: '#139ce5', termine: '#0de7ff', erreur: '#ef5350', awaiting_approval: '#a78bfa' };
        state.chartStatus = new Chart(statusCtx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: Object.keys(counts).filter(k => counts[k] > 0),
                datasets: [{ 
                    data: Object.keys(counts).filter(k => counts[k] > 0).map(k => counts[k]), 
                    backgroundColor: Object.keys(counts).filter(k => counts[k] > 0).map(k => colors[k]),
                    borderColor: 'rgba(8,8,7,0.5)',
                    borderWidth: 2,
                }]
            },
            options: { 
                responsive: true,
                animation: { duration: 800, easing: 'easeOutQuart' },
                plugins: { 
                    legend: { labels: { color: 'rgba(255,255,255,0.5)', font: { family: 'Inter Tight' } } } 
                } 
            }
        });
    }

    // By version chart
    const verCtx = document.getElementById('chart-by-version');
    if (verCtx) {
        if (state.chartVersion) state.chartVersion.destroy();
        const versions = {};
        tasks.forEach(t => {
            const v = t.result?.version || 'unknown';
            versions[v] = (versions[v] || 0) + 1;
        });
        const sorted = Object.entries(versions).sort((a, b) => b[1] - a[1]).slice(0, 8);
        state.chartVersion = new Chart(verCtx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: sorted.map(s => s[0]),
                datasets: [{ 
                    label: 'Bugs', 
                    data: sorted.map(s => s[1]), 
                    backgroundColor: 'rgba(19, 156, 229, 0.7)',
                    borderRadius: 4,
                    borderSkipped: false,
                }]
            },
            options: {
                responsive: true,
                animation: { duration: 800, easing: 'easeOutQuart' },
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: 'rgba(255,255,255,0.3)', font: { family: 'Inter Tight' } } },
                    y: { ticks: { color: 'rgba(255,255,255,0.3)', font: { family: 'Inter Tight' } }, beginAtZero: true }
                }
            }
        });
    }

    // Fix time chart
    const ftCtx = document.getElementById('chart-fix-time');
    if (ftCtx) {
        if (state.chartFixTime) state.chartFixTime.destroy();
        const fixed = tasks.filter(t => t.status === 'termine' && t.created_at && t.completed_at);
        const times = fixed.map(t => {
            const created = new Date(t.created_at).getTime();
            const completed = new Date(t.completed_at).getTime();
            return Math.round((completed - created) / 60000);
        }).filter(t => t > 0 && t < 1440);

        if (times.length > 0) {
            const avg = Math.round(times.reduce((a, b) => a + b, 0) / times.length);
            state.chartFixTime = new Chart(ftCtx.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: ['Moyen', 'Min', 'Max'],
                    datasets: [{
                        label: 'Temps de résolution (min)',
                        data: [avg, Math.min(...times), Math.max(...times)],
                        backgroundColor: ['rgba(13, 231, 255, 0.7)', 'rgba(19, 156, 229, 0.7)', 'rgba(239, 83, 80, 0.7)'],
                        borderRadius: 4,
                        borderSkipped: false,
                    }]
                },
                options: {
                    responsive: true,
                    animation: { duration: 800, easing: 'easeOutQuart' },
                    plugins: { legend: { display: false } },
                    scales: { 
                        y: { beginAtZero: true, ticks: { color: 'rgba(255,255,255,0.3)', font: { family: 'Inter Tight' } } }, 
                        x: { ticks: { color: 'rgba(255,255,255,0.3)', font: { family: 'Inter Tight' } } } 
                    }
                }
            });
        }
    }
}

// ─── Tables ─────────────────────────────────────────────────────────────────
function renderTaskTable(tasks, containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;

    if (tasks.length === 0) {
        el.innerHTML = '<div style="padding: 32px; text-align: center; color: var(--text-muted);">Aucun bug trouvé</div>';
        return;
    }

    let html = '<table class="table"><thead><tr><th>ID</th><th>Description</th><th>Priorité</th><th>Statut</th><th>Version</th><th>Date</th></tr></thead><tbody>';
    tasks.slice(0, 50).forEach((t, i) => {
        const desc = t.brief?.split('DESCRIPTION :')[1]?.trim()?.split('\n')[0]?.slice(0, 60) || t.brief?.slice(0, 60) || '—';
        const version = t.result?.version || '—';
        const date = t.created_at?.split('T')[0] || '—';
        html += `<tr onclick="showTaskDetail('${t.task_id}')" style="animation-delay: ${0.05 + i * 0.02}s">
            <td><code>${t.task_id}</code></td>
            <td>${desc}</td>
            <td><span class="badge badge-${t.priority || 'P2'}">${t.priority || 'P2'}</span></td>
            <td><span class="badge badge-${t.status}">${t.status}</span></td>
            <td>${version}</td>
            <td>${date}</td>
        </tr>`;
    });
    html += '</tbody></table>';
    el.innerHTML = html;
}

async function showTaskDetail(taskId) {
    try {
        const report = await apiGet(`/report/${taskId}`);
        const modal = document.getElementById('modal');
        const body = document.getElementById('modal-body');
        const r = report.result || {};

        let html = `<h2>Bug <code>${taskId}</code></h2>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:16px 0;">
            <div><strong>Statut:</strong> <span class="badge badge-${report.status}">${report.status}</span></div>
            <div><strong>Priorité:</strong> <span class="badge badge-${report.priority || 'P2'}">${report.priority || 'P2'}</span></div>
            <div><strong>Version:</strong> ${r.version || '—'}</div>
            <div><strong>Date:</strong> ${report.created_at?.split('T')[0] || '—'}</div>
        </div>`;

        if (r.root_cause) html += `<div class="setting-card"><h3>🔍 Cause racine</h3><p class="setting-value">${r.root_cause}</p></div>`;
        if (r.fix_summary) html += `<div class="setting-card"><h3>✅ Fix</h3><p class="setting-value">${r.fix_summary}</p></div>`;
        if (r.context && Object.keys(r.context).length > 0) {
            html += `<div class="setting-card"><h3>📦 Contexte</h3><pre style="font-size:12px;color:var(--text-secondary);overflow-x:auto;">${JSON.stringify(r.context, null, 2)}</pre></div>`;
        }
        if (r.breadcrumbs && r.breadcrumbs.length > 0) {
            html += `<div class="setting-card"><h3>🥖 Breadcrumbs (${r.breadcrumbs.length})</h3>`;
            r.breadcrumbs.slice(-10).forEach(b => {
                html += `<div style="font-size:12px;color:var(--text-secondary);padding:2px 0;">${b.action || b.event || JSON.stringify(b)}</div>`;
            });
            html += '</div>';
        }

        modal.classList.remove('hidden');
        body.innerHTML = html;
    } catch (e) {
        console.error('showTaskDetail error:', e);
    }
}

function closeModal(e) {
    if (e && e.target !== document.getElementById('modal')) return;
    document.getElementById('modal').classList.add('hidden');
}

// ─── Settings ────────────────────────────────────────────────────────────────
async function renderSettings() {
    const el = document.getElementById('settings-grid');
    if (!el || !state.health) return;

    const h = state.health;
    const cards = [
        { title: '🧬 Service', value: h.service, key: `Version ${h.version}` },
        { title: '🤖 LLM Actif', value: h.llm?.provider || '?', key: `Modèle: ${h.llm?.model || '?'}` },
        { title: '🔑 API Key', value: h.api_key_configured ? '✅ Configurée' : '❌ Manquante', key: 'Sécurité API' },
        { title: '📊 Base de connaissance', value: h.kb_stats || '—', key: 'KB' },
        { title: '🔗 Webhook GitHub', value: h.github_webhook ? '✅ Actif' : '⏸️ Inactif', key: 'GITHUB_SECRET' },
        { title: '💬 Slack Notifications', value: h.slack_webhook ? '✅ Actives' : '⏸️ Inactives', key: 'SLACK_WEBHOOK_URL' },
        { title: '📈 Prometheus', value: h.metrics_enabled ? '✅ Actif' : '❌ Inactif', key: '/metrics' },
        { title: '🕐 Dernière màj', value: h.timestamp ? new Date(h.timestamp).toLocaleString() : '—', key: 'Timestamp' },
    ];

    el.innerHTML = cards.map(c => `
        <div class="setting-card animate-fade-up stagger" data-index="${cards.indexOf(c)}">
            <h3>${c.title}</h3>
            <div class="setting-value">${c.value}</div>
            <div class="setting-key">${c.key}</div>
        </div>
    `).join('');
    applyStagger();
}

// ─── Nav Indicator Slide ────────────────────────────────────────────────────
function updateNavIndicator(activeItem) {
    const indicator = document.getElementById('nav-indicator');
    if (!indicator || !activeItem) return;

    const navItems = document.querySelector('.nav-items');
    const itemRect = activeItem.getBoundingClientRect();
    const navRect = navItems.getBoundingClientRect();

    indicator.style.top = (itemRect.top - navRect.top) + 'px';
    indicator.style.height = itemRect.height + 'px';
}

// ─── Ripple Effect ──────────────────────────────────────────────────────────
function addRippleEffect(e) {
    const btn = e.currentTarget;
    const rect = btn.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const ripple = document.createElement('span');
    ripple.className = 'ripple-effect';
    ripple.style.left = x + 'px';
    ripple.style.top = y + 'px';

    btn.appendChild(ripple);
    setTimeout(() => ripple.remove(), 600);
}

// ─── Navigation ──────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', function(e) {
        e.preventDefault();
        if (state.animating) return;

        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        this.classList.add('active');
        updateNavIndicator(this);

        const viewId = `view-${this.dataset.view}`;
        const currentView = document.querySelector('.view.active');
        const newView = document.getElementById(viewId);

        if (currentView === newView) return;

        state.animating = true;

        // Exit current view
        currentView.style.animation = 'viewExit 0.2s ease forwards';
        setTimeout(() => {
            currentView.classList.remove('active');
            currentView.style.animation = '';

            // Enter new view
            newView.classList.add('active');
            newView.style.animation = 'none';
            newView.offsetHeight; // reflow
            newView.style.animation = 'viewEnter 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards';

            if (this.dataset.view === 'analytics') {
                renderAnalyticsCharts(state.tasks);
            }
            if (this.dataset.view === 'settings') {
                renderSettings();
            }

            state.animating = false;
        }, 200);
    });
});

// ─── Init ───────────────────────────────────────────────────────────────────
async function refreshAll() {
    // Show skeleton while loading
    showSkeleton('recent-table', 'rows', 5);
    showSkeleton('tasks-table', 'rows', 8);

    const online = await loadHealth();
    const tasks = await loadTasks();
    if (online) {
        updateStats(tasks);
        renderBugsChart(tasks);
        renderTaskTable(tasks, 'recent-table');
        renderTaskTable(tasks, 'tasks-table');
        renderSettings();
        renderAnalyticsCharts(tasks);
    }
}

// ─── Init on Load ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Stagger entrance
    applyStagger();

    // Set initial nav indicator
    const activeNav = document.querySelector('.nav-item.active');
    if (activeNav) updateNavIndicator(activeNav);

    // Ripple on all ripple buttons
    document.querySelectorAll('.ripple-btn').forEach(btn => {
        btn.addEventListener('click', addRippleEffect);
    });

    // Load data
    refreshAll();
});

// Auto-refresh toutes les 30s
setInterval(refreshAll, 30000);
