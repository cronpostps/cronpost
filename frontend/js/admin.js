// /frontend/js/admin.js
// version 1.6 (OTP PIN Modal Integration)
// - Replaced all `prompt()` calls with the new reusable `requestPinVerification()` modal.
// - Removed logic for the old PIN prompt modal.

console.log("--- admin.js SCRIPT STARTED (v1.6) ---");

document.addEventListener('DOMContentLoaded', () => {
    const accessToken = localStorage.getItem('accessToken');
    if (!accessToken) {
        window.location.href = '/signin?status=session_expired';
        return;
    }

    // --- STATE MANAGEMENT ---
    let adminState = {
        users: {
            list: [],
            totalCount: 0,
            currentPage: 1,
            limit: 10,
            search: '',
            sortBy: 'created_at',
            sortDir: 'desc'
        }
    };

    // --- DOM Elements ---
    const mainContent = document.getElementById('main-content');
    const adminStatusMessage = document.getElementById('adminStatusMessage');
    const settingsTableBody = document.getElementById('settingsTableBody');
    const usersTableBody = document.getElementById('usersTableBody');
    const userSearchForm = document.getElementById('userSearchForm');
    const userSearchInput = document.getElementById('userSearchInput');
    const userSearchReset = document.getElementById('userSearchReset');
    const userTableHeader = document.querySelector('#users-panel thead');
    const userPagination = document.getElementById('userPagination');
    const userCountInfo = document.getElementById('userCountInfo');

    // --- Helper Functions ---
    function displayAdminMessage(message, isSuccess) {
        if (typeof displayGeneralFormMessage === "function") {
            displayGeneralFormMessage(adminStatusMessage, message, isSuccess);
        } else {
            alert(message);
        }
    }

    function formatDate(isoString) {
        if (!isoString) return 'N/A';
        const date = new Date(isoString);
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = String(date.getFullYear()).slice(-2);
        return `${day}/${month}/${year}`;
    }

    // --- RENDER FUNCTIONS ---
    function renderUsersTable() {
        if (!usersTableBody) return;
        usersTableBody.innerHTML = '';
        const users = adminState.users.list;
        if (users.length === 0) {
            usersTableBody.innerHTML = '<tr><td colspan="7" class="text-center">No users found.</td></tr>';
            return;
        }
        users.forEach(user => {
            const tr = document.createElement('tr');
            tr.id = `user-row-${user.id}`;
            const typeBadge = user.membership_type === 'premium' ? `<span class="badge bg-warning text-dark">Premium</span>` : `<span class="badge bg-secondary">Free</span>`;
            const statusBadges = { 'INS': '<span class="badge bg-light text-dark">Inactive</span>', 'ANS_CLC': '<span class="badge bg-success">Active (CLC)</span>', 'ANS_WCT': '<span class="badge bg-primary">Active (WCT)</span>', 'FNS': '<span class="badge bg-danger">Frozen</span>' };
            const statusBadge = statusBadges[user.account_status] || `<span class="badge bg-dark">${user.account_status}</span>`;
            let upgradeDowngradeButton = user.membership_type === 'premium' 
                ? `<button class="btn btn-outline-warning downgrade-btn" data-user-id="${user.id}" data-user-email="${user.email}">Downgrade</button>`
                : `<button class="btn btn-outline-success upgrade-btn" data-user-id="${user.id}" data-user-email="${user.email}">Upgrade</button>`;
            const actions = `<div class="btn-group btn-group-sm" role="group">${upgradeDowngradeButton}<button class="btn btn-outline-info reset-pin-btn" data-user-id="${user.id}" data-user-email="${user.email}">Reset PIN</button><button class="btn btn-outline-danger delete-btn" data-user-id="${user.id}" data-user-email="${user.email}">Delete</button></div>`;
            tr.innerHTML = `<td>${user.email}</td><td>${user.user_name || ''}</td><td>${typeBadge}</td><td>${statusBadge}</td><td>${formatDate(user.last_activity_at)}</td><td>${formatDate(user.created_at)}</td><td>${actions}</td>`;
            usersTableBody.appendChild(tr);
        });
    }

    function renderPagination() {
        if (!userPagination || !userCountInfo) return;
        const { totalCount, limit, currentPage } = adminState.users;
        const totalPages = Math.ceil(totalCount / limit);
        userCountInfo.textContent = `Showing ${adminState.users.list.length} of ${totalCount} users.`;
        userPagination.innerHTML = '';
        if (totalPages <= 1) return;
        const createPageLink = (page, text, isDisabled = false, isActive = false) => {
            const li = document.createElement('li');
            li.className = `page-item ${isDisabled ? 'disabled' : ''} ${isActive ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="#" data-page="${page}">${text}</a>`;
            return li;
        };
        userPagination.appendChild(createPageLink(currentPage - 1, 'Previous', currentPage === 1));
        for (let i = 1; i <= totalPages; i++) {
            userPagination.appendChild(createPageLink(i, i, false, i === currentPage));
        }
        userPagination.appendChild(createPageLink(currentPage + 1, 'Next', currentPage === totalPages));
    }

    // --- DATA FETCHING ---
    async function fetchAndDisplaySettings() {
        if (!settingsTableBody) return;
        settingsTableBody.innerHTML = '<tr><td colspan="4" class="text-center">Loading settings...</td></tr>';
        try {
            const response = await fetch('/api/admin/system-settings', { headers: { 'Authorization': `Bearer ${accessToken}` } });
            if (!response.ok) throw new Error((await response.json()).detail || 'Failed to fetch settings');
            const settings = await response.json();
            settingsTableBody.innerHTML = '';
            settings.forEach(setting => {
                const tr = document.createElement('tr');
                tr.innerHTML = `<td><code>${setting.setting_key}</code></td><td><input type="text" class="form-control form-control-sm" value="${setting.setting_value || ''}" id="setting-${setting.setting_key}"></td><td>${setting.description || ''}</td><td><button class="btn btn-sm btn-primary save-setting-btn" data-key="${setting.setting_key}">Save</button></td>`;
                settingsTableBody.appendChild(tr);
            });
        } catch (error) {
            settingsTableBody.innerHTML = `<tr><td colspan="4" class="text-center text-danger">Error: ${error.message}</td></tr>`;
        }
    }

    async function fetchAndDisplayUsers() {
        if (!usersTableBody) return;
        usersTableBody.innerHTML = '<tr><td colspan="7" class="text-center">Loading users...</td></tr>';
        const { limit, currentPage, search, sortBy, sortDir } = adminState.users;
        const skip = (currentPage - 1) * limit;
        const params = new URLSearchParams({ skip, limit, sort_by: sortBy, sort_dir: sortDir });
        if (search) params.append('search', search);
        try {
            const response = await fetch(`/api/admin/users?${params.toString()}`, { headers: { 'Authorization': `Bearer ${accessToken}` } });
            if (!response.ok) throw new Error((await response.json()).detail || 'Failed to fetch users');
            const data = await response.json();
            adminState.users.list = data.users;
            adminState.users.totalCount = data.total_count;
            renderUsersTable();
            renderPagination();
        } catch (error) {
            usersTableBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">Error: ${error.message}</td></tr>`;
        }
    }

    // --- EVENT HANDLERS ---
    async function handleSaveSetting(event) {
        const targetButton = event.target.closest('.save-setting-btn');
        if (!targetButton) return;
        
        const settingKey = targetButton.dataset.key;
        const inputEl = document.getElementById(`setting-${settingKey}`);
        const newValue = inputEl.value;

        try {
            const pin = await window.requestPinVerification(`To save changes for '${settingKey}', please confirm your Admin PIN:`);
            
            targetButton.disabled = true;
            targetButton.textContent = 'Saving...';

            const response = await fetch(`/api/admin/system-settings/${settingKey}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
                body: JSON.stringify({ value: newValue, admin_pin: pin })
            });
            if (!response.ok) throw new Error((await response.json()).detail || 'Failed to save setting.');
            
            displayAdminMessage(`Setting '${settingKey}' saved successfully.`, true);

        } catch (error) {
            // Check for cancellation string from promise rejection
            if (typeof error === 'string' && error.includes('closed')) return; 
            displayAdminMessage(`Error saving '${settingKey}': ${error}`, false);
        } finally {
            targetButton.disabled = false;
            targetButton.textContent = 'Save';
        }
    }
    
    async function handleUserAction(event) {
        const button = event.target.closest('button');
        if (!button) return;

        const userId = button.dataset.userId;
        const userEmail = button.dataset.userEmail;
        let action, url, method, confirmMessage;

        if (button.classList.contains('upgrade-btn')) { action = 'upgrade'; url = `/api/admin/users/${userId}/upgrade`; method = 'PUT'; } 
        else if (button.classList.contains('downgrade-btn')) { action = 'downgrade'; url = `/api/admin/users/${userId}/downgrade`; method = 'PUT'; } 
        else if (button.classList.contains('reset-pin-btn')) {
            if (!confirm(`Are you sure you want to reset the PIN for '${userEmail}'? This will remove their current PIN.`)) return;
            action = 'reset pin for'; url = `/api/admin/users/${userId}/reset-pin`; method = 'POST';
        } else if (button.classList.contains('delete-btn')) {
            if (!confirm(`Are you sure you want to PERMANENTLY DELETE user '${userEmail}'? This action cannot be undone.`)) return;
            action = 'delete'; url = `/api/admin/users/${userId}`; method = 'DELETE';
        } else { return; }

        try {
            const pin = await window.requestPinVerification(`To ${action} user '${userEmail}', please confirm your Admin PIN:`);
            
            button.disabled = true;
            button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>`;

            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
                body: JSON.stringify({ admin_pin: pin })
            });

            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.detail || `Failed to ${action} user.`);
            
            displayAdminMessage(result.message || `Action on ${userEmail} was successful.`, true);
            
            if (action === 'upgrade' || action === 'downgrade' || action === 'delete') {
                fetchAndDisplayUsers();
            } else {
                 button.disabled = false;
                 button.textContent = "Reset PIN";
            }
        } catch (error) {
            if (typeof error === 'string' && error.includes('closed')) return; 
            displayAdminMessage(`Error: ${error.message}`, false);
            button.disabled = false;
            // Restore original button text
            const originalText = action.split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
            button.textContent = originalText;
        }
    }
    
    // Existing event listeners
    if (userSearchForm) userSearchForm.addEventListener('submit', (e) => { e.preventDefault(); adminState.users.search = userSearchInput.value.trim(); adminState.users.currentPage = 1; fetchAndDisplayUsers(); });
    if (userSearchReset) userSearchReset.addEventListener('click', () => { userSearchInput.value = ''; adminState.users.search = ''; adminState.users.currentPage = 1; fetchAndDisplayUsers(); });
    if (userTableHeader) userTableHeader.addEventListener('click', (e) => { const h = e.target.closest('.sortable-header'); if (!h) return; const key = h.dataset.sortKey; if(adminState.users.sortBy === key){ adminState.users.sortDir = adminState.users.sortDir === 'asc' ? 'desc' : 'asc'; } else { adminState.users.sortBy = key; adminState.users.sortDir = 'desc'; } fetchAndDisplayUsers(); });
    if (userPagination) userPagination.addEventListener('click', (e) => { e.preventDefault(); const p = e.target.closest('.page-link'); if (p && !p.closest('.disabled') && !p.closest('.active')) { adminState.users.currentPage = parseInt(p.dataset.page, 10); fetchAndDisplayUsers(); } });
    if (settingsTableBody) settingsTableBody.addEventListener('click', handleSaveSetting);
    if (usersTableBody) usersTableBody.addEventListener('click', handleUserAction);

    // --- Initial Load Logic ---
    async function initializePage() {
        try {
            // First, ask for the PIN using the new modal
            const enteredPin = await window.requestPinVerification("Please enter your Admin PIN to access the dashboard.");
            
            // If PIN is provided, verify it with the backend
            const response = await fetch('/api/admin/verify-pin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
                body: JSON.stringify({ admin_pin: enteredPin })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'PIN verification failed.');
            }

            // If PIN is correct, show content and fetch data
            mainContent.style.display = 'block';
            await fetchAndDisplaySettings();
            await fetchAndDisplayUsers();
        
        } catch(error) {
            // If user cancels the modal or PIN is wrong, redirect them
            console.error("Authentication failed:", error);
            // Show a message on the sign-in page that access was denied
            window.location.href = '/signin?status=admin_auth_failed';
        }
    }
    
    initializePage();
});