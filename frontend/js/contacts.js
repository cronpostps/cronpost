// /frontend/js/contacts.js
// Version 2.0.0 - Logic for the standalone contacts management view (HTML Fragment).

// Sử dụng IIFE để gói gọn code và tự động chạy khi được tải
(function() {
    
    // --- DOM Elements ---
    const tableBody = document.getElementById('contact-list-table-body');
    const spinner = document.getElementById('contacts-loading-spinner');
    const addContactBtn = document.getElementById('add-new-contact-btn');

    // Edit Modal Elements
    const editModalElement = document.getElementById('editContactModal');
    const editModal = bootstrap.Modal.getOrCreateInstance(editModalElement);
    const editContactNameInput = document.getElementById('editContactName');
    const editContactEmailInput = document.getElementById('editContactEmail');
    const editContactOriginalEmailHidden = document.getElementById('editContactOriginalEmail');
    const saveContactChangesBtn = document.getElementById('saveContactChangesBtn');

    
    /**
     * Hàm chính để khởi tạo trang danh bạ
     */
    async function initializeContactsView() {
        if (!tableBody || !spinner) {
            console.error("Contacts view is missing required elements.");
            return;
        }

        spinner.style.display = 'block';
        tableBody.innerHTML = '';

        try {
            const contacts = await fetchContacts();
            renderContactRows(contacts);
        } catch (error) {
            tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-danger">Failed to load contacts.</td></tr>`;
        } finally {
            spinner.style.display = 'none';
        }
        
        // Gắn sự kiện cho các nút
        if(addContactBtn) addContactBtn.addEventListener('click', handleAddNewContact);
        if(saveContactChangesBtn) saveContactChangesBtn.addEventListener('click', handleSaveChanges);
    }

    /**
     * Lấy danh sách liên hệ từ API
     */
    async function fetchContacts() {
        const response = await fetchWithAuth('/api/users/contacts');
        if (!response.ok) {
            throw new Error('Could not fetch contacts from API.');
        }
        return await response.json();
    }

    /**
     * "Vẽ" các hàng dữ liệu liên hệ vào bảng
     */
    function renderContactRows(contacts) {
        if (contacts.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">Your contact list is empty.</td></tr>`;
            return;
        }

        const rowsHtml = contacts.map(contact => `
            <tr data-contact-email="${escapeHtml(contact.contact_email)}" data-contact-name="${escapeHtml(contact.contact_name || '')}" data-is-cronpost-user="${contact.is_cronpost_user}">
                <td><strong>${escapeHtml(contact.display_name)}</strong><br><small class="text-muted">${escapeHtml(contact.contact_email)}</small></td>
                <td>
                    ${contact.is_cronpost_user 
                        ? '<span class="badge bg-success">CronPost User</span>' 
                        : '<span class="badge bg-secondary">External</span>'
                    }
                </td>
                <td><button class="btn btn-outline-secondary btn-sm contact-action-btn" data-action="update">Update</button>
                    <button class="btn btn-outline-danger btn-sm contact-action-btn" data-action="delete">Delete</button></td>
                <td class="text-end">
                    <div class="dropdown">
                        <button class="btn btn-secondary btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown" ${!contact.is_cronpost_user ? 'disabled' : ''}>Send</button>
                        <ul class="dropdown-menu dropdown-menu-end">
                            <li><a class="dropdown-item contact-action-btn" href="#" data-action="in-app">In-App Messenger</a></li>
                            <li><a class="dropdown-item contact-action-btn disabled" href="#" data-action="email">Email (soon)</a></li>
                        </ul>
                    </div>
                </td>
            </tr>
        `).join('');

        tableBody.innerHTML = rowsHtml;

        // Gắn sự kiện cho các nút hành động vừa được tạo
        tableBody.querySelectorAll('.contact-action-btn').forEach(btn => {
            btn.addEventListener('click', handleContactActionClick);
        });
    }
    
    /**
     * Xử lý các hành động trên mỗi liên hệ (Gửi tin, Xóa, Sửa)
     */
    function handleContactActionClick(event) {
        event.preventDefault();
        const target = event.currentTarget;
        const action = target.dataset.action;
        const contactRow = target.closest('tr');
        const email = contactRow.dataset.contactEmail;
        const name = contactRow.dataset.contactName;

        if (action === 'delete') {
            if (confirm(`Are you sure you want to delete the contact "${email}"?`)) {
                deleteContact(email, target);
            }
        } else if (action === 'in-app') {
            if (typeof EditorManager !== 'undefined' && typeof window.sendInAppMessage === 'function') {
                EditorManager.open({
                    recipient: email,
                    onSend: window.sendInAppMessage
                });
            }
        } else if (action === 'update') {
            // Điền thông tin vào modal và hiển thị
            editContactOriginalEmailHidden.value = email;
            editContactEmailInput.value = email;
            editContactNameInput.value = name;
            editModal.show();
        }
    }
    
    /**
     * Gọi API để xóa một liên hệ
     */
    async function deleteContact(contactEmail, buttonElement) {
        buttonElement.disabled = true;
        try {
            const response = await fetchWithAuth('/api/users/contacts', {
                method: 'DELETE',
                body: JSON.stringify({ contact_email: contactEmail })
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to delete contact.');
            }
            buttonElement.closest('tr').remove();
        } catch (error) {
            alert(`Error: ${error.message}`);
            buttonElement.disabled = false;
        }
    }
    
    /**
     * Xử lý khi bấm nút "Save Changes" trên Edit Modal
     */
    async function handleSaveChanges() {
        const originalEmail = editContactOriginalEmailHidden.value;
        const newName = editContactNameInput.value;

        if (!newName.trim()) {
            alert('Contact name cannot be empty.');
            return;
        }

        saveContactChangesBtn.disabled = true;
        saveContactChangesBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Saving...`;

        try {
            // LƯU Ý: API endpoint này cần được tạo ở backend
            const response = await fetchWithAuth(`/api/users/contacts/${originalEmail}`, {
                method: 'PUT',
                body: JSON.stringify({ contact_name: newName })
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to update contact.');
            }
            editModal.hide();
            await initializeContactsView(); // Tải lại toàn bộ danh sách để cập nhật
        } catch(error) {
            alert(`Error: ${error.message}`);
        } finally {
            saveContactChangesBtn.disabled = false;
            saveContactChangesBtn.innerHTML = `Save Changes`;
        }
    }

    function handleAddNewContact() {
        alert('Chức năng "Thêm liên hệ mới" sẽ được xây dựng trong các bước tiếp theo.');
    }

    // Chạy hàm khởi tạo ngay khi script này được tải
    initializeContactsView();

})();