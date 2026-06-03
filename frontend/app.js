/* Nexus Hub Dashboard — Client Portal */
const API_BASE = '';

// ─── State ───────────────────────────────────────────────────
let state = {
    clientId: sessionStorage.getItem('nexus_client_id') || '',
    email: sessionStorage.getItem('nexus_email') || '',
    project: sessionStorage.getItem('nexus_project') || '',
    plan: sessionStorage.getItem('nexus_plan') || '',
    apiKey: sessionStorage.getItem('nexus_api_key') || '',
};

// ─── Router ───────────────────────────────────────────────────
function showPage() {
    if (state.clientId) {
        document.getElementById('login-page').style.display = 'none';
        document.getElementById('app-page').classList.add('active');
        document.getElementById('nav-client-email').textContent = state.email;
        loadDashboard();
    } else {
        document.getElementById('login-page').style.display = 'flex';
        document.getElementById('app-page').classList.remove('active');
    }
}

// ─── Login / Register ─────────────────────────────────────────
function showRegister() {
    document.getElementById('login-form').style.display = 'none';
    document.getElementById('register-form').style.display = 'block';
    hideMsg();
}
function showLogin() {
    document.getElementById('login-form').style.display = 'block';
    document.getElementById('register-form').style.display = 'none';
    hideMsg();
}
function hideMsg() {
    document.getElementById('login-error').style.display = 'none';
    document.getElementById('login-success').style.display = 'none';
}

async function doLogin() {
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    if (!email || !password) return showError('Email et mot de passe requis');

    try {
        const resp = await fetch(API_BASE + '/hub/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await resp.json();
        if (!resp.ok) return showError(data.detail || 'Erreur de connexion');

        // Save session
        state.clientId = data.client_id;
        state.email = data.email;
        state.project = data.project || '';
        state.plan = data.plan || '';
        state.apiKey = data.api_key || '';
        sessionStorage.setItem('nexus_client_id', state.clientId);
        sessionStorage.setItem('nexus_email', state.email);
        sessionStorage.setItem('nexus_project', state.project);
        sessionStorage.setItem('nexus_plan', state.plan);
        if (state.apiKey) sessionStorage.setItem('nexus_api_key', state.apiKey);

        showPage();
    } catch (e) {
        showError('Erreur réseau: ' + e.message);
    }
}

async function doRegister() {
    const email = document.getElementById('reg-email').value.trim();
    const project = document.getElementById('reg-project').value.trim();
    const password = document.getElementById('reg-password').value;
    const confirm = document.getElementById('reg-confirm').value;
    if (!email || !password) return showError('Email et mot de passe requis');
    if (password !== confirm) return showError('Les mots de passe ne correspondent pas');
    if (password.length < 6) return showError('Mot de passe trop court (min 6)');

    try {
        const resp = await fetch(API_BASE + '/hub/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, project }),
        });
        const data = await resp.json();
        if (!resp.ok) return showError(data.error || data.detail || 'Erreur inscription');

        // Auto-login after register
        state.clientId = data.client_id;
        state.apiKey = data.api_key;
        state.email = email;
        state.project = project;
        sessionStorage.setItem('nexus_client_id', state.clientId);
        sessionStorage.setItem('nexus_email', state.email);
        sessionStorage.setItem('nexus_project', state.project);
        sessionStorage.setItem('nexus_api_key', state.apiKey);
        showPage();
    } catch (e) {
        showError('Erreur réseau: ' + e.message);
    }
}

function showError(msg) {
    const el = document.getElementById('login-error');
    el.textContent = msg;
    el.style.display = 'block';
}

function doLogout() {
    state.clientId = '';
    sessionStorage.clear();
    showPage();
}

// ─── View Switching ───────────────────────────────────────────
function switchView(name, el) {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    el.classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-' + name).classList.add('active');

    if (name === 'dashboard') loadDashboard();
    if (name === 'captures') loadCaptures();
    if (name === 'notifications') loadNotifications();
    if (name === 'profile') loadProfile();
}

