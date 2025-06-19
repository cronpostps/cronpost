// /frontend/js/iam.js
// Version 7.5.0

document.addEventListener('DOMContentLoaded', () => {

    // --- STATE & PAGE-SPECIFIC ELEMENTS ---
    let currentUser = null;
    let currentFolder = 'inbox';
    let messageList = [];
    let activeMessage = null;

    const navLinks = document.querySelectorAll('#mailbox-nav .nav-link');
    const mainPaneTitle = document.getElementById('main-pane-title');
    const mainPaneContent = document.getElementById('main-pane-content');
    const messageSearchInput = document.getElementById('message-search-input');
    
    const composeButton = document.getElementById('compose-button');
    const replyButton = document.getElementById('reply-button');
    const deleteButton = document.getElementById('delete-button');
    const markAllReadBtn = document.getElementById('mark-all-read-btn');
    const addContactButton = document.getElementById('add-contact-button');


    // --- INITIALIZATION ---
    async function initializePage() {
        try {
            const response = await fetchWithAuth('/api/users/me');
            if (!response.ok) throw new Error("Failed to fetch user data.");
            currentUser = await response.json();

            if (typeof EditorManager !== 'undefined') {
                EditorManager.init(currentUser);
            }

            setupEventListeners();
            await fetchAndRenderFolder('inbox');

        } catch (error) {
            console.error("Initialization failed:", error);
            mainPaneContent.innerHTML = `<div class="alert alert-danger">Error loading page content.</div>`;
        }
    }


    // --- EVENT LISTENERS ---
    function setupEventListeners() {
        navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const folder = e.currentTarget.dataset.folder;
                if (folder) {
                    navLinks.forEach(l => l.classList.remove('active'));
                    e.currentTarget.classList.add('active');
                    fetchAndRenderFolder(folder);
                }
            });
        });
        let searchDebounceTimer;
        messageSearchInput.addEventListener('input', (event) => {
            clearTimeout(searchDebounceTimer);
            const searchTerm = event.target.value.trim();
            searchDebounceTimer = setTimeout(() => handleSearch(searchTerm), 500);
        });        
        deleteButton.addEventListener('click', handleDeleteClick);
        replyButton.addEventListener('click', handleReplyClick);
        composeButton.addEventListener('click', handleComposeClick);
        markAllReadBtn.addEventListener('click', handleMarkAllRead);
    }
    
    
    // --- CORE LOGIC ---
    async function fetchAndRenderFolder(folder) {
        currentFolder = folder;
        activeMessage = null;
        updateButtonVisibility(false);
        mainPaneContent.innerHTML = renderSpinner();
        
        const titleMap = {
            'inbox': 'Inbox', 'sent': 'Sent', 'all': 'All Messages', 
            'contacts': 'Contacts', 'blocked': 'Blocked Users'
        };
        mainPaneTitle.textContent = titleMap[folder] || 'Inbox';
        
        if (folder === 'contacts') {
            // Tải fragment HTML, sau đó tải và chạy script của nó
            await loadHtmlFragment('/contacts.html', mainPaneContent, '/js/contacts.js');
            return;
        }

        // Xử lý các folder tin nhắn còn lại
        try {
            const apiUrl = `/api/messaging/${folder}`;
            const response = await fetchWithAuth(apiUrl);
            if (!response.ok) throw new Error(`Failed to fetch ${folder}.`);
            messageList = await response.json();
            renderMessageList(messageList);
        } catch (error) {
            console.error(`Error loading content for ${folder}:`, error);
            mainPaneContent.innerHTML = `<div class="alert alert-danger">Could not load content.</div>`;
        }
    }

    // --- ACTION HANDLERS (Calling the EditorManager) ---

    function handleComposeClick() {
        if (typeof EditorManager !== 'undefined') EditorManager.open({ onSend: window.sendInAppMessage });
    }

    function handleReplyClick() {
        if (!activeMessage || typeof EditorManager === 'undefined') return;
        const quotedContent = `
            <br><br>
            <p>--- On ${formatDateTime(activeMessage.sent_at)}, ${escapeHtml(activeMessage.sender.user_name || activeMessage.sender.email)} wrote: ---</p>
            <blockquote>${activeMessage.content}</blockquote>
        `;
        EditorManager.open({
            recipient: activeMessage.sender.email,
            subject: `Re: ${activeMessage.subject || ''}`,
            content: quotedContent,
            onSend: window.sendInAppMessage
        });
    }

    /**
     * SEND CALLBACK FUNCTION - Passed to the EditorManager
     */

    window.sendInAppMessage = async function(data) {
        console.log("Sending In-App Message with data:", data);
        if (!data.recipient || !data.content) {
            alert('Recipient and message content are required.');
            return { success: false };
        }
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(data.recipient)) {
            alert('Invalid recipient email format. Please check again.');
            return { success: false };
        }


        try {
            const payload = {
                receiver_email: data.recipient,
                subject: data.subject,
                content: data.content,
                attachment_file_ids: data.attachmentIds
            };
            const response = await fetchWithAuth('/api/messaging/send', {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw await response.json();
            }
            
            await fetchAndRenderFolder('sent');
            document.querySelectorAll('#mailbox-nav .nav-link').forEach(l => l.classList.remove('active'));
            document.querySelector('#mailbox-nav .nav-link[data-folder="sent"]').classList.add('active');
            
            return { success: true };

        } catch (error) {
            console.error("Send message error object:", error);
            
            let errorMessage = 'An unknown error occurred.';
            if (error && error.detail) {
                if (Array.isArray(error.detail)) {
                    errorMessage = error.detail.map(e => e.msg).join(', ');
                } 
                else if (typeof error.detail === 'string') {
                    errorMessage = error.detail;
                }
            }
            else if (error && error.message) {
                errorMessage = error.message;
            }
            
            alert(`Error: ${errorMessage}`);
            
            return { success: false };
        }
    }


    // --- ALL OTHER PAGE-SPECIFIC FUNCTIONS ---
    async function handleSearch(searchTerm) {
        if (searchTerm.length === 0) {
            fetchAndRenderFolder(currentFolder);
        } else if (searchTerm.length >= 2) {
            mainPaneTitle.textContent = `Search results for: "${searchTerm}"`;
            mainPaneContent.innerHTML = renderSpinner();
            try {
                const encodedTerm = encodeURIComponent(searchTerm);
                const response = await fetchWithAuth(`/api/messaging/search?q=${encodedTerm}`);
                if (!response.ok) throw new Error('Search failed');
                const results = await response.json();
                renderMessageList(results, true);
            } catch (error) {
                console.error("Search error:", error);
                mainPaneContent.innerHTML = `<div class="alert alert-danger">Search request failed.</div>`;
            }
        }
    }

    async function handleMessageClick(event) {
        event.preventDefault();
        const messageListItem = event.currentTarget;
        const messageId = messageListItem.dataset.messageId;
        const clickedMessage = messageList.find(m => m.id === messageId);
        if (clickedMessage) {
            activeMessage = clickedMessage;
            try {
                const isUnread = clickedMessage.read_at === null;
                if (isUnread) {
                    await fetchWithAuth(`/api/messaging/threads/${clickedMessage.thread_id}`);
                    messageListItem.querySelectorAll('.fw-bold').forEach(el => el.classList.remove('fw-bold'));
                    const indicator = messageListItem.querySelector('.unread-indicator');

                    if (indicator) indicator.classList.remove('unread');
                    clickedMessage.read_at = new Date().toISOString();
                    await fetchAndUpdateUnreadCount();
                }
            } catch (error) { console.error("Failed to mark message as read:", error); }
            renderMessageDetail(activeMessage);
        }
    }

    async function handleMarkAllRead() {
        if (confirm('Are you sure you want to mark all messages as read?')) {
            markAllReadBtn.disabled = true;
            markAllReadBtn.textContent = 'Marking...';
            try {
                const response = await fetchWithAuth('/api/messaging/inbox/mark-all-as-read', { method: 'POST' });
                if (!response.ok) throw new Error('Failed to mark all messages as read.');
                await fetchAndRenderFolder('inbox');
            } catch (error) {
                console.error("Mark all as read error:", error);
                alert("An error occurred. Please try again.");
            } finally {
                markAllReadBtn.disabled = false;
                markAllReadBtn.textContent = 'Mark all as read';
            }
        }
    }

    async function handleDeleteClick() {
        if (!activeMessage || !confirm('Are you sure you want to delete this message?')) return;
        try {
            const response = await fetchWithAuth(`/api/messaging/${activeMessage.id}`, { method: 'DELETE' });
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Failed to delete message.');
            }
            alert('Message deleted successfully.');
            await fetchAndRenderFolder(currentFolder);
        } catch (error) {
            console.error('Delete error:', error);
            alert(`Error: ${error.message}`);
        }
    }

    async function handleDownloadClick(event) {
        const button = event.currentTarget;
        const fileId = button.dataset.fileId;
        const filename = button.dataset.filename;

        button.disabled = true;
        button.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Downloading...`;

        try {
            const response = await fetchWithAuth(`/api/files/download/${fileId}`);
            if (!response.ok) {
                throw new Error('Download failed. You may not have permission or the file is missing.');
            }
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();

        } catch (error) {
            console.error("Download error:", error);
            alert(`Error: ${error.message}`);
        } finally {
            button.disabled = false;
            button.innerHTML = `<i class="icon-paper-clip me-2"></i>${escapeHtml(filename)}`;
        }
    }

    // --- RENDERING & UTILITY FUNCTIONS ---
    function renderMessageList(messages, isSearchResult = false) {
        if (!messages || messages.length === 0) {
            mainPaneContent.innerHTML = '<p class="text-center text-muted mt-5">No messages found.</p>';
            return;
        }
        const messageListHtml = messages.map(msg => {
            const isUnread = !isSearchResult && currentFolder === 'inbox' && msg.read_at === null;
            const otherParty = msg.sender.id === currentUser.id 
                ? `To: ${escapeHtml(msg.receiver.user_name || msg.receiver.email)}`
                : `From: ${escapeHtml(msg.sender.user_name)} (${escapeHtml(msg.sender.email)})`;
            return `
            <a href="#" class="list-group-item list-group-item-action message-item d-flex align-items-center" data-message-id="${msg.id}">
                <span class="unread-indicator ${isUnread ? 'unread' : ''}"></span>
                <div class="w-100">
                    <div class="d-flex w-100 justify-content-between">
                        <p class="mb-1 ${isUnread ? 'fw-bold' : ''}">${otherParty}</p>
                        <small class="${isUnread ? 'fw-bold' : 'text-muted'} text-nowrap">${formatRelativeTime(msg.sent_at)}</small>
                    </div>
                    <h6 class="mb-1 ${isUnread ? 'fw-bold' : ''}">${escapeHtml(msg.subject || '(no subject)')}</h6>
                    <p class="mb-1 text-muted text-truncate">${stripHtml(msg.content)}</p>
                </div>
            </a>`;
        }).join('');
        mainPaneContent.innerHTML = `<div class="list-group list-group-flush">${messageListHtml}</div>`;
        document.querySelectorAll('.message-item').forEach(item => item.addEventListener('click', handleMessageClick));
    }

    function renderMessageDetail(message) {
        mainPaneTitle.textContent = `Subject: ${escapeHtml(message.subject || '(no subject)')}`;
        const from = `<strong>From:</strong> ${escapeHtml(message.sender.user_name)} &lt;${escapeHtml(message.sender.email)}&gt;`;
        const to = `<strong>To:</strong> ${escapeHtml(message.receiver.user_name || message.receiver.email)}`;
        const sent = `<strong>Sent:</strong> ${formatDateTime(message.sent_at)}`;
        let detailHtml = `
            <div class="p-3 border-bottom">
                <p class="mb-1">${from}</p>
                <p class="mb-1">${to}</p>
                <p class="mb-0 text-muted">${sent}</p>
            </div>
            <div class="p-3 message-content-body">
                ${message.content}
            </div>
        `;
        let attachmentsHtml = '';
        if (message.attachments && message.attachments.length > 0) {
            attachmentsHtml += '<hr><div class="p-3"><h6 class="mb-2">Attachments:</h6><ul class="list-unstyled mb-0">';
            message.attachments.forEach(file => {
                attachmentsHtml += `
                    <button class="btn btn-link text-decoration-none p-0 download-btn" 
                            data-file-id="${file.id}" 
                            data-filename="${file.original_filename}">
                        <i class="icon-paper-clip me-2"></i>${escapeHtml(file.original_filename)}
                    </button>
                    <span class="text-muted ms-2">(${formatBytes(file.filesize_bytes)})</span>
                `;
            });
            attachmentsHtml += '</ul></div>';
        }
        mainPaneContent.innerHTML = detailHtml + attachmentsHtml;
        mainPaneContent.querySelectorAll('.download-btn').forEach(button => {
            button.addEventListener('click', handleDownloadClick);
        });
        updateButtonVisibility(true);
    }

    function updateButtonVisibility(isViewingMessage) {
        replyButton.style.display = isViewingMessage ? 'inline-block' : 'none';
        deleteButton.style.display = isViewingMessage ? 'inline-block' : 'none';
        addContactButton.style.display = currentFolder === 'contacts' ? 'inline-block' : 'none';
        composeButton.style.display = 'inline-block';
    }

    function renderSpinner() { return `<div class="text-center p-5"><div class="spinner-border" role="status"></div></div>`; }

    async function loadHtmlFragment(htmlPath, container, scriptPath) {
        try {
            container.innerHTML = renderSpinner();
            // Build an absolute URL to prevent mixed content errors
            const absoluteUrl = location.origin + htmlPath + '?t=' + new Date().getTime();
            const response = await fetch(absoluteUrl);
            if (!response.ok) throw new Error(`Could not load ${htmlPath}`);
            container.innerHTML = await response.text();

            if (scriptPath) {
                const script = document.createElement('script');
                script.src = scriptPath;
                script.onload = () => { script.remove(); };
                document.body.appendChild(script);
            }
        } catch (error) {
            console.error("Error loading HTML fragment:", error);
            container.innerHTML = `<div class="alert alert-danger">Failed to load content.</div>`;
        }
    }

    // --- Run Initialization ---
    initializePage();
});