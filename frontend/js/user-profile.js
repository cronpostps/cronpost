// /frontend/js/user-profile.js
// version 1.10 (Display Timezone with GMT offset)
// Changelog:
// - Updated timezone display to include GMT offset (e.g., "[GMT +07:00] - Asia/Saigon").

console.log("--- user-profile.js SCRIPT STARTED (v1.10) ---");

document.addEventListener('DOMContentLoaded', () => {
    console.log("--- user-profile.js DOMContentLoaded ---");

    const accessToken = localStorage.getItem('accessToken');
    if (!accessToken) {
        console.error("No access token found. Redirecting to signin.");
        window.location.href = '/signin.html?status=session_expired';
        return;
    }

    // --- DOM element references ---
    const formStatusMessage = document.getElementById('formStatusMessage');
    const profileForm = document.getElementById('profileForm');
    const emailInput = document.getElementById('email');
    const userNameInput = document.getElementById('userName');
    const timezoneSelect = document.getElementById('timezone');
    const trustVerifierEmailInput = document.getElementById('trustVerifierEmail');

    const passwordChangeForm = document.getElementById('passwordChangeForm');
    const showPasswordToggle = document.getElementById('showPasswordToggle');
    
    const pinChangeForm = document.getElementById('pinChangeForm');
    const showPinToggle = document.getElementById('showPinToggle');
    const pinChangeStatus = document.getElementById('pinChangeStatus');
    
    const securityOptionsForm = document.getElementById('securityOptionsForm');
    const usePinForAllActionsToggle = document.getElementById('usePinForAllActions');
    const checkinOnSigninToggle = document.getElementById('checkinOnSignin');
    const membershipTypeSpan = document.getElementById('membershipType');
    const upgradeButton = document.getElementById('upgradeButton');
    const premiumUserText = document.getElementById('premiumUserText');
    const messagesRemainingSpan = document.getElementById('messagesRemaining');
    const storageUsageBar = document.getElementById('storageUsageBar');
    const storageUsageText = document.getElementById('storageUsageText');
    const accessHistoryTableBody = document.getElementById('accessHistoryTableBody');
    const recoverPinLink = document.getElementById('recoverPinLink');
    const reviewForm = document.getElementById('reviewForm');
    const reviewCommentTextarea = document.getElementById('reviewComment');
    const reviewSubmitStatus = document.getElementById('reviewSubmitStatus');

    // --- Helper Functions ---
    function displayStatusMessage(message, isSuccess, element = formStatusMessage) {
        if (typeof displayGeneralFormMessage === "function") {
            displayGeneralFormMessage(element, message, isSuccess);
        } else {
            alert(message);
        }
    }

    // NEW FUNCTION: Format timezone to include GMT offset
    function formatTimezone(ianaTimezone) {
        if (!ianaTimezone) return "Unknown Timezone";
        try {
            const date = new Date();
            const utcDate = new Date(date.toUTCString());
            const localDate = new Date(date.toLocaleString('en-US', { timeZone: ianaTimezone }));
            const offsetMillis = localDate.getTime() - utcDate.getTime();
            const offsetHours = offsetMillis / (1000 * 60 * 60);
            const sign = offsetHours >= 0 ? '+' : '';
            const formattedOffset = `GMT ${sign}${String(Math.floor(offsetHours)).padStart(2, '0')}:${String(Math.abs(Math.round((offsetHours % 1) * 60))).padStart(2, '0')}`;
            return `[${formattedOffset}] - ${ianaTimezone}`;
        } catch (e) {
            console.warn(`Could not format timezone ${ianaTimezone}: ${e}`);
            return ianaTimezone; // Fallback to raw IANA if formatting fails
        }
    }

    function populateTimezoneSelect() {
        if (!timezoneSelect) return;
        try {
            // Use Intl.supportedValuesOf for modern browsers
            const timezones = Intl.supportedValuesOf('timeZone');
            timezoneSelect.innerHTML = '';
            
            // Add a default empty/placeholder option
            const defaultOption = document.createElement('option');
            defaultOption.value = "";
            defaultOption.textContent = "Select your timezone";
            defaultOption.disabled = true;
            defaultOption.selected = true;
            timezoneSelect.appendChild(defaultOption);

            timezones.forEach(tz => {
                const option = document.createElement('option');
                option.value = tz;
                option.textContent = formatTimezone(tz); // Use new formatTimezone function
                timezoneSelect.appendChild(option);
            });
        } catch (e) {
            console.error("Could not get timezones from Intl API. Falling back to hardcoded options.", e);
            timezoneSelect.innerHTML = `
                <option value="">Select your timezone</option>
                <option value="Etc/UTC">[GMT +00:00] - Etc/UTC</option>
                <option value="Asia/Ho_Chi_Minh">[GMT +07:00] - Asia/Ho_Chi_Minh</option>
                <option value="America/New_York">[GMT -04:00] - America/New_York</option>
                <option value="Europe/London">[GMT +01:00] - Europe/London</option>
            `;
        }
    }

    function populateAccessHistoryTable(history) {
        if (!accessHistoryTableBody) return;
        accessHistoryTableBody.innerHTML = '';
        if (!history || history.length === 0) {
            accessHistoryTableBody.innerHTML = '<tr><td colspan="3" class="text-center">No history found.</td></tr>';
            return;
        }
        history.forEach(entry => {
            const tr = document.createElement('tr');
            const loginTime = new Date(entry.login_time).toLocaleString();
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
                        const ratingInput = document.getElementById(`rating${reviewData.rating_points}`);
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

    async function fetchAndDisplayAccessHistory() {
        if (!accessHistoryTableBody) return;
        try {
            const response = await fetch('/api/users/access-history', { headers: { 'Authorization': `Bearer ${accessToken}` } });
            if (response.ok) {
                const historyData = await response.json();
                populateAccessHistoryTable(historyData);
            } else {
                accessHistoryTableBody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">Error loading history.</td></tr>';
            }
        } catch (error) {
            console.error("Error fetching access history:", error);
            accessHistoryTableBody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">Network error loading history.</td></tr>';
        }
    }

    async function fetchAndPopulateUserData() {
        populateTimezoneSelect(); // Populate with formatted timezones
        try {
            const response = await fetch('/api/users/me', { headers: { 'Authorization': `Bearer ${accessToken}` } });
            if (response.status === 401) { window.location.href = '/signin.html?status=session_expired'; return; }
            if (!response.ok) throw new Error(`Failed to fetch user data. Status: ${response.status}`);
            
            const data = await response.json();
            
            emailInput.value = data.email;
            userNameInput.value = data.user_name || '';

            // Set the value of the select directly to the IANA timezone string
            const userTimezone = data.timezone || 'Etc/UTC';
            let timezoneOptionExists = false;
            for (let i = 0; i < timezoneSelect.options.length; i++) {
                if (timezoneSelect.options[i].value === userTimezone) {
                    timezoneOptionExists = true;
                    break;
                }
            }
    
            if (!timezoneOptionExists) {
                console.warn(`User's saved timezone "${userTimezone}" not found in browser's list. Adding it temporarily.`);
                const option = document.createElement('option');
                option.value = userTimezone;
                option.textContent = formatTimezone(userTimezone); // Format the newly added option
                timezoneSelect.prepend(option);
            }
            timezoneSelect.value = userTimezone; // Set the select value to the raw IANA string

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
            storageUsageText.textContent = `${(storageUsedBytes / (1024*1024)).toFixed(2)} MB / ${data.storage_limit_gb || 0} GB`;

            fetchAndPopulateReview();
            fetchAndDisplayAccessHistory();
        } catch (error) {
            console.error("Error fetching or populating user data:", error);
            displayStatusMessage(`Error: ${error.message}`, false);
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
            toggleFormElementsDisabled(profileForm, true, 'Saving...');
            try {
                const payload = {
                    user_name: userNameInput.value,
                    timezone: timezoneSelect.value, // Send IANA timezone string
                    trust_verifier_email: trustVerifierEmailInput.value || null
                };
                const response = await fetch('/api/users/profile', {
                    method: 'PUT', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` }, body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to save profile.');
                displayStatusMessage("Profile saved successfully!", true);
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false);
            } finally {
                toggleFormElementsDisabled(profileForm, false);
            }
        });
    }

    if (passwordChangeForm) {
        passwordChangeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const statusDiv = document.getElementById('passwordChangeStatus');
            toggleFormElementsDisabled(passwordChangeForm, true, 'Updating...');
            try {
                const currentPassword = document.getElementById('currentPassword').value;
                const newPassword = document.getElementById('newPassword').value;
                const confirmNewPassword = document.getElementById('confirmNewPassword').value;
                if (newPassword !== confirmNewPassword) throw new Error('New passwords do not match.');
                const response = await fetch('/api/users/change-password', {
                    method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` }, body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to update password.');
                displayStatusMessage('Password updated successfully!', true, statusDiv);
                passwordChangeForm.reset();
            }
            catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, statusDiv);
            } finally {
                toggleFormElementsDisabled(passwordChangeForm, false);
            }
        });
    }
    
    if (pinChangeForm) {
        pinChangeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            toggleFormElementsDisabled(pinChangeForm, true, 'Updating...');
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
                displayStatusMessage(result.message, true, pinChangeStatus);
                pinChangeForm.reset();
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, pinChangeStatus);
            } finally {
                toggleFormElementsDisabled(pinChangeForm, false);
            }
        });
    }

    if (securityOptionsForm) {
        securityOptionsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            toggleFormElementsDisabled(securityOptionsForm, true, 'Saving...');
            try {
                const payload = { use_pin_for_all_actions: usePinForAllActionsToggle.checked, checkin_on_signin: checkinOnSigninToggle.checked };
                const response = await fetch('/api/users/security-options', {
                    method: 'PUT', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` }, body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Failed to save options.');
                displayStatusMessage("Security options saved successfully!", true);
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false);
            } finally {
                toggleFormElementsDisabled(securityOptionsForm, false);
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
                displayStatusMessage(result.message, true, pinChangeStatus);
            } catch (error) {
                displayStatusMessage(`Error: ${error.message}`, false, pinChangeStatus);
            }
        });
    }

    // Initial Load
    fetchAndPopulateUserData();
});