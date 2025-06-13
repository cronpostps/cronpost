// /frontend/js/complete-profile.js
// version 1.1
// Changelog:
// - Fetches current user profile to include user_name in the update payload, fixing 422 error.

console.log("--- complete-profile.js SCRIPT STARTED (v1.1) ---");

document.addEventListener('DOMContentLoaded', () => {

    const urlParams = new URLSearchParams(window.location.search);
    const accessToken = urlParams.get('token');

    if (!accessToken) {
        console.error("No access token found in URL. Redirecting to signin.");
        window.location.href = '/signin.html?status=error';
        return;
    }
    localStorage.setItem('accessToken', accessToken);

    const profileForm = document.getElementById('completeProfileForm');
    const formStatusMessage = document.getElementById('formStatusMessage');
    const timezoneSelect = document.getElementById('timezone');

    // --- Timezone Functions ---
    function getIanaTimezoneOffsetMinutes(ianaTimeZone) {
        const date = new Date();
        const utcDate = new Date(date.toLocaleString('en-US', { timeZone: 'UTC' }));
        const targetDate = new Date(date.toLocaleString('en-US', { timeZone: ianaTimeZone }));
        return (targetDate.getTime() - utcDate.getTime()) / (1000 * 60);
    }

    function formatGmtOffset(offsetMinutes) {
        const sign = offsetMinutes >= 0 ? '+' : '-';
        const absOffset = Math.abs(offsetMinutes);
        const hours = String(Math.floor(absOffset / 60)).padStart(2, '0');
        const minutes = String(absOffset % 60).padStart(2, '0');
        return `GMT ${sign}${hours}:${minutes}`;
    }

    function populateTimezoneSelect() {
        if (!timezoneSelect) return;
        try {
            const allTimezones = Intl.supportedValuesOf('timeZone');
            const detectedTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

            const timezoneData = allTimezones.map(tz => ({
                iana: tz,
                offset: getIanaTimezoneOffsetMinutes(tz),
                label: `[${formatGmtOffset(getIanaTimezoneOffsetMinutes(tz))}] - ${tz}`
            }));

            timezoneData.sort((a, b) => a.offset - b.offset);
            timezoneSelect.innerHTML = '';
            timezoneData.forEach(tzInfo => {
                const option = document.createElement('option');
                option.value = tzInfo.iana;
                option.textContent = tzInfo.label;
                if (tzInfo.iana === detectedTimezone) {
                    option.selected = true;
                }
                timezoneSelect.appendChild(option);
            });
        } catch (e) {
            console.error("Could not populate timezones.", e);
            timezoneSelect.innerHTML = '<option value="Etc/UTC">[GMT +00:00] - Etc/UTC</option>';
        }
    }
    
    // --- Event Listeners ---
    if (profileForm) {
        profileForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const statusDiv = document.getElementById('formStatusMessage');
            if (typeof displayGeneralFormMessage === "function") {
                displayGeneralFormMessage(statusDiv, "", false, true);
            }

            const submitButton = profileForm.querySelector('button[type="submit"]');
            submitButton.disabled = true;
            submitButton.textContent = 'Saving...';
            
            try {
                // SỬA LỖI 422: Lấy thông tin user hiện tại để có user_name
                const meResponse = await fetch('/api/users/me', {
                    headers: { 'Authorization': `Bearer ${accessToken}` }
                });
                if (!meResponse.ok) {
                    throw new Error('Could not fetch current user data.');
                }
                const meData = await meResponse.json();

                // Tạo payload hoàn chỉnh bao gồm cả user_name
                const payload = {
                    user_name: meData.user_name, // Gửi kèm user_name đã có
                    timezone: timezoneSelect.value
                };

                const response = await fetch('/api/users/profile', {
                    method: 'PUT',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${accessToken}` 
                    },
                    body: JSON.stringify(payload)
                });

                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.detail || 'Failed to save profile.');
                }
                
                if (typeof displayGeneralFormMessage === "function") {
                    displayGeneralFormMessage(statusDiv, "Profile updated! Redirecting to dashboard...", true);
                }
                setTimeout(() => {
                    window.location.href = '/dashboard.html';
                }, 1500);

            } catch (error) {
                 if (typeof displayGeneralFormMessage === "function") {
                    displayGeneralFormMessage(statusDiv, `Error: ${error.message}`, false);
                }
                submitButton.disabled = false;
                submitButton.textContent = 'Save and Continue';
            }
        });
    }

    // --- Initial Load ---
    populateTimezoneSelect();
});