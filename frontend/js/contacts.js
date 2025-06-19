// /frontend/js/contacts.js
// Version 4.1.0 - Improved UI/UX: Client-side validation and better error handling.

(function() {
    
    // --- DOM Elements ---
    const tableBody = document.getElementById('contact-list-table-body');
    const spinner = document.getElementById('contacts-loading-spinner');
    const mainAddContactBtn = document.getElementById('add-new-contact-btn');

    // Edit Modal Elements
    const editModalElement = document.getElementById('editContactModal');
    const editModal = bootstrap.Modal.getOrCreateInstance(editModalElement);
    const editContactNameInput = document.getElementById('editContactName');
    const editContactEmailInput = document.getElementById('editContactEmail');
    const editContactOriginalEmailHidden = document.getElementById('editContactOriginalEmail');
    const saveContactChangesBtn = document.getElementById('saveContactChangesBtn');
    
    // Add Modal Elements
    const addModalElement = document.getElementById('addContactModal');
    const addModal = bootstrap.Modal.getOrCreateInstance(addModalElement);
    const addContactForm = document.getElementById('addContactForm');
    const addContactEmailInput = document.getElementById('addContactEmail');
    const addContactNameInput = document.getElementById('addContactName');
    const addContactErrorDiv = document.getElementById('addContactError');
    const addContactModalBtn = document.getElementById('addContactBtnModal');

    // Block User Form Elements
    const showBlockFormBtn = document.getElementById('show-block-form-btn');
    const blockUserSection = document.getElementById('block-user-section');
    const blockEmailInput = document.getElementById('block-email-input');
    const blockEmailSubmitBtn = document.getElementById('block-email-submit-btn');
    const blockFormCancelBtn = document.getElementById('block-form-cancel-btn');
    const blockUserErrorDiv = document.getElementById('block-user-error');
    
    // Regular expression for basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    
    async function initializeContactsView() {
        if (!tableBody || !spinner) return;
        spinner.style.display = 'block';
        tableBody.innerHTML = '';
        try {
            const contacts = await fetchContacts();
            renderContactRows(contacts);
        } catch (error) {
            tableBody.innerHTML = `<tr><td colspan="3" class="text-center text-danger">Failed to load contacts. Please try again.</td></tr>`;
        } finally {
            spinner.style.display = 'none';
        }
        setupEventListeners();
    }

    function setupEventListeners() {
        if(mainAddContactBtn) mainAddContactBtn.addEventListener('click', handleOpenAddModal);
        if(saveContactChangesBtn) saveContactChangesBtn.addEventListener('click', handleSaveChanges);
        if(addContactModalBtn) addContactModalBtn.addEventListener('click', handleSaveNewContact);
        
        if(showBlockFormBtn) showBlockFormBtn.addEventListener('click', () => {
            blockUserSection.style.display = 'block';
            showBlockFormBtn.style.display = 'none';
        });
        if(blockFormCancelBtn) blockFormCancelBtn.addEventListener('click', () => {
            blockUserSection.style.display = 'none';
            showBlockFormBtn.style.display = 'inline-block';
            blockUserErrorDiv.style.display = 'none';
            blockEmailInput.value = '';
        });
        if(blockEmailSubmitBtn) blockEmailSubmitBtn.addEventListener('click', handleBlockByEmail);
    }

    async function fetchContacts() {
        const response = await fetchWithAuth('/api/users/contacts');
        if (!response.ok) throw new Error('Could not fetch contacts from API.');
        return await response.json();
    }

    function renderContactRows(contacts) {
        if (contacts.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="3" class="text-center text-muted">Your contact list is empty.</td></tr>`;
            return;
        }

        const rowsHtml = contacts.map(contact => {
            const blockButtonText = contact.is_blocked ? 'Unblock' : 'Block';
            const blockButtonAction = contact.is_blocked ? 'unblock' : 'block';
            const blockButtonClass = contact.is_blocked ? 'btn-success' : 'btn-danger';

            return `
            <tr data-contact-email="${escapeHtml(contact.contact_email)}" data-contact-name="${escapeHtml(contact.contact_name || '')}">
                <td>
                    <strong>${escapeHtml(contact.display_name)}</strong>
                    <br>
                    <small class="text-muted">${escapeHtml(contact.contact_email)}</small>
                </td>
                <td class="text-center">
                    ${contact.is_cronpost_user
                        ? '<span class="badge bg-success">CP User</span>'
                        : '<span class="badge bg-secondary">External</span>'
                    }
                    ${contact.is_blocked
                        ? '<span class="badge bg-danger ms-1">Blocked</span>'
                        : ''
                    }
                </td>
                <td class="text-center">
                    <button class="btn btn-outline-secondary btn-sm contact-action-btn" data-action="update">Update</button>
                    <button class="btn btn-outline-danger btn-sm contact-action-btn" data-action="delete">Delete</button>
                    <button class="btn ${blockButtonClass} btn-sm contact-action-btn" 
                            data-action="${blockButtonAction}"
                            ${!contact.is_cronpost_user ? 'disabled title="Only CronPost users can be blocked"' : ''}>
                        ${blockButtonText}
                    </button>
                </td>
            </tr>`;
        }).join('');

        tableBody.innerHTML = rowsHtml;
        tableBody.querySelectorAll('.contact-action-btn').forEach(btn => btn.addEventListener('click', handleContactActionClick));
    }
    
    function handleContactActionClick(event) {
        event.preventDefault();
        const target = event.currentTarget;
        const action = target.dataset.action;
        const contactRow = target.closest('tr');
        const email = contactRow.dataset.contactEmail;
        const name = contactRow.dataset.contactName;

        if (action === 'delete') {
            if (confirm(`Are you sure you want to delete the contact "${name || email}"?`)) {
                deleteContact(email, target);
            }
        } else if (action === 'update') {
            editContactOriginalEmailHidden.value = email;
            editContactEmailInput.value = email;
            editContactNameInput.value = name;
            editModal.show();
        } else if (action === 'block' || action === 'unblock') {
             blockOrUnblockContact(email, action, target);
        }
    }

    /**
     * {* MODIFIED: Improved error parsing *}
     */
    async function parseErrorMessage(response) {
        try {
            const errorData = await response.json();
            // FastAPI validation errors are nested in 'detail'
            if (Array.isArray(errorData.detail)) {
                return errorData.detail.map(e => e.msg).join(', ');
            }
            // Other FastAPI errors are often a string in 'detail'
            return errorData.detail || 'An unknown error occurred.';
        } catch (e) {
            return response.statusText || 'Failed to communicate with server.';
        }
    }
    
    async function blockOrUnblockContact(email, actionType, buttonElement) {
        if(buttonElement) buttonElement.disabled = true;

        const endpoint = `/api/users/${actionType}`;
        try {
            const response = await fetchWithAuth(endpoint, {
                method: 'POST',
                body: JSON.stringify({ blocked_user_email: email })
            });
            if (!response.ok) {
                const message = await parseErrorMessage(response);
                throw new Error(message);
            }
            await initializeContactsView();
            return { success: true, message: `User ${actionType}ed successfully.` };
        } catch (error) {
            if(buttonElement) buttonElement.disabled = false;
            // Now we return a clear string message instead of an error object
            return { success: false, message: error.message };
        }
    }
    
    async function handleBlockByEmail() {
        const email = blockEmailInput.value.trim();
        
        // {* NEW: Client-side email validation *}
        if (!emailRegex.test(email)) {
            blockUserErrorDiv.textContent = "Please enter a valid email address.";
            blockUserErrorDiv.style.display = 'block';
            return;
        }

        blockEmailSubmitBtn.disabled = true;
        blockEmailSubmitBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span>`;
        blockUserErrorDiv.style.display = 'none';

        const result = await blockOrUnblockContact(email, 'block', null);
        
        if (result.success) {
            blockFormCancelBtn.click();
        } else {
            // result.message is now a clean string
            blockUserErrorDiv.textContent = `Error: ${result.message}`;
            blockUserErrorDiv.style.display = 'block';
        }

        blockEmailSubmitBtn.disabled = false;
        blockEmailSubmitBtn.innerHTML = `Block`;
    }

    async function deleteContact(contactEmail, buttonElement) {
        buttonElement.disabled = true;
        try {
            const response = await fetchWithAuth('/api/users/contacts', {
                method: 'DELETE',
                body: JSON.stringify({ contact_email: contactEmail })
            });
            if (!response.ok) {
                const message = await parseErrorMessage(response);
                throw new Error(message);
            }
            buttonElement.closest('tr').remove();
        } catch (error) {
            alert(`Error: ${error.message}`);
            buttonElement.disabled = false;
        }
    }
    
    async function handleSaveChanges() {
        const originalEmail = editContactOriginalEmailHidden.value;
        const newName = editContactNameInput.value.trim();

        saveContactChangesBtn.disabled = true;
        saveContactChangesBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Saving...`;

        try {
            const response = await fetchWithAuth(`/api/users/contacts/${originalEmail}`, {
                method: 'PUT',
                body: JSON.stringify({ contact_name: newName })
            });
            if (!response.ok) {
                const message = await parseErrorMessage(response);
                throw new Error(message);
            }
            editModal.hide();
            await initializeContactsView();
        } catch(error) {
            alert(`Error: ${error.message}`);
        } finally {
            saveContactChangesBtn.disabled = false;
            saveContactChangesBtn.innerHTML = `Save Changes`;
        }
    }

    function handleOpenAddModal() {
        addContactForm.reset();
        addContactErrorDiv.style.display = 'none';
        addContactErrorDiv.textContent = '';
        addModal.show();
    }

    async function handleSaveNewContact() {
        const email = addContactEmailInput.value.trim();
        const name = addContactNameInput.value.trim();

        if (!emailRegex.test(email)) {
            addContactErrorDiv.textContent = 'Please enter a valid email address.';
            addContactErrorDiv.style.display = 'block';
            return;
        }

        addContactModalBtn.disabled = true;
        addContactModalBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Adding...`;
        addContactErrorDiv.style.display = 'none';

        try {
            const response = await fetchWithAuth('/api/users/contacts', {
                method: 'POST',
                body: JSON.stringify({ contact_email: email, contact_name: name || null })
            });
            if (!response.ok) {
                const message = await parseErrorMessage(response);
                throw new Error(message);
            }
            addModal.hide();
            await initializeContactsView();
        } catch(error) {
            addContactErrorDiv.textContent = `Error: ${error.message}`;
            addContactErrorDiv.style.display = 'block';
        } finally {
            addContactModalBtn.disabled = false;
            addContactModalBtn.innerHTML = `Add Contact`;
        }
    }

    function escapeHtml(str) {
        if (str === null || typeof str === 'undefined') return '';
        return str.toString().replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
    }

    initializeContactsView();

})();