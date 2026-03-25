async function loadUsers() {
    try {
        const res   = await fetch('/api/users');
        const users = await res.json();
        const tbody = document.getElementById('users-tbody');

        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4"><div class="empty-state">No accounts configured.</div></td></tr>';
            return;
        }

        tbody.innerHTML = users.map((u, i) => `
            <tr>
                <td class="user-mono" style="color:var(--muted)">${i + 1}</td>
                <td class="user-mono">${escHtml(u.username)}</td>
                <td class="user-mono">${escHtml(u.password)}</td>
                <td>
                    <div class="actions-cell">
                        <button class="btn btn-ghost btn-sm" onclick="openEditModal(${u.id}, '${escHtml(u.username)}')">
                            Change Password
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id}, '${escHtml(u.username)}')">
                            Remove
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load users', e);
    }
}

window.addEventListener('DOMContentLoaded', loadUsers);

function openAddModal() {
    document.getElementById('modal-title').textContent       = 'Add Account';
    document.getElementById('modal-uid').value              = '';
    document.getElementById('modal-username').value         = '';
    document.getElementById('modal-password').value         = '';
    document.getElementById('username-group').style.display = '';
    document.getElementById('modal-submit').textContent     = 'Add';
    document.getElementById('modal').classList.add('open');
    document.getElementById('modal-username').focus();
}

function openEditModal(uid, username) {
    document.getElementById('modal-title').textContent       = `Change Password — ${username}`;
    document.getElementById('modal-uid').value              = uid;
    document.getElementById('modal-password').value         = '';
    document.getElementById('username-group').style.display = 'none';
    document.getElementById('modal-submit').textContent     = 'Update';
    document.getElementById('modal').classList.add('open');
    document.getElementById('modal-password').focus();
}

function closeModal() {
    document.getElementById('modal').classList.remove('open');
}

window.addEventListener('DOMContentLoaded', () => {
    document.getElementById('modal').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeModal();
    });
});

async function submitModal() {
    const uid      = document.getElementById('modal-uid').value;
    const username = document.getElementById('modal-username').value.trim();
    const password = document.getElementById('modal-password').value.trim();

    if (!password) { toast('Password cannot be empty.', 'error'); return; }

    try {
        let res;
        if (uid) {
            res = await fetch(`/api/users/${uid}`, {
                method:  'PUT',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ password })
            });
        } else {
            if (!username) { toast('Username cannot be empty.', 'error'); return; }
            res = await fetch('/api/users', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ username, password })
            });
        }

        const data = await res.json();
        if (!res.ok) { toast(data.error || 'Request failed.', 'error'); return; }

        toast(uid ? 'Password updated.' : 'Account added.', 'success');
        closeModal();
        loadUsers();
    } catch (e) {
        toast('Network error.', 'error');
    }
}

async function deleteUser(uid, username) {
    if (!confirm(`Remove account "${username}"?`)) return;
    try {
        const res  = await fetch(`/api/users/${uid}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) { toast(data.error || 'Failed to remove.', 'error'); return; }
        toast(`"${username}" removed.`, 'success');
        loadUsers();
    } catch (e) {
        toast('Network error.', 'error');
    }
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
    if (e.key === 'Enter' && document.getElementById('modal').classList.contains('open')) submitModal();
});
