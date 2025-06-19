// frontend/js/signin.js
// Version: 1.4 (Improved error message for Rate Limit)

console.log("--- signin.js SCRIPT STARTED (v1.4) ---");

document.addEventListener('DOMContentLoaded', () => {
    console.log("--- signin.js DOMContentLoaded event fired (v1.4) ---");

    // Form Elements
    const signInForm = document.getElementById('signInForm');
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    
    // Error Elements
    const emailErrorDiv = document.getElementById('emailError');
    const passwordErrorDiv = document.getElementById('passwordError');
    const generalFormErrorDiv = document.getElementById('generalFormError');

    // UI Controls
    const showPasswordCheck = document.getElementById('showPasswordCheck');

    // Resend Confirmation Elements
    const resendConfirmationSection = document.getElementById('resendConfirmationSection');
    const resendConfirmationBtn = document.getElementById('resendConfirmationBtn');
    const resendConfirmationMessage = document.getElementById('resendConfirmationMessage');
    const resendEmailInput = document.getElementById('resendEmailInput');

    // Form Elements Object for Utils
    const signInFormElements = {
        generalErrorDiv: generalFormErrorDiv,
        emailErrorDiv: emailErrorDiv,
        emailInput: emailInput,
        passwordErrorDiv: passwordErrorDiv,
        passwordInput: passwordInput
    };

    if (typeof clearFormMessagesAndValidation === "function") {
        clearFormMessagesAndValidation(signInFormElements);
    } else {
        console.error("signin.js: function clearFormMessagesAndValidation from utils.js is not available.");
    }
    if (resendConfirmationMessage) {
        resendConfirmationMessage.textContent = '';
        resendConfirmationMessage.className = 'form-text mt-1';
        resendConfirmationMessage.style.display = 'none';
    }

    function validateSignInFormInternal() {
        let isValid = true;
        if (typeof displayFieldError !== "function") {
            console.error("signin.js: function displayFieldError from utils.js is not available.");
            if (generalFormErrorDiv && typeof displayGeneralFormMessage === "function") {
                displayGeneralFormMessage(generalFormErrorDiv, "Page error. Please refresh.");
            }
            return false;
        }

        // Validate email
        if (!emailInput || !emailInput.value) {
            displayFieldError(emailErrorDiv, 'Email is required.');
            isValid = false;
        } else if (!/\S+@\S+\.\S+/.test(emailInput.value)) {
            displayFieldError(emailErrorDiv, 'Please enter a valid email address.');
            isValid = false;
        } else {
            displayFieldError(emailErrorDiv, '');
        }

        // Validate password
        if (!passwordInput || !passwordInput.value) {
            displayFieldError(passwordErrorDiv, 'Password is required.');
            isValid = false;
        } else {
            displayFieldError(passwordErrorDiv, '');
        }
        return isValid;
    }

    function setupSigninPageEventListeners() {
        if (!signInForm) return;

        // Show/Hide Password Logic
        if (showPasswordCheck && passwordInput) {
            showPasswordCheck.addEventListener('change', () => {
                passwordInput.type = showPasswordCheck.checked ? 'text' : 'password';
            });
        }

        // Form Submit Logic
        signInForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            
            if (typeof clearFormMessagesAndValidation === "function") {
                clearFormMessagesAndValidation(signInFormElements);
            }

            if (!validateSignInFormInternal()) {
                if (typeof displayGeneralFormMessage === "function") {
                    displayGeneralFormMessage(generalFormErrorDiv, 'Please correct the errors in the form.');
                }
                return;
            }

            // Add Turnstile verification
            const turnstileResponse = document.querySelector('[name="cf-turnstile-response"]')?.value || null;
            if (!turnstileResponse) {
                if (typeof displayGeneralFormMessage === "function") {
                    displayGeneralFormMessage(generalFormErrorDiv, 'Please complete the CAPTCHA verification.');
                }
                return;
            }

            const email = emailInput.value;
            const password = passwordInput.value;
            const submitButton = signInForm.querySelector('button[type="submit"]');

            if (typeof toggleFormElementsDisabled === "function") {
                toggleFormElementsDisabled(signInForm, true, 'Signing In...');
            } else if (submitButton) {
                submitButton.disabled = true;
                if (!submitButton.dataset.originalText) submitButton.dataset.originalText = submitButton.textContent;
                submitButton.textContent = 'Signing In...';
            }

            try {
                const response = await fetch('/api/auth/signin', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        email,
                        password,
                        captchaToken: turnstileResponse
                    }),
                });

                let data;
                let responseOk = response.ok;
                try {
                    data = await response.json();
                } catch (e) {
                    console.error("Failed to parse JSON response:", e);
                    data = { detail: "An unexpected error occurred with the server's response." };
                    if (!responseOk && response.headers.get("content-type")?.includes("text/html")) {
                         data.detail = `Server error (${response.status}). Please check server logs and try again later.`;
                    }
                    responseOk = false;
                }

                if (responseOk) {
                    if (data && data.access_token) {
                        localStorage.setItem('accessToken', data.access_token);
                        if(data.refresh_token) localStorage.setItem('refreshToken', data.refresh_token);
                        
                        const successMessage = (data.message && typeof data.message === 'string' ? data.message : 'Sign in successful! Redirecting...');
                        if (typeof displayGeneralFormMessage === "function") {
                            displayGeneralFormMessage(generalFormErrorDiv, successMessage, true);
                        } else {
                            alert(successMessage);
                        }
                        setTimeout(() => { window.location.href = '/dashboard'; }, 1000);
                    } else {
                        const errorMsg = data?.detail ? String(data.detail) : 'Sign in successful, but no token received.';
                        if (typeof displayGeneralFormMessage === "function") displayGeneralFormMessage(generalFormErrorDiv, errorMsg);
                        else alert(errorMsg);
                    }
                } else {
                    let errorMsg = "An unknown error occurred. Please try again."; // Thông báo mặc định
                    if (response.status === 429) { // KIỂM TRA LỖI RATE LIMIT
                        errorMsg = "Too many requests. Please wait a while before trying again.";
                    } else if (data && data.detail) {
                        errorMsg = (typeof data.detail === 'string') ? data.detail : JSON.stringify(data.detail);
                    } else if (response.statusText) {
                        errorMsg = `Error: ${response.statusText} (Status: ${response.status})`;
                    }
                    
                    if (response.status === 403 && response.headers.get('x-verification-needed') === 'true') {
                         errorMsg = data?.detail || 'Your email is not confirmed. Please check your inbox or resend the confirmation email.';
                        if (resendConfirmationSection && resendEmailInput && emailInput) {
                            resendEmailInput.value = email;
                            if(emailInput) emailInput.classList.add('is-invalid');
                            resendConfirmationSection.style.display = 'block';
                        }
                    }
                    if (typeof displayGeneralFormMessage === "function") {
                        displayGeneralFormMessage(generalFormErrorDiv, String(errorMsg));
                    } else {
                        alert(String(errorMsg));
                    }
                }
            } catch (error) {
                console.error('Network or unexpected error during signin:', error);
                const networkErrorMsg = 'A network error occurred. Please check your connection and try again.';
                if (typeof displayGeneralFormMessage === "function") {
                    displayGeneralFormMessage(generalFormErrorDiv, networkErrorMsg);
                } else {
                    alert(networkErrorMsg);
                }
            } finally {
                if (typeof toggleFormElementsDisabled === "function") {
                    toggleFormElementsDisabled(signInForm, false);
                } else if (submitButton){
                    submitButton.disabled = false;
                    if (submitButton.dataset.originalText) submitButton.textContent = submitButton.dataset.originalText;
                    else submitButton.textContent = "Sign In";
                }
            }
        });
    }

    if (resendConfirmationBtn && resendEmailInput && emailInput && resendConfirmationMessage) {
        resendConfirmationBtn.addEventListener('click', async () => {
            const emailToResend = emailInput.value || resendEmailInput.value;
            if (!emailToResend || !/\S+@\S+\.\S+/.test(emailToResend)) {
                 resendConfirmationMessage.textContent = 'Please enter a valid email address in the email field above.';
                 resendConfirmationMessage.className = 'form-text text-danger d-block';
                 resendConfirmationMessage.style.display = 'block';
                return;
            }
            const originalResendBtnText = resendConfirmationBtn.textContent;
            resendConfirmationBtn.disabled = true;
            resendConfirmationBtn.textContent = 'Sending...';
            resendConfirmationMessage.textContent = 'Sending confirmation email...';
            resendConfirmationMessage.className = 'form-text text-info d-block';
            resendConfirmationMessage.style.display = 'block';

            try {
                const response = await fetch('/api/auth/resend-confirmation', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: emailToResend }),
                });
                const data = await response.json().catch(() => ({detail: "Invalid response."}));
                let messageToDisplay = ""; let isSuccess = false;
                if (response.ok) {
                    messageToDisplay = data.message || 'Confirmation email has been resent.'; isSuccess = true;
                } else {
                    messageToDisplay = data?.detail ? String(data.detail) : 'Failed to resend confirmation email.';
                }
                resendConfirmationMessage.textContent = messageToDisplay;
                resendConfirmationMessage.className = isSuccess ? 'form-text text-success d-block' : 'form-text text-danger d-block';
            } catch (error) {
                console.error('Error resending confirmation email:', error);
                resendConfirmationMessage.textContent = 'A network error occurred. Please try again.';
                resendConfirmationMessage.className = 'form-text text-danger d-block';
            } finally {
                setTimeout(() => {
                    if (resendConfirmationBtn) {
                        resendConfirmationBtn.disabled = false;
                        resendConfirmationBtn.textContent = originalResendBtnText || 'Resend Confirmation Email';
                    }
                }, 30000);
            }
        });
    }

    function handleUrlStatusMessagesOnSignin() {
        const urlParams = new URLSearchParams(window.location.search);
        const statusParam = urlParams.get('status');
        const emailParamUrl = urlParams.get('email'); 
        const detailParam = urlParams.get('detail');
    
        if (statusParam && typeof displayGeneralFormMessage === "function") {
            let message = ''; let isSuccess = false;
            let autoFillEmail = emailParamUrl ? decodeURIComponent(emailParamUrl) : "";
    
            if (statusParam === 'email_verification_pending' && autoFillEmail) {
                message = `Registration successful for ${autoFillEmail}. Please check your email to verify your account. If you haven't received it, you can request a new one below.`;
                isSuccess = true;
                if (resendConfirmationSection && resendEmailInput && emailInput) {
                    emailInput.value = autoFillEmail; resendEmailInput.value = autoFillEmail; 
                    resendConfirmationSection.style.display = 'block';
                }
            } else if (statusParam === 'email_confirmed_success' && autoFillEmail) {
                message = `Email ${autoFillEmail} has been successfully confirmed. You can now sign in.`;
                isSuccess = true; if (emailInput) emailInput.value = autoFillEmail;
            } else if (statusParam === 'email_already_confirmed' && autoFillEmail) {
                message = `Email ${autoFillEmail} was already confirmed. You can sign in.`;
                isSuccess = true; if (emailInput) emailInput.value = autoFillEmail;
            } else if (statusParam === 'email_confirmation_expired' || statusParam === 'email_confirmation_invalid' || statusParam === 'email_confirmation_invalid_or_used') {
                message = 'The email confirmation link is invalid or has expired. Please try resending the confirmation email.';
                if (resendConfirmationSection && autoFillEmail && resendEmailInput && emailInput) {
                    emailInput.value = autoFillEmail; resendEmailInput.value = autoFillEmail;
                    resendConfirmationSection.style.display = 'block';
                }
            } else if (statusParam === 'email_confirmation_user_not_found') {
                message = 'User not found for this confirmation link. Please register or check the link.';
            } else if (statusParam === 'google_oauth_error') {
                message = `Google Sign-In failed: ${String(decodeURIComponent(detailParam || 'Unknown error'))}`;
            } else if (statusParam === 'google_email_not_verified' && autoFillEmail) {
                message = `Your Google email (${autoFillEmail}) is not verified. Please verify your email with Google first.`;
            } else if (statusParam === 'google_signup_success_check_email' && autoFillEmail) {
                message = `Welcome! Your account for ${autoFillEmail} was created with Google. An email with guidance has been sent. You can now sign in with Google.`;
                isSuccess = true; if (emailInput) emailInput.value = autoFillEmail;
            } else if (statusParam === 'google_merge_success_check_email' && autoFillEmail) {
                 message = `Your account for ${autoFillEmail} has been successfully linked with Google. An email with guidance has been sent. You can now sign in with Google.`;
                isSuccess = true; if (emailInput) emailInput.value = autoFillEmail;
            } else if (statusParam === 'google_link_success' && autoFillEmail) {
                message = `Your account for ${autoFillEmail} has been successfully linked with Google. You can now sign in using Google.`;
                isSuccess = true; if (emailInput) emailInput.value = autoFillEmail;
            } else if (statusParam === 'signout_success') {
                 message = `You have been signed out successfully.`; isSuccess = true;
            } else if (statusParam === 'password_reset_success') { // NEW: Handle password reset success
                message = 'Your password has been successfully reset. Please sign in with your new password.';
                isSuccess = true;
            }
            
            if (message) {
                displayGeneralFormMessage(generalFormErrorDiv, String(message), isSuccess); 
                if (window.history.replaceState) {
                    const cleanUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
                    window.history.replaceState({ path: cleanUrl }, '', cleanUrl);
                }
            }
        }
    }
    setupSigninPageEventListeners();
    handleUrlStatusMessagesOnSignin();
    
    console.log("--- signin.js DOMContentLoaded event listener finished (v1.3) ---");
});