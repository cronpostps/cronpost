// /frontend/js/signup.js
// version 1.1

console.log("--- signup.js SCRIPT STARTED (v1.1) ---");

document.addEventListener('DOMContentLoaded', () => {

    // --- DOM element references ---
    const signupForm = document.getElementById('signupForm');
    const formStatusMessage = document.getElementById('formStatusMessage');
    const timezoneSelect = document.getElementById('timezone');
    const showPasswordToggle = document.getElementById('showPasswordToggle');

    // --- Timezone Functions (reused from user-profile.js) ---
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
            
            timezoneSelect.innerHTML = ''; // Clear loading option

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

    // Show/Hide Password Logic
    if (showPasswordToggle) {
        showPasswordToggle.addEventListener('change', () => {
            const isChecked = showPasswordToggle.checked;
            document.getElementById('password').type = isChecked ? 'text' : 'password';
            document.getElementById('confirmPassword').type = isChecked ? 'text' : 'password';
        });
    }

    // Form Submission Logic
    if (signupForm) {
        signupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Clear previous messages
            if (typeof clearFormMessagesAndValidation === "function") {
                 clearFormMessagesAndValidation({ generalErrorDiv: formStatusMessage });
            }

            // Client-side validation
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;

            if (password !== confirmPassword) {
                displayGeneralFormMessage(formStatusMessage, "Passwords do not match.", false);
                return;
            }

            // Get Turnstile captcha token
            const captchaToken = signupForm.querySelector('[name="cf-turnstile-response"]')?.value;
            if (!captchaToken) {
                displayGeneralFormMessage(formStatusMessage, "Please complete the CAPTCHA verification.", false);
                return;
            }

            // Disable form during submission
            if(typeof toggleFormElementsDisabled === "function") {
                toggleFormElementsDisabled(signupForm, true, 'Creating Account...');
            }

            const payload = {
                email: document.getElementById('email').value,
                password: password,
                timezone: timezoneSelect.value,
                captchaToken: captchaToken
            };

            try {
                const response = await fetch('/api/auth/signup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const result = await response.json();

                if (!response.ok) {
                    // Use detailed message from backend if available
                    throw new Error(result.detail || 'An unknown error occurred.');
                }
                
                // Success
                signupForm.style.display = 'none'; // Hide the form
                displayGeneralFormMessage(formStatusMessage, result.message, true);
                
                // Redirect to signin page after a delay
                setTimeout(() => {
                    window.location.href = `/signin?status=email_verification_pending&email=${encodeURIComponent(payload.email)}`;
                }, 5000);

            } catch (error) {
                displayGeneralFormMessage(formStatusMessage, error.message, false);
                // Reset Turnstile widget on error
                if (window.turnstile) {
                    window.turnstile.reset();
                }
            } finally {
                // Re-enable form elements if it's still visible
                 if(typeof toggleFormElementsDisabled === "function") {
                    toggleFormElementsDisabled(signupForm, false);
                }
            }
        });
    }

    // --- Initial Load ---
    populateTimezoneSelect();
});