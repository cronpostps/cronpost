// /frontend/js/upload-file.js
// Version: 1.1.0
// - Corrected PIN verification endpoint to /api/users/verify-pin-session
// - Added a local upload function to avoid modifying utils.js

document.addEventListener('DOMContentLoaded', () => {

    // --- DOM Elements ---
    const mainContent = document.getElementById('main-content');
    const permissionDeniedPlaceholder = document.getElementById('permission-denied-placeholder');
    const storageUsageDisplay = document.getElementById('storage-usage-display');
    const uploadForm = document.getElementById('upload-form');
    const fileInput = document.getElementById('file-input');
    const uploadButton = document.getElementById('upload-button');
    const uploadSpinner = document.getElementById('upload-spinner');
    const uploadStatusMessage = document.getElementById('upload-status-message');
    const fileListBody = document.getElementById('file-list-body');
    const fileListLoading = document.getElementById('file-list-loading');
    
    // --- State ---
    let currentUser = null;
    const MAX_STORAGE_GB = 1;

    // --- Main Initialization Function ---
    async function initializePage() {
        try {
            const response = await fetchWithAuth('/api/users/me');
            if (!response.ok) {
                window.location.href = '/signin';
                return;
            }
            currentUser = await response.json();

            if (currentUser.membership_type !== 'premium') {
                mainContent.classList.add('d-none');
                permissionDeniedPlaceholder.classList.remove('d-none');
                return;
            }

            mainContent.classList.remove('d-none');
            await fetchAndRenderFiles();

        } catch (error) {

            console.error('Initialization failed:', error);
            mainContent.classList.add('d-none');
            permissionDeniedPlaceholder.textContent = 'An error occurred while loading the page. Please try again later.';
            permissionDeniedPlaceholder.classList.remove('d-none');
        }
    }

    // --- Data Fetching and Rendering ---
    async function fetchAndRenderFiles() {
        fileListLoading.classList.remove('d-none');
        fileListBody.innerHTML = '';
        
        try {
            const response = await fetchWithAuth('/api/files/');
            if (!response.ok) throw new Error('Failed to fetch files.');

            const files = await response.json();
            
            if (files.length === 0) {
                fileListBody.innerHTML = '<tr><td colspan="4" class="text-center">No files uploaded yet.</td></tr>';
            } else {
                files.forEach(file => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${escapeHtml(file.original_filename)}</td>
                        <td>${formatBytes(file.filesize_bytes)}</td>
                        <td>${new Date(file.created_at).toLocaleString()}</td>
                        <td>
                            <button class="btn btn-danger btn-sm delete-btn" data-file-id="${file.id}">Delete</button>
                        </td>
                    `;
                    fileListBody.appendChild(row);
                });
            }
            
            const totalUsedBytes = files.reduce((sum, file) => sum + file.filesize_bytes, 0);
            storageUsageDisplay.textContent = `${formatBytes(totalUsedBytes)} / ${MAX_STORAGE_GB} GB`;

        } catch (error) {
            console.error('Error fetching files:', error);
            fileListBody.innerHTML = '<tr><td colspan="4" class="text-center text-danger">Could not load files.</td></tr>';
        } finally {
            fileListLoading.classList.add('d-none');
            addDeleteButtonListeners();
        }
    }

    // --- Event Handlers & Helpers ---

    // Custom fetch function for FormData to avoid modifying the shared utils.js
    async function uploadFileWithManualFetch(formData) {
        const accessToken = localStorage.getItem('accessToken');
        const headers = {};
        if (accessToken) {
            headers['Authorization'] = `Bearer ${accessToken}`;
        }
        return fetch('/api/files/upload', {
            method: 'POST',
            body: formData,
            headers: headers
        });
    }

    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const file = fileInput.files[0];
        if (!file) {
            displayStatusMessage('Please select a file to upload.', false);
            return;
        }
        toggleUploadUI(true);
        const formData = new FormData();
        formData.append('file', file);
        try {
            const response = await uploadFileWithManualFetch(formData);
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.detail || 'Upload failed.');
            }
            displayStatusMessage('File uploaded successfully!', true);
            uploadForm.reset();
            await fetchAndRenderFiles();
        } catch (error) {
            displayStatusMessage(`Error: ${error.message}`, false);
        } finally {
            toggleUploadUI(false);
        }
    });

    function addDeleteButtonListeners() {
        document.querySelectorAll('.delete-btn').forEach(button => {
            button.addEventListener('click', async (e) => {
                const fileId = e.target.dataset.fileId;
                if (confirm('Are you sure you want to delete this file?')) {
                    await deleteFile(fileId, e.target);
                }
            });
        });
    }

    async function deleteFile(fileId, buttonElement) {
        buttonElement.disabled = true;
        buttonElement.textContent = 'Deleting...';
        try {
            const response = await fetchWithAuth(`/api/files/${fileId}`, { method: 'DELETE' });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to delete file.');
            }
            buttonElement.closest('tr').remove();
            displayStatusMessage('File deleted successfully.', true, 3000);
            await fetchAndRenderFiles(); // Recalculate storage
        } catch (error) {
            alert(`Error: ${error.message}`);
            buttonElement.disabled = false;
            buttonElement.textContent = 'Delete';
        }
    }

    function toggleUploadUI(isUploading) {
        uploadButton.disabled = isUploading;
        fileInput.disabled = isUploading;
        uploadSpinner.classList.toggle('d-none', !isUploading);
        uploadButton.textContent = isUploading ? 'Uploading...' : 'Upload';
    }
    
    function displayStatusMessage(message, isSuccess, timeout = 0) {
        uploadStatusMessage.textContent = message;
        uploadStatusMessage.className = `alert mt-3 ${isSuccess ? 'alert-success' : 'alert-danger'}`;
        if (timeout > 0) {
            setTimeout(() => { uploadStatusMessage.className += ' d-none'; }, timeout);
        }
    }

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals < 0 ? 0 : decimals))} ${['Bytes', 'KB', 'MB', 'GB', 'TB'][i]}`;
    }

    function escapeHtml(unsafe) {
        return unsafe.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    // --- Run Initialization ---
    initializePage();
});