// ─── Dashboard ────────────────────────────────────────────────
async function loadDashboard() {
    document.getElementById('dashboard-project').textContent = state.project ? `📦 ${state.project}` : '';
    try {
        const resp = await fetch(API_BASE + `/hub/${state.clientId}/stats`);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const stats = await resp.json();
        document.getElementById('stat-total').textContent = stats.total || 0;
        document.getElementById('stat-resolved').textContent = stats.resolved || 0;
        document.getElementById('stat-open').textContent = stats.open || 0;
        document.getElementById('stat-rate').textContent = (stats.rate || 0) + '%';
    } catch (e) {
        document.getElementById('stat-total').textContent = '?';
    }

    try {
        const resp = await fetch(API_BASE + `/hub/${state.clientId}/captures?limit=10`);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        renderCaptureTable(data.captures || [], 'recent-captures', true);
    } catch (e) {
        document.getElementById('recent-captures').innerHTML = '<div class="empty-state">Impossible de charger les captures</div>';
    }
}

// ─── Captures ─────────────────────────────────────────────────
async function loadCaptures() {
    const el = document.getElementById('captures-table');
    el.innerHTML = '<div class="empty-state">Chargement...</div>';
    try {
        const resp = await fetch(API_BASE + `/hub/${state.clientId}/captures?limit=100`);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        renderCaptureTable(data.captures || [], 'captures-table', false);
    } catch (e) {
        el.innerHTML = '<div class="empty-state">Impossible de charger les captures</div>';
    }
}

function renderCaptureTable(captures, containerId, recent) {
    const el = document.getElementById(containerId);
    if (!captures.length) {
        el.innerHTML = '<div class="empty-state">🎉 Aucune erreur capturée pour le moment</div>';
        return;
    }
    let html = '<table class="table"><thead><tr>' +
        '<th>ID</th><th>Type</th><th>Message</th><th>URL</th>' + (recent ? '' : '<th>Status</th>') + '<th>Date</th>' +
        '</tr></thead><tbody>';
    captures.forEach(c => {
        const statusClass = c.nexus_status === 'fixed' ? 'badge-fixed' : (c.resolved ? 'badge-resolved' : 'badge-pending');
        const statusLabel = c.nexus_status === 'fixed' ? '✅ Fixé' : (c.resolved ? '✅ Résolu' : '⏳ En attente');
        const date = (c.created_at || '').split('T')[0] || '—';
        const url = (c.url || '').length > 40 ? (c.url || '').slice(0, 40) + '…' : (c.url || '—');
        html += `<tr onclick="showCaptureDetail(${c.id})">
            <td><code>#${c.id}</code></td>
            <td><span class="badge badge-error">${c.error_type || '?'}</span></td>
            <td>${(c.error_message || '').slice(0, 50)}</td>
            <td style="font-size:11px;color:var(--text-muted)">${url}</td>` +
            (recent ? '' : `<td><span class="${statusClass}">${statusLabel}</span></td>`) +
            `<td style="font-size:11px;color:var(--text-muted)">${date}</td>
        </tr>`;
    });
    html += '</tbody></table>';
    el.innerHTML = html;
}

// ─── Capture Detail ───────────────────────────────────────────
async function showCaptureDetail(captureId) {
    const modal = document.getElementById('modal');
    const body = document.getElementById('modal-body');
    body.innerHTML = '<div class="empty-state">Chargement...</div>';
    modal.classList.remove('hidden');

    try {
        const resp = await fetch(API_BASE + `/hub/${state.clientId}/captures/${captureId}`);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        const c = data.capture || {};

        let html = `
            <span class="modal-close" onclick="closeModal()">&times;</span>
            <h2 style="margin-bottom:16px;">🐛 Capture #${c.id}</h2>
            <div class="detail-card">
                <h3>Erreur</h3>
                <p style="color:var(--text-secondary);font-size:14px;">
                    <span class="badge badge-error">${c.error_type || '?'}</span>
                    ${(c.error_message || '').slice(0, 200)}
                </p>
            </div>
            <div class="meta-grid">
                <div class="meta-item"><div class="label">URL</div><div class="value">${c.url || '—'}</div></div>
                <div class="meta-item"><div class="label">Status</div><div class="value">${c.status_code || '—'}</div></div>
                <div class="meta-item"><div class="label">Version</div><div class="value">${c.version || '—'}</div></div>
                <div class="meta-item"><div class="label">Environment</div><div class="value">${c.environment || '—'}</div></div>
                <div class="meta-item"><div class="label">Date</div><div class="value">${(c.created_at || '').split('T')[0] || '—'}</div></div>
                <div class="meta-item"><div class="label">Nexus Status</div><div class="value">${c.nexus_status || 'pending'}</div></div>
            </div>`;

        // Stack trace
        if (c.stack_trace) {
            html += `<div class="detail-card">
                <h3>📜 Stack trace</h3>
                <pre>${escapeHtml(c.stack_trace)}</pre>
            </div>`;
        }

        // AI Report button
        html += `<div class="detail-card">
            <h3>🤖 Diagnostic IA</h3>
            <button class="btn btn-sm btn-primary" onclick="generateReport(${c.id})">Générer le rapport</button>
            <div id="ai-report-${c.id}" style="margin-top:12px;font-size:13px;color:var(--text-secondary);"></div>
        </div>`;

        body.innerHTML = html;
    } catch (e) {
        body.innerHTML = `<div class="empty-state">Erreur: ${e.message}</div>`;
    }
}

