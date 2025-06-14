// frontend/js/utils.js
// Version: 1.5
// - Removed global 401 handling from fetchWithAuth to allow local error processing.
// - executeActionWithPinVerification now centrally handles the PIN retry loop.
// - executeActionWithPinVerification now automatically redirects to the dashboard on account lockout.

console.log("--- utils.js SCRIPT STARTED (v1.5) ---");

// === API CALL HELPER FUNCTION ===

/**
 * A wrapper for the native fetch function that automatically adds the authentication token.
 * It no longer handles 401 errors globally, allowing the calling function to manage them.
 * @param {string} url - The URL to fetch.
 * @param {object} [options={}] - The options object for the fetch call.
 * @returns {Promise<Response>} The fetch Response object.
 */
async function fetchWithAuth(url, options = {}) {
    const accessToken = localStorage.getItem('accessToken');

    // Set default headers
    const defaultHeaders = {
        'Content-Type': 'application/json',
        ...options.headers, // Allow overriding default headers
    };

    // Add authorization header if token exists
    if (accessToken) {
        defaultHeaders['Authorization'] = `Bearer ${accessToken}`;
    }

    // Create the final options object
    const finalOptions = {
        ...options,
        headers: defaultHeaders,
    };

    // Perform the fetch call and return the response directly
    const response = await fetch(url, finalOptions);
    return response;
}


// --- FORM & UI HELPER FUNCTIONS ---

/**
 * Displays an error/success message for a specific input field.
 */
function displayFieldError(errorElement, message, type = 'error') {
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.display = message ? 'block' : 'none';
        const inputElement = errorElement.previousElementSibling; 
        if (inputElement && inputElement.tagName === 'INPUT' && inputElement.classList.contains('form-control')) {
            inputElement.classList.remove('is-invalid', 'is-valid');
            if (message) {
                inputElement.classList.add(type === 'error' ? 'is-invalid' : 'is-valid');
            }
        }
        errorElement.className = message ? (type === 'error' ? 'invalid-feedback' : 'valid-feedback') : 'invalid-feedback';
    }
}

/**
 * Displays a general form message (usually an alert).
 */
function displayGeneralFormMessage(alertElement, message, isSuccess = false) {
    if (alertElement) {
        alertElement.textContent = message;
        alertElement.style.display = message ? 'block' : 'none';
        alertElement.className = 'alert mt-3'; // Reset old alert classes
        if (message) {
            alertElement.classList.add(isSuccess ? 'alert-success' : 'alert-danger');
        }
    }
}

/**
 * Clears all error/success messages on a specific form.
 */
function clearFormMessagesAndValidation(formElements) {
    if (formElements.generalErrorDiv) {
        displayGeneralFormMessage(formElements.generalErrorDiv, '', false);
    }
    if (formElements.emailErrorDiv && formElements.emailInput) {
        displayFieldError(formElements.emailErrorDiv, '');
        formElements.emailInput.classList.remove('is-invalid', 'is-valid');
    }
    if (formElements.passwordErrorDiv && formElements.passwordInput) {
        displayFieldError(formElements.passwordErrorDiv, '');
        formElements.passwordInput.classList.remove('is-invalid', 'is-valid');
    }
    if (formElements.confirmPasswordErrorDiv && formElements.confirmPasswordInput) {
        displayFieldError(formElements.confirmPasswordErrorDiv, '');
        formElements.confirmPasswordInput.classList.remove('is-invalid', 'is-valid');
    }
}

/**
 * Disables/Enables inputs and the primary button on a form.
 */
function toggleFormElementsDisabled(formElement, disable, buttonTextWhileDisabled = null) {
    if (!formElement) return;
    const submitButton = formElement.querySelector('button[type="submit"]');
    const inputs = formElement.querySelectorAll('input:not([type="checkbox"]), select, textarea');
    if (submitButton) {
        submitButton.disabled = disable;
        if (disable && buttonTextWhileDisabled) {
            if (!submitButton.dataset.originalText) {
                submitButton.dataset.originalText = submitButton.textContent;
            }
            submitButton.textContent = buttonTextWhileDisabled;
        } else if (!disable && submitButton.dataset.originalText) {
            submitButton.textContent = submitButton.dataset.originalText;
        }
    }
    inputs.forEach(input => { input.disabled = disable; });
    const googleBtn = document.getElementById('googleSignInBtn');
    if (googleBtn) {
        googleBtn.disabled = disable;
    }
}


// --- DATE & TIMEZONE HELPER FUNCTIONS ---

