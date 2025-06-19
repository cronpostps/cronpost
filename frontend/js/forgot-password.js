// frontend/js/forgot-password.js
// Version: 1.4 (Improved error message for Rate Limit)

console.log("--- forgot-password.js SCRIPT STARTED (v1.4) ---"); // Cập nhật version trong log

document.addEventListener('DOMContentLoaded', () => {
    console.log("--- forgot-password.js DOMContentLoaded event fired (v1.4) ---"); // Cập nhật version trong log

    const forgotPasswordForm = document.getElementById('forgotPasswordForm');
    const emailInput = document.getElementById('email');
    const emailErrorDiv = document.getElementById('emailError');
    const generalFormErrorDiv = document.getElementById('generalFormError');
    const forgotPwdTurnstileDiv = document.getElementById('forgotPwdTurnstile');

    const formElements = {
        generalErrorDiv: generalFormErrorDiv,
        emailErrorDiv: emailErrorDiv,
        emailInput: emailInput
    };

    if (typeof clearFormMessagesAndValidation === "function") {
        clearFormMessagesAndValidation(formElements);
    } else {
        console.error("forgot-password.js: function clearFormMessagesAndValidation from utils.js is not available.");
    }

    function validateForgotPasswordForm() {
        let isValid = true;
        if (typeof displayFieldError !== "function") {
            console.error("forgot-password.js: function displayFieldError from utils.js is not available.");
            if (generalFormErrorDiv && typeof displayGeneralFormMessage === "function") {
                displayGeneralFormMessage(generalFormErrorDiv, "Page error. Please refresh.");
            }
            return false;
        }

        if (!emailInput || !emailInput.value) {
            displayFieldError(emailErrorDiv, 'Email is required.');
            isValid = false;
        } else if (!/\S+@\S+\.\S+/.test(emailInput.value)) {
            displayFieldError(emailErrorDiv, 'Please enter a valid email address.');
            isValid = false;
        } else {
            displayFieldError(emailErrorDiv, '', 'success');
        }
        return isValid;
    }

    if (forgotPasswordForm) {
        forgotPasswordForm.addEventListener('submit', async (event) => {
            event.preventDefault();

            if (typeof clearFormMessagesAndValidation === "function") {
                clearFormMessagesAndValidation(formElements);
            }

            if (!validateForgotPasswordForm()) {
                if (typeof displayGeneralFormMessage === "function") {
                    displayGeneralFormMessage(generalFormErrorDiv, 'Please correct the errors in the form.');
                }
                return;
            }

            const email = emailInput.value;
            const turnstileResponse = document.querySelector('[name="cf-turnstile-response"]')?.value || null;

            if (!turnstileResponse) {
                if (typeof displayGeneralFormMessage === "function") {
                    displayGeneralFormMessage(generalFormErrorDiv, 'Please complete the CAPTCHA verification.');
                }
                return;
            }

            const submitButton = forgotPasswordForm.querySelector('button[type="submit"]');
            if (typeof toggleFormElementsDisabled === "function") {
                toggleFormElementsDisabled(forgotPasswordForm, true, 'Sending...');
            } else if (submitButton) {
                submitButton.disabled = true;
                if (!submitButton.dataset.originalText) submitButton.dataset.originalText = submitButton.textContent;
                submitButton.textContent = 'Sending...';
            }

            try {
                const response = await fetch('/api/auth/request-password-reset', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ email: email, captchaToken: turnstileResponse }),
                });

                let data;
                let responseOk = response.ok;
                try {
                    data = await response.json();
                } catch (e) {
                    console.error("Failed to parse JSON response:", e);
                    data = { detail: "An unexpected error occurred with the server's response." };
                    responseOk = false;
                }

                if (responseOk) {
                    const messageToDisplay = data.message || 'If an account with that email exists, a password reset link has been sent to your inbox.';
                    if (typeof displayGeneralFormMessage === "function") {
                        displayGeneralFormMessage(generalFormErrorDiv, messageToDisplay, true);
                    } else {
                        alert(messageToDisplay);
                    }
                    forgotPasswordForm.reset();
                } else {
                    let errorMsg = "An unknown error occurred. Please try again."; // Thông báo mặc định
                    if (response.status === 429) { // KIỂM TRA LỖI RATE LIMIT
                        errorMsg = "Too many requests. Please wait a while before trying again.";
                    } else if (data && data.detail) {
                        errorMsg = (typeof data.detail === 'string') ? data.detail : JSON.stringify(data.detail);
                    } else if (response.statusText) {
                        errorMsg = `Error: ${response.statusText} (Status: ${response.status})`;
                    }
                    
                    if (typeof displayGeneralFormMessage === "function") {
                        displayGeneralFormMessage(generalFormErrorDiv, errorMsg);
                    } else {
                        alert(errorMsg);
                    }
                }
            } catch (error) {
                console.error('Network or unexpected error during password reset request:', error);
                if (typeof displayGeneralFormMessage === "function") {
                    displayGeneralFormMessage(generalFormErrorDiv, 'A network error occurred. Please check your connection and try again.');
                } else {
                    alert('A network error occurred. Please check your connection and try again.');
                }
            } finally {
                if (typeof turnstile !== 'undefined' && turnstile.reset) {
                    turnstile.reset();
                }

                if (typeof toggleFormElementsDisabled === "function") {
                    toggleFormElementsDisabled(forgotPasswordForm, false);
                } else if (submitButton) {
                    submitButton.disabled = false;
                    if (submitButton.dataset.originalText) submitButton.textContent = submitButton.dataset.originalText;
                    else submitButton.textContent = "Send Reset Link";
                }
            }
        });
    }

    console.log("--- forgot-password.js DOMContentLoaded event listener finished (v1.4) ---"); // Cập nhật version trong log
});