async function generateReport(captureId) {
    const el = document.getElementById('ai-report-' + captureId);
    el.textContent = '⏳ Génération du rapport...';
    try {
        const resp = await fetch(API_BASE + `/hub/${state.clientId}/captures/${captureId}/report`, {
            method: 'POST',
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        el.innerHTML = `<pre style="font-size:13px;line-height:1.6;white-space:pre-wrap;color:#6bc9a0;">${escapeHtml(data.report || 'Pas de rapport')}</pre>`;
    } catch (e) {
        el.innerHTML = `<span style="color:#ff6666;">Erreur: ${e.message}</span>`;
    }
}

function closeModal() {
    document.getElementById('modal').classList.add('hidden');
}

// ─── Notifications ────────────────────────────────────────────
async function loadNotifications() {
    try {
        const resp = await fetch(API_BASE + `/hub/${state.clientId}/notifications`);
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.telegram_chat) {
            document.getElementById('notif-telegram').value = data.telegram_chat;
        }
    } catch (e) {}
}

async function saveNotifications() {
    const telegram = document.getElementById('notif-telegram').value.trim();
    const status = document.getElementById('notif-status');
    try {
        const resp = await fetch(API_BASE + `/hub/${state.clientId}/notifications`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                telegram_chat: telegram,
                whatsapp_phone: '',
                slack_webhook: '',
            }),
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        status.textContent = '✅ Notifications enregistrées !';
        status.style.color = '#6bc9a0';
    } catch (e) {
        status.textContent = '❌ Erreur: ' + e.message;
        status.style.color = '#ff6666';
    }
}

// ─── Profile ──────────────────────────────────────────────────
async function loadProfile() {
    document.getElementById('profile-id').textContent = state.clientId;
    document.getElementById('profile-email').textContent = state.email;
    document.getElementById('profile-project').textContent = state.project || '—';
    document.getElementById('profile-plan').textContent = state.plan || 'starter';
    document.getElementById('profile-created').textContent = '—';

    // API key
    if (state.apiKey) {
        document.getElementById('profile-api-key').textContent = state.apiKey;
        document.getElementById('show-key-btn').textContent = '👁️‍🗨️';
    }

    // .env example
    document.getElementById('env-example').textContent =
        `# watch-py configuration\n` +
        `WATCH_API_KEY=${state.apiKey || 'sk-watch-votre-clé'}\n` +
        `WATCH_HUB_URL=http://100.70.168.107:9000/hub\n` +
        `WATCH_PROJECT=${state.project || 'mon-projet'}\n` +
        `WATCH_ENVIRONMENT=production\n` +
        `WATCH_VERSION=1.0.0`;

    try {
        const resp = await fetch(API_BASE + `/hub/${state.clientId}/profile`);
        if (resp.ok) {
            const data = await resp.json();
            document.getElementById('profile-created').textContent = (data.created_at || '').split('T')[0] || '—';
        }
    } catch (e) {}
}

async function showApiKey() {
    if (state.apiKey) {
        document.getElementById('profile-api-key').textContent = state.apiKey;
        document.getElementById('show-key-btn').textContent = '👁️‍🗨️';
        return;
    }
    // Fetch from API if not in session
    // For now, show placeholder
    document.getElementById('profile-api-key').textContent = 'sk-watch-... (rechargez)';
}

// ─── Utilities ────────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ─── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    showPage();
});