function formatTimestampInZone(isoTimestamp, targetTimezone) {
    if (!isoTimestamp) { return 'N/A'; }
    let validTimezone = 'UTC';
    try {
        new Intl.DateTimeFormat(undefined, { timeZone: targetTimezone });
        validTimezone = targetTimezone;
    } catch (e) {
        console.warn(`Invalid or unsupported timezone provided: "${targetTimezone}". Falling back to UTC.`);
    }
    try {
        const date = new Date(isoTimestamp);
        const formatter = new Intl.DateTimeFormat('en-GB', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false, timeZone: validTimezone
        });
        return formatter.format(date);
    } catch (error) {
        console.error(`Error formatting date for timezone ${validTimezone}:`, error);
        return new Date(isoTimestamp).toLocaleString();
    }
}

function getIanaTimezoneOffsetMinutes(ianaTimeZone) {
    try {
        const date = new Date();
        const utcDate = new Date(date.toLocaleString('en-US', { timeZone: 'UTC' }));
        const targetDate = new Date(date.toLocaleString('en-US', { timeZone: ianaTimeZone }));
        return (targetDate.getTime() - utcDate.getTime()) / (1000 * 60);
    } catch (e) {
        console.error(`Could not calculate offset for timezone: ${ianaTimeZone}`, e);
        return 0;
    }
}

function formatGmtOffset(offsetMinutes) {
    const sign = offsetMinutes >= 0 ? '+' : '-';
    const absOffset = Math.abs(offsetMinutes);
    const hours = String(Math.floor(absOffset / 60)).padStart(2, '0');
    const minutes = String(absOffset % 60).padStart(2, '0');
    return `GMT ${sign}${hours}:${minutes}`;
}

/**
 * Formats a total number of seconds into an hh:mm:ss string.
 * @param {number} totalSeconds - The total seconds to format.
 * @returns {string} The formatted time string, e.g., "00:15:00".
 */
function formatSecondsToHms(totalSeconds) {
    if (isNaN(totalSeconds) || totalSeconds < 0) {
        return "00:00:00";
    }
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = Math.floor(totalSeconds % 60);

    const paddedHours = String(hours).padStart(2, '0');
    const paddedMinutes = String(minutes).padStart(2, '0');
    const paddedSeconds = String(seconds).padStart(2, '0');

    return `${paddedHours}:${paddedMinutes}:${paddedSeconds}`;
}


// === CENTRALIZED PIN VERIFICATION FUNCTION ===

/**
 * Executes an API action that requires PIN verification, handling the retry loop and lockout redirect centrally.
 * @param {string} promptText - The text to display in the PIN modal prompt.
 * @param {Function} apiCallback - An async function that takes the entered PIN and performs the fetch request. It must return the raw response object.
 * @returns {Promise<any>} A promise that resolves with the successful JSON result of the apiCallback.
 * @throws Will re-throw an error if the user cancels the action.
 */
async function executeActionWithPinVerification(promptText, apiCallback) {
    let isActionSuccessful = false;
    let lastErrorMessage = null;

    do {
        try {
            // 1. Request PIN from user via modal
            const enteredPin = await window.requestPinVerification(promptText, lastErrorMessage);
            
            // 2. Execute the provided API callback with the entered PIN
            const response = await apiCallback(enteredPin);

            // 3. If the response is not OK, parse the error and throw it to be caught below
            if (!response.ok) {
                const errorData = await response.json();
                throw errorData;
            }
            
            // 4. If successful, mark as such and return the JSON data
            isActionSuccessful = true;
            return await response.json();

        } catch (error) {
            // Case 1: User closed the PIN modal (e.g., pressed Esc or clicked outside)
            if (error instanceof Error && error.message.includes('cancelled')) {
                // This is a "clean" exit. Re-throw it so the calling page knows the action was aborted.
                throw error; 
            }
            
            // The error is likely a JSON object from the backend
            const errorDetail = error.detail || error;

            // Case 2: The backend returned a specific "account_locked" error.
            if (typeof errorDetail === 'object' && errorDetail.type === 'account_locked') {
                const timeStr = formatSecondsToHms(errorDetail.remaining_seconds);
                const finalMessage = `${errorDetail.message} You will be redirected to the dashboard. Please try again in ${timeStr}.`;
                
                // Alert the user with the detailed message.
                alert(finalMessage);
                
                // Redirect to the dashboard.
                window.location.href = '/dashboard';
                
                // Return a promise that never resolves to halt further script execution.
                // This prevents any `.then()` or `await` in the calling code from proceeding, as the page is now redirecting.
                return new Promise(() => {}); 
            }

            // Case 3: Other retry-able errors (e.g., invalid PIN).
            // Prepare the error message for the next PIN modal prompt.
            if (typeof errorDetail === 'string') {
                lastErrorMessage = errorDetail;
            } else {
                lastErrorMessage = errorDetail.message || 'An unknown error occurred.';
            }
        }
    } while (!isActionSuccessful);
}