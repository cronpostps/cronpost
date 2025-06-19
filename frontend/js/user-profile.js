// /frontend/js/user-profile.js
// version 2.7
// - Refactored PIN-required actions (Security Options, Remove PIN) to align with the updated utils.js v1.5 helper function.
// - Simplified apiCallback and try...catch blocks for these actions to fix "response.json is not a function" error.

console.log("--- user-profile.js SCRIPT STARTED (v2.7) ---");

document.addEventListener('DOMContentLoaded', async () => {
    // {* Token handling - No change *}
    const url = new URL(window.location.href);
    const tokenFromUrl = url.searchParams.get("token");
    if (tokenFromUrl) {
        localStorage.setItem('accessToken', tokenFromUrl);
        url.searchParams.delete("token");
        window.history.replaceState({}, document.title, url.toString());
    }
    if (!localStorage.getItem('accessToken')) {
        console.error("No access token found. The first API call will trigger a redirect if needed.");
    }

    // --- STATE MANAGEMENT ---
    let userHasPin = false;

    // --- DOM Element References (No changes) ---
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
    const recoverPinLink = document.getElementById('recoverPinLink');
    const removePinLink = document.getElementById('removePinLink');
    const securityOptionsForm = document.getElementById('securityOptionsForm');
    const securityOptionsStatus = document.getElementById('securityOptionsStatus');
    const usePinForAllActionsToggle = document.getElementById('usePinForAllActions');
    const checkinOptionsForm = document.getElementById('checkinOptionsForm');
    const checkinOptionsStatus = document.getElementById('checkinOptionsStatus');
    const checkinOnSigninToggle = document.getElementById('checkinOnSignin');
    const useCheckinTokenEmailToggle = document.getElementById('useCheckinTokenEmail');
    const premiumReminderOption = document.getElementById('premiumReminderOption');
    const sendAdditionalReminderToggle = document.getElementById('sendAdditionalReminder');
    const additionalReminderInputContainer = document.getElementById('additionalReminderInputContainer');
    const additionalReminderMinutesInput = document.getElementById('additionalReminderMinutes');
    const smtpSettingsForm = document.getElementById('smtpSettingsForm');
    const smtpStatusBadge = document.getElementById('smtpStatusBadge');
    const smtpServerInput = document.getElementById('smtpServer');
    const smtpPortSelect = document.getElementById('smtpPort');
    const smtpSenderEmailInput = document.getElementById('smtpSenderEmail');
    const smtpPasswordInput = document.getElementById('smtpPassword');
    const removeSmtpSettingsButton = document.getElementById('removeSmtpSettings');
    const smtpSettingsStatus = document.getElementById('smtpSettingsStatus');
    const reviewForm = document.getElementById('reviewForm');
    const reviewCommentTextarea = document.getElementById('reviewComment');
    const reviewSubmitStatus = document.getElementById('reviewSubmitStatus');
    const membershipTypeSpan = document.getElementById('membershipType');
    const upgradeButton = document.getElementById('upgradeButton');
    const premiumUserText = document.getElementById('premiumUserText');
    const messagesRemainingSpan = document.getElementById('messagesRemaining');
    const storageUsageBar = document.getElementById('storageUsageBar');
    const storageUsageText = document.getElementById('storageUsageText');
    const accessHistoryTableBody = document.getElementById('accessHistoryTableBody');

    // --- Helper Functions (No changes) ---
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
                const offset = (typeof getIanaTimezoneOffsetMinutes === 'function') ? getIanaTimezoneOffsetMinutes(tz) : 0;
                const label = (typeof formatGmtOffset === 'function') ? `[${formatGmtOffset(offset)}] - ${tz}` : tz;
                return { iana: tz, offset, label };
            });
            timezoneData.sort((a, b) => a.offset - b.offset);
            timezoneSelect.innerHTML = '';
            const defaultOption = document.createElement('option');
            defaultOption.value = "";
            defaultOption.textContent = "Select your timezone";
            defaultOption.disabled = true; defaultOption.selected = true;
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
                <td>${entry.device_os || 'Unknown'}</td>
            `;
            accessHistoryTableBody.appendChild(tr);
        });
    }

    // --- DATA FETCHING (No changes in logic) ---
    async function fetchAndPopulateReview() {
        if (!reviewForm) return;
        try {
            const response = await fetchWithAuth('/api/users/review');
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

    async function fetchAndPopulateSmtpData() {
        if (!smtpSettingsForm) return;
        try {
            const response = await fetchWithAuth('/api/users/smtp-settings');
            if (response.ok) {
                const smtpData = await response.json();
                smtpServerInput.value = smtpData.smtp_server;
                smtpPortSelect.value = smtpData.smtp_port;
                smtpSenderEmailInput.value = smtpData.smtp_sender_email;
                smtpStatusBadge.textContent = smtpData.is_active ? 'Active' : 'Inactive - Test Required';
                smtpStatusBadge.className = `badge ${smtpData.is_active ? 'bg-success' : 'bg-warning text-dark'}`;
                removeSmtpSettingsButton.style.display = 'inline-block';
            } else if (response.status === 404) {
                smtpStatusBadge.textContent = 'Not Configured';
                smtpStatusBadge.className = 'badge bg-secondary';
                removeSmtpSettingsButton.style.display = 'none';
            } else { 
                displayStatusMessage("Could not load SMTP settings.", false, smtpSettingsStatus); 
            }
        } catch (error) {
            console.error("Error fetching SMTP settings:", error);
            displayStatusMessage("Network error loading SMTP settings.", false, smtpSettingsStatus);
        }
    }

    async function fetchAndDisplayAccessHistory(userTimezone) {
        if (!accessHistoryTableBody) return;
        try {
            const response = await fetchWithAuth('/api/users/access-history');
            if (response.ok) {
                populateAccessHistoryTable(await response.json(), userTimezone);
            } else {
                accessHistoryTableBody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">Error loading history.</td></tr>';
            }
        } catch (error) {
            console.error("Error fetching access history:", error);
            accessHistoryTableBody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">Network error loading history.</td></tr>';
        }
    }

    async function fetchAndPopulateCheckinSettings() {
        if (!checkinOptionsForm) return;
        try {
            const response = await fetchWithAuth('/api/users/checkin-settings');
            if (response.ok) {
                const settings = await response.json();
                checkinOnSigninToggle.checked = settings.checkin_on_signin || false;
                useCheckinTokenEmailToggle.checked = settings.use_checkin_token_email || false;
                sendAdditionalReminderToggle.checked = settings.send_additional_reminder || false;
                additionalReminderMinutesInput.value = settings.additional_reminder_minutes || 5;
                sendAdditionalReminderToggle.dispatchEvent(new Event('change'));
            } else if (response.status !== 404) { 
                console.warn("Could not fetch check-in settings:", response.status); 
            }
        } catch (error) { 
            console.error("Error fetching check-in settings:", error); 
        }
    }
    
    async function fetchAndPopulateUserData() {
        populateTimezoneSelect();
        try {
            const response = await fetchWithAuth('/api/users/me');
            if (!response.ok) {
                // If the initial fetch fails, it's likely a session issue.
                // fetchWithAuth will handle redirection if it's a 401.
                // For other errors, we display a message.
                const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch user data.' }));
                throw new Error(errorData.detail);
            }
            
            const data = await response.json();
            
            userHasPin = data.has_pin || false;
            emailInput.value = data.email;
            userNameInput.value = data.user_name || '';
            trustVerifierEmailInput.value = data.trust_verifier_email || '';
            document.getElementById('pinQuestion').value = data.pin_code_question || '';
            
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
            
            usePinForAllActionsToggle.checked = data.use_pin_for_all_actions;
            
            membershipTypeSpan.textContent = data.membership_type.charAt(0).toUpperCase() + data.membership_type.slice(1);
            if (data.membership_type === 'premium') {
                upgradeButton.style.display = 'none';
                premiumUserText.style.display = 'block';
                if (premiumReminderOption) premiumReminderOption.style.display = 'block';
            } else {
                upgradeButton.style.display = 'block';
                premiumUserText.style.display = 'none';
                if (premiumReminderOption) premiumReminderOption.style.display = 'none';
            }
            
            messagesRemainingSpan.textContent = data.messages_remaining !== null ? data.messages_remaining : 'N/A';
            const storageLimitBytes = (data.storage_limit_gb || 0) * 1024 * 1024 * 1024;
            const storageUsedBytes = data.uploaded_storage_bytes || 0;
            const usagePercent = storageLimitBytes > 0 ? (storageUsedBytes / storageLimitBytes) * 100 : 0;
            storageUsageBar.style.width = `${usagePercent}%`;
            storageUsageBar.setAttribute('aria-valuenow', usagePercent);
            storageUsageText.textContent = `${(storageUsedBytes / (1024 * 1024)).toFixed(2)} MB / ${data.storage_limit_gb || 0} GB`;

            await Promise.all([
                fetchAndPopulateReview(),
                fetchAndDisplayAccessHistory(userTimezone),
                fetchAndPopulateSmtpData(),
                fetchAndPopulateCheckinSettings()
            ]);

        } catch (error) {
            console.error("Critical error fetching user data:", error);
            // Avoid showing generic errors if it's a session expiry being handled by redirection
            if (!error.message.includes('Session expired')) {
                displayStatusMessage(`Error: ${error.message}`, false, formStatusMessage);
            }
        }
    }
    
    // --- Event Listeners ---
    
    if (showPasswordToggle) { showPasswordToggle.addEventListener('change', () => { const isChecked = showPasswordToggle.checked; document.getElementById('currentPassword').type = isChecked ? 'text' : 'password'; document.getElementById('newPassword').type = isChecked ? 'text' : 'password'; document.getElementById('confirmNewPassword').type = isChecked ? 'text' : 'password'; }); }
    if (showPinToggle) { showPinToggle.addEventListener('change', () => { const isChecked = showPinToggle.checked; document.getElementById('currentPin').type = isChecked ? 'text' : 'password'; document.getElementById('newPin').type = isChecked ? 'text' : 'password'; document.getElementById('confirmNewPin').type = isChecked ? 'text' : 'password'; }); }

    if (profileForm) {
        profileForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(profileForm, true, 'Saving...');
            try {
                const payload = { user_name: userNameInput.value, timezone: timezoneSelect.value, trust_verifier_email: trustVerifierEmailInput.value || null };
                const response = await fetchWithAuth('/api/users/profile', { method: 'PUT', body: JSON.stringify(payload) });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to save profile.');
                displayStatusMessage("Profile saved successfully! Page will reload...", true, profileFormStatus);
                setTimeout(() => { location.reload(); }, 1500);
            } catch (error) {
                console.error("Error saving profile:", error);
                if (error.message !== 'Session expired.' && error.message !== 'Request failed with status 401') {
                    displayStatusMessage(`Error: ${error.message}`, false, profileFormStatus);
                }
            } finally {
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
                // {* Changed method to PUT *}
                const response = await fetchWithAuth('/api/users/change-password', { 
                    method: 'PUT', 
                    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) 
                });
                if (!response.ok) { const result = await response.json(); throw new Error(result.detail || 'Failed to update password.'); }
                displayStatusMessage('Password updated successfully! Reloading...', true, passwordChangeStatus);
                setTimeout(() => { location.reload(); }, 1500);
            } catch (error) {
                console.error("Error changing password:", error);
                if (error.message !== 'Session expired.' && error.message !== 'Request failed with status 401') {
                    displayStatusMessage(`Error: ${error.message}`, false, passwordChangeStatus);
                }
            } finally {
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
                
                const response = await fetchWithAuth('/api/users/change-pin', {
                    method: 'POST',
                    body: JSON.stringify({
                        current_pin: currentPin || null,
                        new_pin: newPin,
                        pin_question: pinQuestion || null
                    })
                });

                // {* Throw the entire error object on failure for the catch block to inspect *}
                if (!response.ok) {
                    const errorData = await response.json();
                    throw errorData;
                }
                
                const result = await response.json();
                displayStatusMessage(result.message + ' Reloading...', true, pinChangeStatus);
                setTimeout(() => { location.reload(); }, 1500);

            } catch (error) {
                console.error("Error changing PIN:", error);
                const errorDetail = error.detail || error;

                // {* Smartly handle the error object from the backend *}
                if (typeof errorDetail === 'object' && errorDetail.type === 'account_locked') {
                    const timeStr = formatSecondsToHms(errorDetail.remaining_seconds);
                    const finalMessage = `${errorDetail.message} You will be redirected to the dashboard. Please try again in ${timeStr}.`;
                    alert(finalMessage);
                    window.location.href = '/dashboard';
                } else {
                    // {* Handle other errors (string or object with a message) *}
                    const message = errorDetail.message || errorDetail.toString();
                    displayStatusMessage(`Error: ${message}`, false, pinChangeStatus);
                }
            } finally {
                if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(pinChangeForm, false);
            }
        });
    }

    if (securityOptionsForm) {
        securityOptionsForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            if (usePinForAllActionsToggle.checked && !userHasPin) {
                displayStatusMessage("You must create a PIN before you can enable this option.", false, securityOptionsStatus);
                usePinForAllActionsToggle.checked = false;
                return;
            }

            if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(securityOptionsForm, true, 'Saving...');
            
            try {
                let result;
                // This action requires a PIN only if the user has one.
                if (userHasPin) {
                    const apiCallback = async (pin) => {
                        return await fetchWithAuth('/api/users/security-options', {
                            method: 'PUT',
                            body: JSON.stringify({
                                use_pin_for_all_actions: usePinForAllActionsToggle.checked,
                                pin_code: pin
                            })
                        });
                    };
                    result = await executeActionWithPinVerification("Please enter your PIN to confirm changes", apiCallback);
                } else {
                    const payload = { use_pin_for_all_actions: usePinForAllActionsToggle.checked };
                    const response = await fetchWithAuth('/api/users/security-options', {
                        method: 'PUT',
                        body: JSON.stringify(payload)
                    });
                    result = await response.json();
                    if (!response.ok) {
                        throw new Error(result.detail || 'Failed to save settings.');
                    }
                }

                // Handle success (this code runs only if the action succeeds)
                displayStatusMessage("Security options saved successfully! Reloading...", true, securityOptionsStatus);
                setTimeout(() => { location.reload(); }, 1500);

            } catch (error) {
                // Handle cancellation or other unexpected errors
                if (error.message.includes('cancelled')) {
                    console.log('Action cancelled by user.');
                    displayStatusMessage('Action cancelled.', false, securityOptionsStatus);
                } else {
                    console.error("Error saving security options:", error);
                    displayStatusMessage(`Error: ${error.message}`, false, securityOptionsStatus);
                }
            } finally {
                if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(securityOptionsForm, false);
            }
        });
    }

    if (checkinOptionsForm) {
        checkinOptionsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(checkinOptionsForm, true, 'Saving...');
            try {
                const payload = { checkin_on_signin: checkinOnSigninToggle.checked, use_checkin_token_email: useCheckinTokenEmailToggle.checked, send_additional_reminder: sendAdditionalReminderToggle.checked, additional_reminder_minutes: parseInt(additionalReminderMinutesInput.value, 10) || 5 };
                const response = await fetchWithAuth('/api/users/checkin-settings', { method: 'PUT', body: JSON.stringify(payload) });
                if (!response.ok) { const errorResult = await response.json(); throw new Error(errorResult.detail || 'Failed to save check-in options.'); }
                displayStatusMessage("Check-in options saved successfully! Page will reload...", true, checkinOptionsStatus);
                setTimeout(() => { location.reload(); }, 1500);
            } catch (error) {
                console.error("Error saving check-in options:", error);
                if (error.message !== 'Session expired.' && error.message !== 'Request failed with status 401') {
                    displayStatusMessage(`Error: ${error.message}`, false, checkinOptionsStatus);
                }
            } finally {
                if (typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(checkinOptionsForm, false);
            }
        });
    }

    if (sendAdditionalReminderToggle) {
        sendAdditionalReminderToggle.addEventListener('change', () => {
            if (additionalReminderInputContainer) { additionalReminderInputContainer.style.display = sendAdditionalReminderToggle.checked ? 'block' : 'none'; }
        });
    }

    if (reviewForm) {
        reviewForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if(typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(reviewForm, true, 'Submitting...');
            try {
                const selectedRating = reviewForm.querySelector('input[name="rating"]:checked');
                if (!selectedRating) throw new Error('Please select a rating.');
                const payload = { rating_points: `_${selectedRating.value}`, comment: reviewCommentTextarea.value || null };
                const response = await fetchWithAuth('/api/users/review', { method: 'PUT', body: JSON.stringify(payload) });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to submit review.');
                displayStatusMessage('Thank you for your feedback!', true, reviewSubmitStatus);
            } catch (error) {
                console.error("Error submitting review:", error);
                if (error.message !== 'Session expired.' && error.message !== 'Request failed with status 401') {
                    displayStatusMessage(`Error: ${error.message}`, false, reviewSubmitStatus);
                }
            } finally {
                if(typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(reviewForm, false);
            }
        });
    }
    
    // --- Updated PIN recovery link handler ---
    if(recoverPinLink) {
        recoverPinLink.addEventListener('click', async (e) => {
            e.preventDefault();
            const recoveryCode = prompt("Please enter your PIN recovery code:");
            if (!recoveryCode) {
                displayStatusMessage("PIN recovery cancelled.", false, pinChangeStatus);
                return;
            }
            const newPin = prompt("Enter your new 4-digit PIN:");
            if (!newPin || !/^\d{4}$/.test(newPin)) { 
                displayStatusMessage("Invalid PIN format. Please enter a 4-digit PIN.", false, pinChangeStatus); 
                return; 
            }
            const confirmNewPin = prompt("Confirm your new 4-digit PIN:");
            if (newPin !== confirmNewPin) { 
                displayStatusMessage("The new PINs do not match.", false, pinChangeStatus); 
                return; 
            }
            
            displayStatusMessage("Attempting PIN recovery...", false, pinChangeStatus);
            try {
                const response = await fetchWithAuth('/api/users/recover-pin', {
                    method: 'POST',
                    body: JSON.stringify({ recovery_code: recoveryCode, new_pin: newPin })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'PIN recovery failed.');
                displayStatusMessage(result.message + ' Reloading...', true, pinChangeStatus);
                setTimeout(() => { location.reload(); }, 1500);
            } catch (error) { 
                console.error("Error during PIN recovery:", error);
                if (error.message !== 'Session expired.' && error.message !== 'Request failed with status 401') {
                    displayStatusMessage(`Error: ${error.message}`, false, pinChangeStatus); 
                }
            }
        });
    }

    // --- Updated remove PIN link handler ---
    if (removePinLink) {
        removePinLink.addEventListener('click', async (e) => {
            e.preventDefault();
            if (!userHasPin) {
                displayStatusMessage("You have not set a PIN yet.", false, pinChangeStatus);
                return;
            }
            
            try {
                const apiCallback = async (pin) => {
                    return await fetchWithAuth('/api/users/pin', {
                        method: 'DELETE',
                        body: JSON.stringify({ pin_code: pin })
                    });
                };

                await executeActionWithPinVerification("To remove your PIN, please enter your current PIN for confirmation:", apiCallback);

                displayStatusMessage("PIN successfully removed! The page will now reload.", true, pinChangeStatus);
                setTimeout(() => { location.reload(); }, 2000);

            } catch (error) {
                if (error.message.includes('cancelled')) {
                    console.log('PIN removal cancelled by user.');
                    displayStatusMessage('Action cancelled.', false, pinChangeStatus);
                } else {
                    console.error("Error removing PIN:", error);
                    displayStatusMessage(`Error: ${error.message}`, false, pinChangeStatus);
                }
            }
        });
    }

    if (smtpSettingsForm) {
        smtpSettingsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if(typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(smtpSettingsForm, true, 'Testing & Saving...');
            try {
                const payload = { smtp_server: smtpServerInput.value, smtp_port: parseInt(smtpPortSelect.value, 10), smtp_sender_email: smtpSenderEmailInput.value, smtp_password: smtpPasswordInput.value };
                const response = await fetchWithAuth('/api/users/smtp-settings', { method: 'PUT', body: JSON.stringify(payload) });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to save SMTP settings.');
                displayStatusMessage('SMTP settings saved and connection successful! Reloading...', true, smtpSettingsStatus);
                setTimeout(() => { location.reload(); }, 2000);
            } catch (error) {
                console.error("Error saving SMTP settings:", error);
                if (error.message !== 'Session expired.' && error.message !== 'Request failed with status 401') {
                    displayStatusMessage(`Error: ${error.message}`, false, smtpSettingsStatus);
                }
            } finally {
                if(typeof toggleFormElementsDisabled === "function") toggleFormElementsDisabled(smtpSettingsForm, false);
            }
        });
    }
    
    if (removeSmtpSettingsButton) {
        removeSmtpSettingsButton.addEventListener('click', async () => {
            if (!confirm("Are you sure you want to remove your custom SMTP settings?")) return;
            displayStatusMessage('Removing settings...', true, smtpSettingsStatus);
            try {
                 const response = await fetchWithAuth('/api/users/smtp-settings', { method: 'DELETE' });
                if (!response.ok) { const result = await response.json(); throw new Error(result.detail || 'Failed to remove settings.'); }
                displayStatusMessage('Settings removed successfully! Reloading...', true, smtpSettingsStatus);
                setTimeout(() => { location.reload(); }, 1500);
            } catch (error) { 
                console.error("Error removing SMTP settings:", error);
                if (error.message !== 'Session expired.' && error.message !== 'Request failed with status 401') {
                    displayStatusMessage(`Error: ${error.message}`, false, smtpSettingsStatus); 
                }
            }
        });
    }

    // --- Initial Load ---
    await fetchAndPopulateUserData();
    console.log("--- user-profile.js SCRIPT ENDED (v2.7) ---");
});