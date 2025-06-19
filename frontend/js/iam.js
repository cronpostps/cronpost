// /frontend/js/iam.js
// Version 8.2.0 - Implemented multi-select and delete functionality.

(function() {
    // --- STATE MANAGEMENT ---
    let currentUser = null;
    let currentView = { folder: 'inbox', messageId: null, searchTerm: '' };
    let messageCache = {};
    let isSelectMode = false;
    let selectedMessageIds = new Set();

    // --- DOM Elements ---
    const contentPane = document.getElementById('iam-content-pane');
    const navTabs = document.querySelectorAll('#iam-nav-tabs .nav-link');
    const composeBtn = document.getElementById('iam-compose-btn');
    const searchInput = document.getElementById('iam-search-input');
    const searchBtn = document.getElementById('iam-search-btn');
    const searchSection = document.getElementById('iam-search-section');
    const spinner = document.getElementById('iam-loading-spinner');
    const inboxBadge = document.getElementById('iam-inbox-unread-count');
    // New elements for select mode
    const selectBtn = document.getElementById('iam-select-btn');
    const selectActions = document.getElementById('iam-select-actions');
    const deleteSelectedBtn = document.getElementById('iam-delete-selected-btn');
    const deselectAllBtn = document.getElementById('iam-deselect-all-btn');

    async function initializeApp() {
        try {
            const response = await fetchWithAuth('/api/users/me');
            if (!response.ok) throw new Error("Failed to fetch user data.");
            currentUser = await response.json();
            if (typeof EditorManager !== 'undefined') EditorManager.init(currentUser);
        } catch (error) {
            contentPane.innerHTML = `<div class="alert alert-danger">Error loading page. Please try again later.</div>`;
            return;
        }
        setupEventListeners();
        await renderCurrentView();
        await fetchAndUpdateInboxBadge();
    }

    function setupEventListeners() {
        navTabs.forEach(tab => tab.addEventListener('click', handleNavClick));
        if (composeBtn) composeBtn.addEventListener('click', handleComposeClick);
        if (searchBtn) searchBtn.addEventListener('click', handleSearch);
        if (searchInput) searchInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleSearch(); });
        if (contentPane) contentPane.addEventListener('click', handleContentPaneClick);
        // New listeners for select mode buttons
        if (selectBtn) selectBtn.addEventListener('click', () => toggleSelectMode());
        if (deleteSelectedBtn) deleteSelectedBtn.addEventListener('click', handleDeleteSelected);
        if (deselectAllBtn) deselectAllBtn.addEventListener('click', () => toggleSelectMode(true));
    }

    async function renderCurrentView() {
        showSpinner();
        if (isSelectMode) toggleSelectMode(true); // Always exit select mode on view change

        const isMessageFolder = ['inbox', 'sent'].includes(currentView.folder);
        if (selectBtn) selectBtn.style.display = isMessageFolder ? 'inline-block' : 'none';

        if (currentView.messageId) {
            await renderMessageDetail(currentView.messageId);
        } else {
            switch (currentView.folder) {
                case 'inbox':
                case 'sent':
                    await renderMessageList(currentView.folder);
                    break;
                case 'search':
                    await renderSearchResults(currentView.searchTerm);
                    break;
                case 'contacts':
                    await renderContactsView();
                    break;
            }
        }
        hideSpinner();
    }

    async function renderMessageList(folder) {
        try {
            if (folder !== 'inbox' && messageCache[folder]) { /* use cache */ } 
            else {
                const response = await fetchWithAuth(`/api/messaging/${folder}`);
                if (!response.ok) throw new Error(`Failed to fetch ${folder}.`);
                messageCache[folder] = await response.json();
            }
            const messages = messageCache[folder];

            if (messages.length === 0) {
                contentPane.innerHTML = `<div class="text-center p-5 text-muted">Your ${folder} is empty.</div>`;
                return;
            }

            const rowsHtml = messages.map(msg => {
                const isUnread = folder === 'inbox' && msg.read_at === null;
                const isSelected = selectedMessageIds.has(msg.id);
                let otherPartyDisplay = '';
                if (msg.sender.id === currentUser.id) {
                    const rName = escapeHtml(msg.receiver.user_name), rEmail = escapeHtml(msg.receiver.email);
                    otherPartyDisplay = `To: ${rName ? `${rName} (${rEmail})` : rEmail}`;
                } else {
                    const sName = escapeHtml(msg.sender.user_name), sEmail = escapeHtml(msg.sender.email);
                    otherPartyDisplay = `From: ${sName ? `${sName} (${sEmail})` : sEmail}`;
                }

                return `
                <div class="list-group-item list-group-item-action message-item d-flex align-items-center" data-message-id="${msg.id}" data-thread-id="${msg.thread_id}">
                    ${isSelectMode ? `<input type="checkbox" class="form-check-input iam-select-checkbox" data-message-id="${msg.id}" ${isSelected ? 'checked' : ''}>` : `<span class="unread-indicator ${isUnread ? 'unread' : ''}"></span>`}
                    <div class="flex-grow-1 ${isSelectMode ? 'ms-3' : ''}">
                        <div class="d-flex w-100 justify-content-between">
                            <p class="mb-1 ${isUnread ? 'fw-bold' : ''}">${otherPartyDisplay}</p>
                            <small class="${isUnread ? 'text-primary fw-bold' : 'text-muted'}">${formatRelativeTime(msg.sent_at)}</small>
                        </div>
                        <h6 class="mb-1 ${isUnread ? 'fw-bold' : ''}">${escapeHtml(msg.subject || '(no subject)')}</h6>
                        <p class="mb-1 text-muted text-truncate">${stripHtml(msg.content)}</p>
                    </div>
                </div>`;
            }).join('');
            contentPane.innerHTML = `<div class="list-group list-group-flush">${rowsHtml}</div>`;

        } catch (error) {
            contentPane.innerHTML = `<div class="alert alert-danger">${error.message}</div>`;
        }
    }

    function toggleSelectMode(forceExit = false) {
        isSelectMode = forceExit ? false : !isSelectMode;
        
        if (!isSelectMode) {
            selectedMessageIds.clear();
        }

        if(selectBtn) selectBtn.style.display = isSelectMode ? 'none' : 'inline-block';
        if(selectActions) selectActions.style.display = isSelectMode ? 'block' : 'none';
        
        updateDeleteButtonState();
        renderMessageList(currentView.folder); // Re-render to show/hide checkboxes
    }

    function updateDeleteButtonState() {
        if (deleteSelectedBtn) {
            deleteSelectedBtn.disabled = selectedMessageIds.size === 0;
            deleteSelectedBtn.textContent = selectedMessageIds.size > 0 ? `Delete Selected (${selectedMessageIds.size})` : 'Delete Selected';
        }
    }

    function handleNavClick(event) {
        if(isSelectMode) toggleSelectMode(true); // Exit select mode when changing tabs
        
        const targetFolder = event.currentTarget.dataset.folder;
        if (targetFolder === currentView.folder && currentView.messageId === null) return;
        
        if (searchSection) searchSection.style.display = (targetFolder === 'contacts') ? 'none' : 'block';

        navTabs.forEach(tab => tab.classList.remove('active'));
        event.currentTarget.classList.add('active');

        currentView.folder = targetFolder;
        currentView.messageId = null;
        currentView.searchTerm = '';
        if(searchInput) searchInput.value = '';
        
        renderCurrentView();
    }

    function handleReplyClick() {
        const message = findMessageInCache(currentView.messageId);
        if (!message || typeof EditorManager === 'undefined') return;

        const quotedContent = `
            <br><br>
            <p>--- On ${formatDateTime(message.sent_at)}, ${escapeHtml(message.sender.user_name || message.sender.email)} wrote: ---</p>
            <blockquote>${message.content}</blockquote>
        `;

        EditorManager.open({
            recipient: message.sender.email,
            subject: `Re: ${message.subject || ''}`,
            content: quotedContent,
            onSend: handleSendMessage
        });
    }

    async function handleContentPaneClick(event) {
        // Khai báo tất cả các phần tử có thể được click
        const checkbox = event.target.closest('.iam-select-checkbox');
        const messageItem = event.target.closest('.message-item');
        const backBtn = event.target.closest('#iam-back-btn');
        const replyBtn = event.target.closest('#iam-reply-btn');
        const downloadLink = event.target.closest('.download-attachment');

        // Sắp xếp lại thứ tự kiểm tra cho đúng logic
        if (checkbox) {
            // Nếu click trực tiếp vào checkbox
            const messageId = checkbox.dataset.messageId;
            if (checkbox.checked) {
                selectedMessageIds.add(messageId);
            } else {
                selectedMessageIds.delete(messageId);
            }
            updateDeleteButtonState();
        } else if (isSelectMode && messageItem) {
            // Nếu đang ở chế độ chọn và click vào cả item
            const innerCheckbox = messageItem.querySelector('.iam-select-checkbox');
            if (innerCheckbox) {
                innerCheckbox.checked = !innerCheckbox.checked;
                // Kích hoạt sự kiện để logic thêm/xóa ID được chạy
                innerCheckbox.dispatchEvent(new Event('click', { bubbles: true }));
            }
        } else if (replyBtn) {
            // Nếu click nút Reply
            event.preventDefault();
            handleReplyClick();
        } else if (backBtn) {
            // Nếu click nút Back
            event.preventDefault();
            currentView.messageId = null;
            renderCurrentView();
        } else if (messageItem) {
            // Nếu click vào message item (ở chế độ thường)
            event.preventDefault();
            currentView.messageId = messageItem.dataset.messageId;
            renderCurrentView();
        } else if (downloadLink) {
            // Nếu click link download
            event.preventDefault();
            await handleDownloadClick(downloadLink);
        }
    }

    async function handleDeleteSelected() {
        if (selectedMessageIds.size === 0) return;
        if (!confirm(`Are you sure you want to delete ${selectedMessageIds.size} message(s)? This action cannot be undone.`)) return;

        deleteSelectedBtn.disabled = true;
        deleteSelectedBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Deleting...`;

        const deletePromises = [];
        for (const messageId of selectedMessageIds) {
            deletePromises.push(
                fetchWithAuth(`/api/messaging/${messageId}`, { method: 'DELETE' })
            );
        }

        try {
            await Promise.all(deletePromises);
        } catch (error) {
            console.error("Error during multi-delete:", error);
            alert("An error occurred while deleting messages. Some messages may not have been deleted.");
        } finally {
            // Invalidate cache for the current folder
            delete messageCache[currentView.folder];
            // Exit select mode and re-render
            toggleSelectMode(true);
            await renderCurrentView();
        }
    }
    
    async function renderMessageDetail(messageId) {
        const message = findMessageInCache(messageId);
        if (!message) {
            contentPane.innerHTML = `<div class="alert alert-danger">Message not found.</div>`;
            return;
        }
        if (currentView.folder === 'inbox' && message.read_at === null) {
            try {
                await fetchWithAuth(`/api/messaging/threads/${message.thread_id}`);
                message.read_at = new Date().toISOString();
                delete messageCache['inbox'];
                await fetchAndUpdateInboxBadge();
            } catch (e) { console.error("Failed to mark thread as read", e); }
        }
        let attachmentsHtml = '';
        if (message.attachments && message.attachments.length > 0) {
            attachmentsHtml = '<hr><div class="p-3"><h6 class="mb-2">Attachments:</h6>' + message.attachments.map(file => `<div><a href="#" class="download-attachment" data-file-id="${file.id}" data-filename="${escapeHtml(file.original_filename)}">${escapeHtml(file.original_filename)}</a> <span class="text-muted ms-2">(${formatBytes(file.filesize_bytes)})</span></div>`).join('') + '</div>';
        }
        const fromName = escapeHtml(message.sender.user_name),
            fromEmail = escapeHtml(message.sender.email),
            fromDisplay = fromName ? `${fromName} (${fromEmail})` : fromEmail;
        const toName = escapeHtml(message.receiver.user_name),
            toEmail = escapeHtml(message.receiver.email),
            toDisplay = toName ? `${toName} (${toEmail})` : toEmail;
        const detailHtml = `<div id="iam-message-detail-view">
                <div class="p-3 border-bottom d-flex justify-content-between align-items-center">
                    <button class="btn btn-sm btn-outline-secondary" id="iam-back-btn">&larr; Back to ${currentView.folder}</button>
                    <button class="btn btn-sm btn-primary" id="iam-reply-btn">Reply</button>
                </div>
                <div class="p-3">
                    <h5>${escapeHtml(message.subject || '(no subject)')}</h5>
                    <p class="mb-1"><strong>From:</strong> ${fromDisplay}</p>
                    <p class="mb-1"><strong>To:</strong> ${toDisplay}</p>
                    <p class="text-muted"><strong>Sent:</strong> ${formatDateTime(message.sent_at)}</p>
                </div>
                <div class="message-body">${message.content}</div>
                ${attachmentsHtml}
            </div>`;
        contentPane.innerHTML = detailHtml;
    }
    
    async function handleSendMessage(data) {
        // {* MODIFIED: Updated validation to check the receiver_emails array *}
        if (!data.receiver_emails || data.receiver_emails.length === 0 || !data.content) {
            alert('Recipient(s) and message content are required.');
            return { success: false };
        }
        try {
            const payload = {
                // {* MODIFIED: Use the correct key for the payload *}
                receiver_emails: data.receiver_emails,
                subject: data.subject,
                content: data.content,
                attachment_file_ids: data.attachmentIds
            };
            const response = await fetchWithAuth('/api/messaging/send', {
                method: 'POST', body: JSON.stringify(payload)
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to send message.');
            }
            
            // Invalidate cache for sent folder and switch to it
            delete messageCache['sent'];
            document.querySelector('#iam-nav-tabs .nav-link[data-folder="sent"]').click();

            return { success: true };
        } catch (error) {
            alert(`Error: ${error.message}`);
            return { success: false };
        }
    }
    
    async function renderContactsView() { await loadHtmlFragment('/contacts.html', contentPane, '/js/contacts.js'); }
    async function renderSearchResults(term) { if (!term) { contentPane.innerHTML = '<p class="text-center p-5">Please enter a search term.</p>'; return; } try { const response = await fetchWithAuth(`/api/messaging/search?q=${encodeURIComponent(term)}`); if (!response.ok) throw new Error('Search request failed.'); const messages = await response.json(); if (messages.length === 0) { contentPane.innerHTML = `<div class="text-center p-5 text-muted">No results found for "<strong>${escapeHtml(term)}</strong>".</div>`; return; } const header = `<div class="p-3 border-bottom">Search results for "<strong>${escapeHtml(term)}</strong>":</div>`; const rowsHtml = messages.map(msg => { const otherParty = `From: ${escapeHtml(msg.sender.user_name || msg.sender.email)}`; return `<a href="#" class="list-group-item list-group-item-action message-item" data-message-id="${msg.id}" data-thread-id="${msg.thread_id}"><div class="d-flex w-100 justify-content-between"><p class="mb-1">${otherParty}</p><small class="text-muted">${formatRelativeTime(msg.sent_at)}</small></div><h6 class="mb-1">${escapeHtml(msg.subject || '(no subject)')}</h6></a>`; }).join(''); contentPane.innerHTML = header + `<div class="list-group list-group-flush">${rowsHtml}</div>`; } catch (error) { contentPane.innerHTML = `<div class="alert alert-danger">${error.message}</div>`; } }
    function handleSearch() { const term = searchInput.value.trim(); if (!term) return; navTabs.forEach(tab => tab.classList.remove('active')); currentView.folder = 'search'; currentView.messageId = null; currentView.searchTerm = term; renderCurrentView(); }
    function handleComposeClick() { if (typeof EditorManager !== 'undefined') { EditorManager.open({ onSend: handleSendMessage }); } }
    
    async function handleDownloadClick(linkElement) { const fileId = linkElement.dataset.fileId, filename = linkElement.dataset.filename, originalText = linkElement.innerHTML; linkElement.innerHTML = 'Downloading...'; linkElement.style.pointerEvents = 'none'; try { const response = await fetchWithAuth(`/api/files/download/${fileId}`); if (!response.ok) throw new Error('Download failed.'); const blob = await response.blob(); const url = window.URL.createObjectURL(blob); const a = document.createElement('a'); a.style.display = 'none'; a.href = url; a.download = filename; document.body.appendChild(a); a.click(); window.URL.revokeObjectURL(url); a.remove(); } catch (error) { alert(`Error: ${error.message}`); } finally { linkElement.innerHTML = originalText; linkElement.style.pointerEvents = 'auto'; } }
    async function fetchAndUpdateInboxBadge() { if (!inboxBadge) return; try { const response = await fetchWithAuth('/api/messaging/unread-count'); if(response.ok) { const data = await response.json(); const count = data.unread_count || 0; if (count > 0) { inboxBadge.textContent = count > 99 ? '99+' : count; inboxBadge.style.display = 'inline-block'; } else { inboxBadge.style.display = 'none'; } } } catch(e) { console.error("Failed to fetch unread count for badge.", e); inboxBadge.style.display = 'none'; } }
    function showSpinner() { if(spinner) spinner.style.display = 'block'; contentPane.innerHTML = ''; }
    function hideSpinner() { if(spinner) spinner.style.display = 'none'; }
    function findMessageInCache(messageId) { for (const folder in messageCache) { const found = messageCache[folder]?.find(m => m.id === messageId); if (found) return found; } return null; }
    async function loadHtmlFragment(htmlPath, container, scriptPath) { try { const response = await fetch(htmlPath + '?t=' + new Date().getTime()); if (!response.ok) throw new Error(`Could not load ${htmlPath}`); container.innerHTML = await response.text(); if (scriptPath) { const script = document.createElement('script'); script.src = scriptPath; script.onload = () => script.remove(); document.body.appendChild(script); } } catch (error) { container.innerHTML = `<div class="alert alert-danger">Failed to load content.</div>`; } }
    function escapeHtml(str) { if (str === null || typeof str === 'undefined') return ''; return str.toString().replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));}
    function stripHtml(html) { if (!html) return ""; let doc = new DOMParser().parseFromString(html, 'text/html'); return doc.body.textContent || "";}
    function formatBytes(bytes, decimals = 2) { if (bytes === 0) return '0 Bytes'; const k = 1024; const i = Math.floor(Math.log(bytes) / Math.log(k)); return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals < 0 ? 0 : decimals))} ${['Bytes', 'KB', 'MB', 'GB', 'TB'][i]}`; }
    function formatDateTime(iso) { if (!iso) return ''; return new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }); }
    function formatRelativeTime(iso) { if (!iso) return ''; const dt = new Date(iso), now = new Date(), diff = Math.round((now - dt) / 1000); if (diff < 60) return 'now'; if (diff < 3600) return `${Math.floor(diff / 60)}m ago`; if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`; return dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }); }

    // --- START THE APP ---
    initializeApp();

})();