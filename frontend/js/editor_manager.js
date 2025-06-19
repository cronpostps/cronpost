// /frontend/js/editor_manager.js
// Version 3.1.0 - Integrated multi-recipient tags with inline picker architecture.

const EditorManager = {
    // Properties
    instance: null,
    currentUser: null,
    sendCallback: null,
    currentPickerType: null,
    recipientEmails: new Set(), // State for multi-recipient tags

    // Modal & Form Elements
    composeModal: null,
    composeModalElement: null,
    multiEmailContainer: null, // New
    recipientInput: null, // This is now the input inside the tag container
    subjectInput: null,
    sendButton: null,
    composeCloseBtn: null,
    selectContactButton: null,
    mainComposeFields: null,
    
    // Upgrade Modal Elements
    upgradeModal: null,
    upgradeModalElement: null,
    modalUpgradeBtn: null,

    // Attachment Elements
    attachFileBtn: null,
    attachmentsPreviewArea: null,

    // Inline Picker Elements
    pickerContainer: null,
    pickerTitle: null,
    pickerCloseBtn: null,
    pickerSearchInput: null,
    pickerListArea: null,
    pickerLoadingSpinner: null,
    pickerActionArea: null,
    pickerConfirmBtn: null,
    pickerCancelBtn: null,

    // State
    selectedAttachments: [],
    availableFiles: [],
    availableContacts: [],

    /**
     * Initializes the manager.
     */
    init: function(currentUser) {
        this.currentUser = currentUser;

        // Cache DOM elements
        this.composeModalElement = document.getElementById('composeModal');
        this.composeModal = bootstrap.Modal.getOrCreateInstance(this.composeModalElement);
        
        // --- MODIFIED: Cache new recipient elements ---
        this.multiEmailContainer = document.getElementById('multi-email-container');
        this.recipientInput = document.getElementById('recipient-input');
        
        this.subjectInput = document.getElementById('composeSubject');
        this.sendButton = document.getElementById('sendComposeBtn');
        this.selectContactButton = document.getElementById('select-contact-button');
        this.mainComposeFields = document.getElementById('main-compose-fields');
        this.composeCloseBtn = this.composeModalElement.querySelector('.modal-footer .btn-secondary');

        this.upgradeModalElement = document.getElementById('upgradeRequiredModal');
        this.upgradeModal = bootstrap.Modal.getOrCreateInstance(this.upgradeModalElement);
        this.modalUpgradeBtn = document.getElementById('modalUpgradeBtn');
        this.attachFileBtn = document.getElementById('attachFileBtn');
        this.attachmentsPreviewArea = document.getElementById('attachmentsPreviewArea');

        this.pickerContainer = document.getElementById('picker-container');
        this.pickerTitle = document.getElementById('picker-title');
        this.pickerCloseBtn = document.getElementById('picker-close-btn');
        this.pickerSearchInput = document.getElementById('picker-search-input');
        this.pickerListArea = document.getElementById('picker-list-area');
        this.pickerLoadingSpinner = document.getElementById('picker-loading-spinner');
        this.pickerActionArea = document.getElementById('picker-action-area');
        this.pickerConfirmBtn = document.getElementById('picker-confirm-btn');
        this.pickerCancelBtn = document.getElementById('picker-cancel-btn');

        this._setupInternalListeners();
        console.log("EditorManager initialized (v3.1.0 - Multi-Recipient & Inline Picker).");
    },

    /**
     * {* MODIFIED: Always show attach button *}
     */
    open: function({ recipient = '', subject = '', content = '', onSend = null } = {}) {
        if (!this.composeModal) return;
        
        this._hidePicker();
        this._resetRecipientInput();
        if (recipient) {
            // Handle single or multiple initial recipients
            const recipients = Array.isArray(recipient) ? recipient : [recipient];
            recipients.forEach(r => this._addRecipientTag(r));
        }
        
        this.subjectInput.value = subject;
        this.sendCallback = onSend;
        this.selectedAttachments = [];
        this._renderSelectedAttachmentsPreview();
        this.attachFileBtn.style.display = 'inline-block';

        this._createEditorInstance();
        this.composeModal.show();
        setTimeout(() => { this._setEditorData(content); }, 300);
    },
    
    /**
     * {* MODIFIED: Added listeners for new logic *}
     */
    _setupInternalListeners: function() {
        this.sendButton.addEventListener('click', () => this._handleSendClick());
        this.composeModalElement.addEventListener('hidden.bs.modal', () => this._destroyEditorInstance());
        
        this.attachFileBtn.addEventListener('click', () => {
            if (this.currentUser?.membership_type === 'premium') {
                this._showPicker('files');
            } else {
                this.upgradeModal.show();
            }
        });

        // Use the new contact button ID from the multi-email component
        this.selectContactButton.addEventListener('click', () => this._showPicker('contacts'));
        
        this.pickerCloseBtn.addEventListener('click', () => this._hidePicker());
        this.pickerConfirmBtn.addEventListener('click', () => this._handlePickerConfirm());
        this.pickerCancelBtn.addEventListener('click', () => this._hidePicker());
        this.pickerSearchInput.addEventListener('input', (e) => this._handlePickerSearch(e.target.value));
        this.modalUpgradeBtn.addEventListener('click', () => { window.location.href = '/pricing.html'; });

        // Listeners for the multi-email input component
        if (this.multiEmailContainer) {
            this.multiEmailContainer.addEventListener('click', (e) => {
                if (e.target.classList.contains('remove-tag')) {
                    this._removeRecipientTag(e.target.parentElement);
                } else {
                    this.recipientInput.focus();
                }
            });
        }
        if (this.recipientInput) {
            this.recipientInput.addEventListener('keydown', (e) => {
                if (['Enter', ',', 'Tab'].includes(e.key)) {
                    e.preventDefault();
                    const email = this.recipientInput.value.trim();
                    if (email) this._addRecipientTag(email);
                    this.recipientInput.value = '';
                } else if (e.key === 'Backspace' && this.recipientInput.value === '') {
                    const lastTag = this.multiEmailContainer.querySelector('.email-tag:last-of-type');
                    if (lastTag) this._removeRecipientTag(lastTag);
                }
            });
        }
    },

    _showPicker: async function(type) {
        this.currentPickerType = type;
        if(this.sendButton) this.sendButton.disabled = true;
        if(this.composeCloseBtn) this.composeCloseBtn.disabled = true;

        this.mainComposeFields.style.display = 'none';
        this.pickerContainer.style.display = 'block';
        this.pickerListArea.innerHTML = '';
        this.pickerLoadingSpinner.style.display = 'block';
        this.pickerSearchInput.value = '';
        this.pickerActionArea.style.display = 'block';
        
        let title = '';
        let placeholder = '';

        try {
            if (type === 'files') {
                title = 'Select Files to Attach';
                placeholder = 'Search your files...';
                this.pickerConfirmBtn.style.display = 'inline-block';
                const response = await fetchWithAuth('/api/files/');
                if (!response.ok) throw new Error('Could not load your files.');
                this.availableFiles = await response.json();
                this._renderPickerList(this.availableFiles);
            } else if (type === 'contacts') {
                title = 'Select a Contact';
                placeholder = 'Search contacts by name or email...';
                this.pickerConfirmBtn.style.display = 'none';
                const response = await fetchWithAuth('/api/users/contacts');
                if (!response.ok) throw new Error('Could not fetch contacts.');
                const contacts = await response.json();
                this.availableContacts = contacts.filter(c => c.is_cronpost_user);
                this._renderPickerList(this.availableContacts);
            }
            
            this.pickerTitle.textContent = title;
            this.pickerSearchInput.placeholder = placeholder;

        } catch (error) {
            this.pickerListArea.innerHTML = `<div class="p-3 text-danger text-center">${error.message}</div>`;
        } finally {
            this.pickerLoadingSpinner.style.display = 'none';
        }
    },

    _hidePicker: function() {
        this.pickerContainer.style.display = 'none';
        this.mainComposeFields.style.display = 'block';
        this.currentPickerType = null;
        if(this.sendButton) this.sendButton.disabled = false;
        if(this.composeCloseBtn) this.composeCloseBtn.disabled = false;
    },

    _renderPickerList: function(data) {
        this.pickerListArea.innerHTML = '';
        if (data.length === 0) {
            const message = this.currentPickerType === 'files' ? 'You have no uploaded files.' : 'No suitable contacts found.';
            this.pickerListArea.innerHTML = `<div class="list-group-item text-center text-muted">${message}</div>`;
            return;
        }

        let listHtml = '';
        if (this.currentPickerType === 'files') {
            listHtml = data.map(file => `
                <label class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        <strong class="d-block">${escapeHtml(file.original_filename)}</strong>
                        <small class="text-muted">${this._formatBytes(file.filesize_bytes)}</small>
                    </div>
                    <input class="form-check-input" type="checkbox" value="${file.id}" data-filename="${escapeHtml(file.original_filename)}" ${this.selectedAttachments.some(att => att.id === file.id) ? 'checked' : ''}>
                </label>`).join('');
        } else if (this.currentPickerType === 'contacts') {
             listHtml = data.map(contact => `
                <a href="#" class="list-group-item list-group-item-action" data-email="${escapeHtml(contact.contact_email)}">
                    <strong>${escapeHtml(contact.display_name)}</strong>
                    <small class="d-block text-muted">${escapeHtml(contact.contact_email)}</small>
                </a>`).join('');
        }
        
        this.pickerListArea.innerHTML = listHtml;
        
        if (this.currentPickerType === 'contacts') {
            this.pickerListArea.querySelectorAll('a').forEach(item => {
                item.addEventListener('click', (e) => {
                    e.preventDefault();
                    this._addRecipientTag(e.currentTarget.dataset.email);
                    this._hidePicker();
                });
            });
        }
    },

    _handlePickerSearch: function(searchTerm) {
        const lowerCaseTerm = searchTerm.toLowerCase();
        if (this.currentPickerType === 'files') {
            const filtered = this.availableFiles.filter(f => f.original_filename.toLowerCase().includes(lowerCaseTerm));
            this._renderPickerList(filtered);
        } else if (this.currentPickerType === 'contacts') {
            const filtered = this.availableContacts.filter(c => 
                c.display_name.toLowerCase().includes(lowerCaseTerm) || 
                c.contact_email.toLowerCase().includes(lowerCaseTerm)
            );
            this._renderPickerList(filtered);
        }
    },

    _handlePickerConfirm: function() {
        if (this.currentPickerType === 'files') {
            this.selectedAttachments = [];
            const checkboxes = this.pickerListArea.querySelectorAll('input[type="checkbox"]:checked');
            checkboxes.forEach(cb => {
                this.selectedAttachments.push({ id: cb.value, filename: cb.dataset.filename });
            });
            this._renderSelectedAttachmentsPreview();
        }
        this._hidePicker();
    },

    _handleSendClick: async function() {
        const lastEmail = this.recipientInput.value.trim();
        if (lastEmail) this._addRecipientTag(lastEmail);
        this.recipientInput.value = '';

        if (typeof this.sendCallback === 'function') {
            this.sendButton.disabled = true;
            this.sendButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Sending...`;
            
            const data = {
                receiver_emails: Array.from(this.recipientEmails),
                subject: this.subjectInput.value,
                content: this._getEditorData(),
                attachmentIds: this.selectedAttachments.map(att => att.id)
            };

            try {
                const result = await this.sendCallback(data);
                if (result && result.success) {
                    this.composeModal.hide();
                }
            } catch (e) {
                console.error("Error executing send callback:", e);
            } finally {
                this.sendButton.disabled = false;
                this.sendButton.innerHTML = `Send`;
            }
        }
    },
    
    // --- NEW and MODIFIED Helper functions ---
    _addRecipientTag(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email) || this.recipientEmails.has(email)) {
            return;
        }
        this.recipientEmails.add(email);
        const tag = document.createElement('span');
        tag.className = 'email-tag';
        tag.textContent = email;
        tag.dataset.email = email;
        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-tag';
        removeBtn.innerHTML = '&times;';
        removeBtn.setAttribute('aria-label', `Remove ${email}`);
        tag.appendChild(removeBtn);
        this.multiEmailContainer.insertBefore(tag, this.recipientInput);
    },

    _removeRecipientTag(tagElement) {
        const email = tagElement.dataset.email;
        this.recipientEmails.delete(email);
        tagElement.remove();
    },

    _resetRecipientInput() {
        this.recipientEmails.clear();
        if(this.multiEmailContainer) {
            this.multiEmailContainer.querySelectorAll('.email-tag').forEach(tag => tag.remove());
        }
        if(this.recipientInput) this.recipientInput.value = '';
    },

    // --------------------------------

    _renderSelectedAttachmentsPreview: function() {
        this.attachmentsPreviewArea.innerHTML = '';
        if (this.selectedAttachments.length === 0) return;

        const tagsHtml = this.selectedAttachments.map(att => `
            <div class="attachment-tag">
                <span>${escapeHtml(att.filename)}</span>
                <button type="button" class="remove-attachment-btn" data-file-id="${att.id}">&times;</button>
            </div>
        `).join('');
        this.attachmentsPreviewArea.innerHTML = tagsHtml;

        this.attachmentsPreviewArea.querySelectorAll('.remove-attachment-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const fileIdToRemove = e.currentTarget.dataset.fileId;
                this.selectedAttachments = this.selectedAttachments.filter(att => att.id !== fileIdToRemove);
                this._renderSelectedAttachmentsPreview();
            });
        });
    },

    _createEditorInstance: function() {
        if (this.instance) { this._destroyEditorInstance(); }
        const characterLimit = this.currentUser?.membership_type === 'premium' ? 50000 : 5000;
        if (typeof CKEDITOR === 'undefined') { console.error("CKEditor library not found."); return; }
        this.instance = CKEDITOR.replace('composeContent', {
            height: 250, versionCheck: false, extraPlugins: 'wordcount', removePlugins: 'exportpdf',
            wordcount: { showParagraphs: false, showWordCount: false, showCharCount: true, maxCharCount: characterLimit },
            toolbar: [
                { name: 'basicstyles', items: ['Bold', 'Italic', 'Underline', 'Strike'] },
                { name: 'paragraph', items: ['NumberedList', 'BulletedList'] },
                { name: 'links', items: ['Link', 'Unlink'] },
                { name: 'clipboard', items: ['PasteFromWord', 'RemoveFormat'] },
            ]
        });
    },
    _getEditorData: function() { return this.instance ? this.instance.getData() : ''; },
    _setEditorData: function(data) { if (this.instance) this.instance.setData(data); },
    _destroyEditorInstance: function() { if (this.instance) { this.instance.destroy(true); this.instance = null; } },
    _formatBytes: function(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes'; const k = 1024;
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals < 0 ? 0 : decimals))} ${['Bytes', 'KB', 'MB', 'GB', 'TB'][i]}`;
    }
};

function escapeHtml(str) {
    if (str === null || typeof str === 'undefined') return '';
    return str.toString().replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}