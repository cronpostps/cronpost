// /frontend/js/editor_manager.js
// Version 2.2.0 - Integrated with ContactsManager

const EditorManager = {
    // Properties
    instance: null,
    currentUser: null,
    sendCallback: null,

    // Modal & Form Elements
    composeModal: null,
    composeModalElement: null,
    recipientInput: null,
    subjectInput: null,
    sendButton: null,
    selectContactButton: null,

    // Attachment Elements
    attachFileBtn: null,
    attachmentsPreviewArea: null,
    filePickerModal: null,
    filePickerModalElement: null,
    filePickerListBody: null,
    filePickerLoading: null,
    filePickerSearch: null,
    confirmAttachmentBtn: null,

    // Attachment State
    selectedAttachments: [],
    availableFiles: [],

    /**
     * Initializes the manager. Must be called once on page load.
     * Caches all DOM elements and sets up internal event listeners.
     */
    init: function(currentUser) {
        this.currentUser = currentUser;

        // Cache DOM elements from the shared modals in the footer
        this.composeModalElement = document.getElementById('composeModal');
        this.composeModal = bootstrap.Modal.getOrCreateInstance(this.composeModalElement);
        this.recipientInput = document.getElementById('composeRecipient');
        this.subjectInput = document.getElementById('composeSubject');
        this.sendButton = document.getElementById('sendComposeBtn');
        this.attachFileBtn = document.getElementById('attachFileBtn');
        this.attachmentsPreviewArea = document.getElementById('attachmentsPreviewArea');
        this.filePickerModalElement = document.getElementById('filePickerModal');
        this.filePickerModal = bootstrap.Modal.getOrCreateInstance(this.filePickerModalElement);
        this.filePickerListBody = document.getElementById('file-picker-list-body');
        this.filePickerLoading = document.getElementById('file-picker-loading');
        this.filePickerSearch = document.getElementById('file-picker-search');
        this.confirmAttachmentBtn = document.getElementById('confirm-attachment-btn');
        this.selectContactButton = document.getElementById('select-contact-button');

        this._setupInternalListeners();
        console.log("EditorManager initialized.");
    },

    /**
     * Main public method to open the compose modal.
     */
    open: function({ recipient = '', subject = '', content = '', onSend = null } = {}) {
        if (!this.composeModal) {
            console.error("EditorManager not initialized. Call init() first.");
            return;
        }
        // Reset form state
        this.recipientInput.value = recipient;
        this.subjectInput.value = subject;
        this.sendCallback = onSend;
        this.selectedAttachments = [];
        this._renderSelectedAttachmentsPreview();

        // Show/hide premium features
        this.attachFileBtn.style.display = (this.currentUser?.membership_type === 'premium') ? 'inline-block' : 'none';

        // Create editor, then show modal, then set content
        this._createEditorInstance();
        this.composeModal.show();
        setTimeout(() => { this._setEditorData(content); }, 300);
    },

    /**
     * Handles the click on the 'Contacts' button inside the compose modal.
     * @private
     */
    _handleSelectContactClick: function() {
        if (typeof ContactsManager !== 'undefined') {
            ContactsManager.openPicker({
                filter: 'cronpost_users_only', 
                onSelect: (selectedEmail) => {
                    this.recipientInput.value = selectedEmail;
                }
            });
        }
    },

    /**
     * Sets up all internal event listeners for the modals.
     * @private
     */
    _setupInternalListeners: function() {
        // Send button listener
        this.sendButton.addEventListener('click', async () => {
            if (typeof this.sendCallback === 'function') {
                this.sendButton.disabled = true;
                this.sendButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Sending...`;
                const data = {
                    recipient: this.recipientInput.value,
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
        });

        // Destroy editor when compose modal is hidden
        this.composeModalElement.addEventListener('hidden.bs.modal', () => this._destroyEditorInstance());

        // Attachment-related listeners
        this.attachFileBtn.addEventListener('click', () => this._openFilePicker());
        this.confirmAttachmentBtn.addEventListener('click', () => this._handleConfirmAttachments());
        this.selectContactButton.addEventListener('click', () => this._handleSelectContactClick());
        this.filePickerSearch.addEventListener('input', (e) => this._handleFilePickerSearch(e.target.value));
    },

    // --- CKEditor specific methods ---
    _createEditorInstance: function() {
        if (this.instance) { this._destroyEditorInstance(); }
        const characterLimit = this.currentUser?.membership_type === 'premium' ? this.currentUser.max_message_chars_premium : this.currentUser?.max_message_chars_free || 5000;
        if (typeof CKEDITOR === 'undefined') { console.error("CKEditor library not found."); return; }
        this.instance = CKEDITOR.replace('composeContent', {
            height: 250, versionCheck: false, extraPlugins: 'wordcount,pastefromword', removePlugins: 'exportpdf',
            pasteFromWordRemoveFontStyles: true, pasteFromWordRemoveStyles: true,
            wordcount: { showParagraphs: false, showWordCount: false, showCharCount: true, maxCharCount: characterLimit },
            toolbar: [
                { name: 'basicstyles', items: ['Bold', 'Italic', 'Underline', 'Strike'] },
                { name: 'paragraph', items: ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent'] },
                { name: 'links', items: ['Link', 'Unlink'] }, { name: 'styles', items: ['Format'] },
                { name: 'clipboard', items: ['PasteFromWord'] }, { name: 'about', items: ['About'] }
            ],
            removeButtons: 'Subscript,Superscript,Anchor'
        });
    },
    _getEditorData: function() { return this.instance ? this.instance.getData() : ''; },
    _setEditorData: function(data) { if (this.instance) this.instance.setData(data); },
    _destroyEditorInstance: function() { if (this.instance) { this.instance.destroy(true); this.instance = null; } },

    // --- File-picker specific methods ---
    _openFilePicker: async function() {
        this.filePickerListBody.innerHTML = '';
        this.filePickerLoading.style.display = 'block';
        this.filePickerSearch.value = '';
        this.filePickerModal.show();
        try {
            const response = await fetchWithAuth('/api/files/');
            if (!response.ok) throw new Error('Could not load your files.');
            this.availableFiles = await response.json();
            this._renderFilePickerList(this.availableFiles);
        } catch (error) {
            this.filePickerListBody.innerHTML = `<tr><td colspan="4" class="text-danger text-center">Error loading files.</td></tr>`;
        } finally {
            this.filePickerLoading.style.display = 'none';
        }
    },
    _renderFilePickerList: function(filesToRender) {
        this.filePickerListBody.innerHTML = '';
        if (filesToRender.length === 0) {
            this.filePickerListBody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">You have no uploaded files.</td></tr>`;
            return;
        }
        filesToRender.forEach(file => {
            const isSelected = this.selectedAttachments.some(att => att.id === file.id);
            this.filePickerListBody.innerHTML += `
                <tr>
                    <td><input class="form-check-input" type="checkbox" value="${file.id}" data-filename="${file.original_filename}" ${isSelected ? 'checked' : ''}></td>
                    <td>${file.original_filename}</td>
                    <td>${this._formatBytes(file.filesize_bytes)}</td>
                    <td>${new Date(file.created_at).toLocaleDateString()}</td>
                </tr>`;
        });
    },
    _handleFilePickerSearch: function(searchTerm) {
        const lowerCaseSearchTerm = searchTerm.toLowerCase();
        const filteredFiles = this.availableFiles.filter(file => file.original_filename.toLowerCase().includes(lowerCaseSearchTerm));
        this._renderFilePickerList(filteredFiles);
    },
    _handleConfirmAttachments: function() {
        this.selectedAttachments = [];
        const checkboxes = this.filePickerListBody.querySelectorAll('input[type="checkbox"]:checked');
        checkboxes.forEach(cb => {
            this.selectedAttachments.push({ id: cb.value, filename: cb.dataset.filename });
        });
        this._renderSelectedAttachmentsPreview();
        this.filePickerModal.hide();
    },
    _renderSelectedAttachmentsPreview: function() {
        this.attachmentsPreviewArea.innerHTML = '';
        this.selectedAttachments.forEach(att => {
            this.attachmentsPreviewArea.innerHTML += `
                <div class="attachment-tag">
                    <span>${att.filename}</span>
                    <button type="button" class="remove-attachment-btn" data-file-id="${att.id}">&times;</button>
                </div>`;
        });
        this.attachmentsPreviewArea.querySelectorAll('.remove-attachment-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const fileIdToRemove = e.currentTarget.dataset.fileId;
                this.selectedAttachments = this.selectedAttachments.filter(att => att.id !== fileIdToRemove);
                this._renderSelectedAttachmentsPreview();
            });
        });
    },
    _formatBytes: function(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes'; const k = 1024;
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals < 0 ? 0 : decimals))} ${['Bytes', 'KB', 'MB', 'GB', 'TB'][i]}`;
    }
};