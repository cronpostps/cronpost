// /frontend/js/user-profile.js
// version 1.14 (Integrate SMTP settings form logic)
// Changelog:
// - Added logic to fetch, display, update, and remove user's custom SMTP settings.
// - All forms now display status messages in their own section.
// - All successful submissions will now auto-reload the page for consistency.
// - All PIN-related logic and checks are fully integrated.

console.log("--- user-profile.js SCRIPT STARTED (v1.14) ---");

document.addEventListener('DOMContentLoaded', () => {
    console.log("--- user-profile.js DOMContentLoaded ---");
    let userHasPin = false; 
    const accessToken = localStorage.getItem('accessToken');
    if (!accessToken) {
        console.error("No access token found. Redirecting to signin.");
        window.location.href = '/signin.html?status=session_expired';
        return;
    }

    // --- DOM element references ---
    const formStatusMessage = document.getElementById('formStatusMessage');
    const profileForm = document.getElementById('profileForm');
    const profileFormStatus = document.getElementById('profileFormStatus');
    const emailInput = document.getElementById('email');
    const userNameInput = document.getElementById('userName');
    const timezoneSelect = document.getElementById('timezone');
    const trustVerifierEmailInput = document.getElementById('trustVerifierEmail');

    const passwordChangeForm = document.getElementById('passwordChangeForm');
    const passwordChangeStatus = document.getElementById('passwordChangeStatus');
    const showPasswordToggle = document.getElementById('showPasswordToggle');
    
    const pinChangeForm = document.getElementById('pinChangeForm');
    const pinChangeStatus = document.getElementById('pinChangeStatus');
    const showPinToggle = document.getElementById('showPinToggle');
    
    const securityOptionsForm = document.getElementById('securityOptionsForm');
    const securityOptionsStatus = document.getElementById('securityOptionsStatus');
    const usePinForAllActionsToggle = document.getElementById('usePinForAllActions');
    const checkinOnSigninToggle = document.getElementById('checkinOnSignin');

    // NEW: SMTP Form Elements
    const smtpSettingsForm = document.getElementById('smtpSettingsForm');
    const smtpStatusBadge = document.getElementById('smtpStatusBadge');
    const smtpServerInput = document.getElementById('smtpServer');
    const smtpPortSelect = document.getElementById('smtpPort');
    const smtpSenderEmailInput = document.getElementById('smtpSenderEmail');
    const smtpPasswordInput = document.getElementById('smtpPassword');
    const removeSmtpSettingsButton = document.getElementById('removeSmtpSettings');
    const smtpSettingsStatus = document.getElementById('smtpSettingsStatus');

    const membershipTypeSpan = document.getElementById('membershipType');
    const upgradeButton = document.getElementById('upgradeButton');
    const premiumUserText = document.getElementById('premiumUserText');
    const messagesRemainingSpan = document.getElementById('messagesRemaining');
    const storageUsageBar = document.getElementById('storageUsageBar');
    const storageUsageText = document.getElementById('storageUsageText');
    const accessHistoryTableBody = document.getElementById('accessHistoryTableBody');
    const recoverPinLink = document.getElementById('recoverPinLink');
    const removePinLink = document.getElementById('removePinLink');
    
    const reviewForm = document.getElementById('reviewForm');
    const reviewCommentTextarea = document.getElementById('reviewComment');
    const reviewSubmitStatus = document.getElementById('reviewSubmitStatus');

    // --- Helper Functions ---
    function displayStatusMessage(message, isSuccess, element) {
        const targetElement = element || formStatusMessage;
        if (typeof displayGeneralFormMessage === "function") {
            displayGeneralFormMessage(targetElement, message, isSuccess);
        } else {
            alert(message);
        }
    }

    function populateTimezoneSelect() {
        if (!timezoneSelect) return;
        try {
            const allTimezones = Intl.supportedValuesOf('timeZone');
            const timezoneData = allTimezones.map(tz => {
                const offset = getIanaTimezoneOffsetMinutes(tz);
                return {
                    iana: tz,
                    offset: offset,
                    label: `[${formatGmtOffset(offset)}] - ${tz}`
                };
            });
            timezoneData.sort((a, b) => a.offset - b.offset);
            timezoneSelect.innerHTML = '';
            const defaultOption = document.createElement('option');
            defaultOption.value = "";
            defaultOption.textContent = "Select your timezone";
            defaultOption.disabled = true;
            defaultOption.selected = true;
            timezoneSelect.appendChild(defaultOption);
            timezoneData.forEach(tzInfo => {
                const option = document.createElement('option');
                option.value = tzInfo.iana;
                option.textContent = tzInfo.label;
                timezoneSelect.appendChild(option);
            });
        } catch (e) {
            console.error("Could not get timezones from Intl API.", e);
        }
    }

    function populateAccessHistoryTable(history, userTimezone) {
        if (!accessHistoryTableBody) return;
        accessHistoryTableBody.innerHTML = '';
        if (!history || history.length === 0) {
            accessHistoryTableBody.innerHTML = '<tr><td colspan="3" class="text-center">No history found.</td></tr>';
            return;
        }
        const recordsToDisplay = history.slice(0, 10);
        recordsToDisplay.forEach(entry => {
            const tr = document.createElement('tr');
            const loginTime = formatTimestampInZone(entry.login_time, userTimezone);
            tr.innerHTML = `
                <td>${loginTime}</td>
                <td>${entry.ip_address || 'N/A'}</td>
                <td>${entry.user_agent ? entry.user_agent.substring(0, 30) + '...' : 'N/A'}</td>
            `;
            accessHistoryTableBody.appendChild(tr);
        });
    }

    async function fetchAndPopulateReview() {
        if (!reviewForm) return;
        try {
            const response = await fetch('/api/users/review', { headers: { 'Authorization': `Bearer ${accessToken}` } });
            if (response.ok) {
                const reviewData = await response.json();
                if (reviewData) {
                    reviewCommentTextarea.value = reviewData.comment || '';
                    if (reviewData.rating_points) {
                        const ratingValue = reviewData.rating_points.replace('_', '');
                        const ratingInput = document.getElementById(`rating_${ratingValue}`);
                        if (ratingInput) ratingInput.checked = true;
                    }
                }
            } else if (response.status !== 404) {
                console.warn("Could not fetch user review:", response.status);
            }
        } catch (error) {
            console.error("Error fetching user review:", error);
        }
    }
    
    // NEW: Fetch and populate SMTP data
    async function fetchAndPopulateSmtpData() {
        if (!smtpSettingsForm) return;
        try {
            const response = await fetch('/api/users/smtp-settings', {
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
            if (response.ok) {
                const smtpData = await response.json();
                if (smtpData.smtp_server) {
                    smtpServerInput.value = smtpData.smtp_server;
                    smtpPortSelect.value = smtpData.smtp_port;
                    smtpSenderEmailInput.value = smtpData.smtp_sender_email;
                    // Do not populate password field
                    if (smtpData.is_active) {
                        smtpStatusBadge.textContent = 'Active';
                        smtpStatusBadge.className = 'badge bg-success';
                    } else {
                        smtpStatusBadge.textContent = 'Inactive - Test Required';
                        smtpStatusBadge.className = 'badge bg-warning text-dark';
                    }
                    removeSmtpSettingsButton.style.display = 'inline-block';
                }
            } else if (response.status !== 404) {
                displayStatusMessage("Could not load SMTP settings.", false, smtpSettingsStatus);
            }
        } catch (error) {
            console.error("Error fetching SMTP settings:", error);
            displayStatusMessage("Network error loading SMTP settings.", false, smtpSettingsStatus);
        }
    }


    async function fetchAndDisplayAccessHistory() {
        if (!accessHistoryTableBody) return;
        const userTimezone = timezoneSelect.value;
        if (!userTimezone) {
            console.warn("User timezone not available yet for history formatting.");
        }
        try {
            const response = await fetch('/api/users/access-history', { headers: { 'Authorization': `Bearer ${accessToken}` } });
            if (response.ok) {
                const historyData = await response.json();
                populateAccessHistoryTable(historyData, userTimezone);
            } else {
                accessHistoryTableBody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">Error loading history.</td></tr>';
            }
        } catch (error) {
            console.error("Error fetching access history:", error);
            accessHistoryTableBody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">Network error loading history.</td></tr>';
        }
    }

    async function fetchAndPopulateUserData() {
        populateTimezoneSelect();
        try {
            const response = await fetch('/api/users/me', { headers: { 'Authorization': `Bearer ${accessToken}` } });
            if (response.status === 401) { window.location.href = '/signin.html?status=session_expired'; return; }
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch user data.' }));
                throw new Error(errorData.detail || `Status: ${response.status}`);
            }
            const data = await response.json();
            
            userHasPin = data.has_pin || false;
            emailInput.value = data.email;
            userNameInput.value = data.user_name || '';
            const userTimezone = data.timezone || 'Etc/UTC';
            if ([...timezoneSelect.options].some(opt => opt.value === userTimezone)) {
                timezoneSelect.value = userTimezone;
            } else {
                const option = document.createElement('option');
                option.value = userTimezone;
                option.textContent = `[Saved] - ${userTimezone}`;
                timezoneSelect.prepend(option);
                timezoneSelect.value = userTimezone;
            }
            trustVerifierEmailInput.value = data.trust_verifier_email || '';
            document.getElementById('pinQuestion').value = data.pin_code_question || '';
            usePinForAllActionsToggle.checked = data.use_pin_for_all_actions;
            checkinOnSigninToggle.checked = data.checkin_on_signin || false;
            
            membershipTypeSpan.textContent = data.membership_type.charAt(0).toUpperCase() + data.membership_type.slice(1);
            if (data.membership_type === 'free') {
                upgradeButton.style.display = 'block';
                premiumUserText.style.display = 'none';
            } else {
                upgradeButton.style.display = 'none';
                premiumUserText.style.display = 'block';
            }
            messagesRemainingSpan.textContent = data.messages_remaining !== null ? data.messages_remaining : 'N/A';
            const storageLimitBytes = (data.storage_limit_gb || 0) * 1024 * 1024 * 1024;
            const storageUsedBytes = data.uploaded_storage_bytes || 0;
            const usagePercent = storageLimitBytes > 0 ? (storageUsedBytes / storageLimitBytes) * 100 : 0;
            storageUsageBar.style.width = `${usagePercent}%`;
            storageUsageBar.setAttribute('aria-valuenow', usagePercent);
            storageUsageText.textContent = `${(storageUsedBytes / (1024 * 1024)).toFixed(2)} MB / ${data.storage_limit_gb || 0} GB`;

            fetchAndPopulateReview();
            fetchAndDisplayAccessHistory();
            fetchAndPopulateSmtpData(); // NEW: Fetch SMTP data
        } catch (error) {
            console.error("Error fetching or populating user data:", error);
            displayStatusMessage(`Error: ${error.message}`, false, formStatusMessage);
        }
    }
    
    // --- Event Listeners ---
    
    if (showPasswordToggle) {
        showPasswordToggle.addEventListener('change', () => {
            const isChecked = showPasswordToggle.checked;
            document.getElementById('currentPassword').type = isChecked ? 'text' : 'password';
            document.getElementById('newPassword').type = isChecked ? 'text' : 'password';
            document.getElementById('confirmNewPassword').type = isChecked ? 'text' : 'password';
        });
    }

    if (showPinToggle) {
        showPinToggle.addEventListener('change', () => {
            const isChecked = showPinToggle.checked;
            document.getElementById('currentPin').type = isChecked ? 'text' : 'password';
            document.getElementById('newPin').type = isChecked ? 'text' : 'password';
            document.getElementById('confirmNewPin').type = isChecked ? 'text' : 'password';
        });
    }

    if (profileForm) {
        profileForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(profileForm, true, 'Saving...');
            try {
                const payload = {
                    user_name: userNameInput.value,
                    timezone: timezoneSelect.value,
                    trust_verifier_email: trustVerifierEmailInput.value || null
                };
                const response = await fetch('/api/users/profile', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
                    body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to save profile.');
                
                displayStatusMessage("Profile saved successfully! Page will reload...", true, profileFormStatus);
                setTimeout(() => { location.reload(); }, 1500);
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, profileFormStatus);
                if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(profileForm, false);
            }
        });
    }

    if (passwordChangeForm) {
        passwordChangeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(passwordChangeForm, true, 'Updating...');
            try {
                const currentPassword = document.getElementById('currentPassword').value;
                const newPassword = document.getElementById('newPassword').value;
                const confirmNewPassword = document.getElementById('confirmNewPassword').value;
                if (newPassword !== confirmNewPassword) throw new Error('New passwords do not match.');
                const response = await fetch('/api/users/change-password', {
                    method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` }, body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
                });
                if (!response.ok) {
                    const result = await response.json();
                    throw new Error(result.detail || 'Failed to update password.');
                }
                
                displayStatusMessage('Password updated successfully! Reloading...', true, passwordChangeStatus);
                setTimeout(() => { location.reload(); }, 1500);
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, passwordChangeStatus);
                if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(passwordChangeForm, false);
            }
        });
    }
    
    if (pinChangeForm) {
        pinChangeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(pinChangeForm, true, 'Updating...');
            try {
                const currentPin = document.getElementById('currentPin').value;
                const newPin = document.getElementById('newPin').value;
                const confirmNewPin = document.getElementById('confirmNewPin').value;
                if (newPin !== confirmNewPin) throw new Error("New PINs do not match.");
                const pinQuestion = document.getElementById('pinQuestion').value;
                const response = await fetch('/api/users/change-pin', {
                    method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` }, body: JSON.stringify({ current_pin: currentPin || null, new_pin: newPin, pin_question: pinQuestion || null })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to update PIN.');
                
                displayStatusMessage(result.message + ' Reloading...', true, pinChangeStatus);
                setTimeout(() => { location.reload(); }, 1500);
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, pinChangeStatus);
                if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(pinChangeForm, false);
            }
        });
    }

    if (securityOptionsForm) {
        securityOptionsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if ((usePinForAllActionsToggle.checked || checkinOnSigninToggle.checked) && !userHasPin) {
                displayStatusMessage("You must create a PIN before you can enable these options.", false, securityOptionsStatus);
                if (usePinForAllActionsToggle.checked) usePinForAllActionsToggle.checked = false;
                if (checkinOnSigninToggle.checked) checkinOnSigninToggle.checked = false;
                return;
            }
            
            let enteredPin = null;
            if (userHasPin) {
                enteredPin = prompt("Please enter your 4-digit PIN to confirm these changes:");
                if (enteredPin === null) {
                    displayStatusMessage("Action cancelled by user.", false, securityOptionsStatus);
                    return; 
                }
                if (!/^\d{4}$/.test(enteredPin)) {
                    displayStatusMessage("Invalid PIN format. Changes were not saved.", false, securityOptionsStatus);
                    return;
                }
            }

            if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(securityOptionsForm, true, 'Saving...');
            try {
                const payload = { 
                    use_pin_for_all_actions: usePinForAllActionsToggle.checked, 
                    checkin_on_signin: checkinOnSigninToggle.checked,
                    pin_code: enteredPin
                };
                const response = await fetch('/api/users/security-options', {
                    method: 'PUT', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` }, body: JSON.stringify(payload)
                });
                if (!response.ok) {
                    const errorResult = await response.json();
                    throw new Error(errorResult.detail || 'Failed to save options.');
                }
                
                displayStatusMessage("Security options saved successfully! Reloading...", true, securityOptionsStatus);
                setTimeout(() => { location.reload(); }, 1500);
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, securityOptionsStatus);
                if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(securityOptionsForm, false);
            }
        });
    }

    if (reviewForm) {
        reviewForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            toggleFormElementsDisabled(reviewForm, true, 'Submitting...');
            try {
                const selectedRating = reviewForm.querySelector('input[name="rating"]:checked');
                if (!selectedRating) throw new Error('Please select a rating.');
                const payload = { rating_points: `_${selectedRating.value}`, comment: reviewCommentTextarea.value || null };
                const response = await fetch('/api/users/review', {
                    method: 'PUT', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` }, body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to submit review.');
                displayStatusMessage('Thank you for your feedback!', true, reviewSubmitStatus);
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, reviewSubmitStatus);
            } finally {
                toggleFormElementsDisabled(reviewForm, false);
            }
        });
    }
    
    if(recoverPinLink) {
        recoverPinLink.addEventListener('click', async (e) => {
            e.preventDefault();
            const recoveryCode = prompt("Please enter your PIN recovery code:");
            if (!recoveryCode) return;
            const newPin = prompt("Enter your new 4-digit PIN:");
            if (!newPin || !/^\d{4}$/.test(newPin)) { alert("Invalid PIN format."); return; }
            const confirmNewPin = prompt("Confirm your new 4-digit PIN:");
            if (newPin !== confirmNewPin) { alert("The new PINs do not match."); return; }
            displayStatusMessage("Attempting PIN recovery...", false, pinChangeStatus);
            try {
                const response = await fetch('/api/users/recover-pin', {
                    method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` }, body: JSON.stringify({ recovery_code: recoveryCode, new_pin: newPin })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'PIN recovery failed.');
                
                displayStatusMessage(result.message + ' Reloading...', true, pinChangeStatus);
                setTimeout(() => { location.reload(); }, 1500);
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, pinChangeStatus);
            }
        });
    }
    
    if (removePinLink) {
        removePinLink.addEventListener('click', async (e) => {
            e.preventDefault();
            if (!userHasPin) {
                displayStatusMessage("You have not set a PIN yet.", false, pinChangeStatus);
                return;
            }
            const enteredPin = prompt("To remove your PIN, please enter your current 4-digit PIN for confirmation:");
            if (enteredPin === null) {
                displayStatusMessage("PIN removal cancelled.", false, pinChangeStatus);
                return;
            }
            if (!/^\d{4}$/.test(enteredPin)) {
                displayStatusMessage("Invalid PIN format. PIN was not removed.", false, pinChangeStatus);
                return;
            }
            displayStatusMessage("Removing PIN...", true, pinChangeStatus);
            try {
                const response = await fetch('/api/users/pin', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
                    body: JSON.stringify({ pin_code: enteredPin })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to remove PIN.');
                
                displayStatusMessage("PIN successfully removed! The page will now reload.", true, pinChangeStatus);
                setTimeout(() => { location.reload(); }, 2000);
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, pinChangeStatus);
            }
        });
    }

    // NEW: SMTP Settings Listeners
    if (smtpSettingsForm) {
        smtpSettingsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            toggleFormElementsDisabled(smtpSettingsForm, true, 'Testing & Saving...');
            try {
                const payload = {
                    smtp_server: smtpServerInput.value,
                    smtp_port: parseInt(smtpPortSelect.value, 10),
                    smtp_sender_email: smtpSenderEmailInput.value,
                    smtp_password: smtpPasswordInput.value
                };

                const response = await fetch('/api/users/smtp-settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
                    body: JSON.stringify(payload)
                });
                
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to save SMTP settings.');

                displayStatusMessage('SMTP settings saved and connection successful! Reloading...', true, smtpSettingsStatus);
                setTimeout(() => { location.reload(); }, 2000);

            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, smtpSettingsStatus);
                toggleFormElementsDisabled(smtpSettingsForm, false);
            }
        });
    }
    
    if (removeSmtpSettingsButton) {
        removeSmtpSettingsButton.addEventListener('click', async () => {
            if (!confirm("Are you sure you want to remove your custom SMTP settings? The system will revert to using CronPost's default email sender.")) {
                return;
            }
            displayStatusMessage('Removing settings...', true, smtpSettingsStatus);
            try {
                 const response = await fetch('/api/users/smtp-settings', {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${accessToken}` }
                });

                if (!response.ok) {
                    const result = await response.json();
                    throw new Error(result.detail || 'Failed to remove settings.');
                }
                displayStatusMessage('Settings removed successfully! Reloading...', true, smtpSettingsStatus);
                setTimeout(() => { location.reload(); }, 1500);

            } catch (error) {
                 displayStatusMessage(`Error: ${error.message}`, false, smtpSettingsStatus);
            }
        });
    }

    // Initial Load
    fetchAndPopulateUserData();
});