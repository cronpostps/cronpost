// frontend/js/auth.js
// Version: 2.11
// - Fixed "response.json is not a function" error by correcting the apiCallback inside enforcePinSessionProtection.
// - The callback now returns the raw response object as required by utils.js.

console.log("--- auth.js SCRIPT STARTED (v2.11) ---");

async function enforcePinSessionProtection() {
    // Return immediately if PIN is already verified for this session
    if (sessionStorage.getItem('isPinVerified') === 'true') {
        console.log("PIN session already verified, skipping check.");
        return;
    }

    // Define which pages require PIN verification on load
    const protectedPages = [
        'user-profile',
        'upload-file', 
        'ucm', 
        'scm', 
        'iam',

    ];
    // Lấy tên file từ URL, ví dụ: "upload-file" từ "/upload-file.html"
    const currentPage = window.location.pathname.split('/').pop().replace('.html', '');

    if (!protectedPages.includes(currentPage)) {
        return;
    }

    console.log(`auth.js: Running PIN protection check for protected page: ${currentPage}`);

    try {
        const response = await fetchWithAuth('/api/users/me');
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({detail: 'Could not fetch user data.'}));
            throw new Error(errorData.detail);
        }
        const userData = await response.json();

        if (userData.use_pin_for_all_actions && userData.has_pin) {
            const verificationCallback = async (pin) => {
                return await fetchWithAuth('/api/users/verify-pin-session', {
                    method: 'POST',
                    body: JSON.stringify({ pin_code: pin })
                });
            };

            await executeActionWithPinVerification(
                "For your security, please verify your PIN to continue.", 
                verificationCallback
            );

            sessionStorage.setItem('isPinVerified', 'true');
            console.log("Session PIN verified successfully via auth.js.");
        } else {
            sessionStorage.setItem('isPinVerified', 'true');
        }
    } catch (error) {
        if (error.message?.includes('cancelled')) {
            console.log("PIN verification was cancelled by user. Redirecting to dashboard.");
            alert("Access to this page requires PIN verification. Redirecting to dashboard.");
            window.location.href = '/dashboard';
            return;
        }
        if (!error.message?.includes('Session expired')) {
            console.error("Unrecoverable page access error:", error.message);
            const mainContent = document.querySelector('.container, #main-content');
            if(mainContent) mainContent.innerHTML = `<div class="alert alert-danger">Access Denied: ${error.message}</div>`;
            alert(`Access Denied: An error occurred during security verification. ${error.message}`);
        }
    }
}

function setupSignupPageEventListeners() {
    const signupForm = document.getElementById('signupForm');
    if (!signupForm) return;

    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const confirmPasswordInput = document.getElementById('confirmPassword');
    const emailErrorDiv = document.getElementById('emailError');
    const passwordErrorDiv = document.getElementById('passwordError');
    const confirmPasswordErrorDiv = document.getElementById('confirmPasswordError');
    const generalFormErrorDiv = document.getElementById('generalFormError');
    const showPasswordCheck = document.getElementById('showPasswordCheck');
    const showConfirmPasswordCheck = document.getElementById('showConfirmPasswordCheck');
    const signupFormElements = {
        generalErrorDiv: generalFormErrorDiv,
        emailErrorDiv: emailErrorDiv, emailInput: emailInput,
        passwordErrorDiv: passwordErrorDiv, passwordInput: passwordInput,
        confirmPasswordErrorDiv: confirmPasswordErrorDiv, confirmPasswordInput: confirmPasswordInput
    };
    function validateSignupFormInternal() {
        let isValid = true;
        if (typeof displayFieldError !== "function") {
            console.error("utils.js or displayFieldError function is not loaded.");
            return false;
        }
        if (!emailInput || !emailInput.value) { displayFieldError(emailErrorDiv, 'Email is required.'); isValid = false; }
        else if (!/\S+@\S+\.\S+/.test(emailInput.value)) { displayFieldError(emailErrorDiv, 'Please enter a valid email address.'); isValid = false; }
        else { displayFieldError(emailErrorDiv, ''); }
        if (!passwordInput || !passwordInput.value) { displayFieldError(passwordErrorDiv, 'Password is required.'); isValid = false; }
        else if (passwordInput.value.length < 6 || passwordInput.value.length > 20) { displayFieldError(passwordErrorDiv, 'Password must be 6-20 characters long.'); isValid = false; }
        else { displayFieldError(passwordErrorDiv, ''); }
        if (confirmPasswordInput) {
            if (!confirmPasswordInput.value) { displayFieldError(confirmPasswordErrorDiv, 'Confirm password is required.'); isValid = false; }
            else if (passwordInput && passwordInput.value !== confirmPasswordInput.value) { displayFieldError(confirmPasswordErrorDiv, 'Passwords do not match.'); isValid = false; }
            else { displayFieldError(confirmPasswordErrorDiv, ''); }
        }
        return isValid;
    }
    if (showPasswordCheck && passwordInput) { showPasswordCheck.addEventListener('change', () => { passwordInput.type = showPasswordCheck.checked ? 'text' : 'password'; }); }
    if (showConfirmPasswordCheck && confirmPasswordInput) { showConfirmPasswordCheck.addEventListener('change', () => { confirmPasswordInput.type = showConfirmPasswordCheck.checked ? 'text' : 'password'; }); }
    signupForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (typeof clearFormMessagesAndValidation === "function") { clearFormMessagesAndValidation(signupFormElements); }
        if (!validateSignupFormInternal()) {
            if (typeof displayGeneralFormMessage === "function") { displayGeneralFormMessage(generalFormErrorDiv, 'Please correct the errors in the form.'); }
            return;
        }
        const email = emailInput.value;
        const password = passwordInput.value;
        const captchaToken = document.querySelector('[name="cf-turnstile-response"]')?.value || null;
        if (!captchaToken) {
            if (typeof displayGeneralFormMessage === "function") { displayGeneralFormMessage(generalFormErrorDiv, 'CAPTCHA verification is required. Please complete the challenge.'); }
            if (typeof turnstile !== 'undefined' && turnstile.reset) turnstile.reset();
            return;
        }
        const submitButton = signupForm.querySelector('button[type="submit"]');
        if (typeof toggleFormElementsDisabled === "function") {
            toggleFormElementsDisabled(signupForm, true, 'Creating Account...');
        }

        try {
            const response = await fetchWithAuth('/api/auth/signup', {
                method: 'POST',
                body: JSON.stringify({ email, password, captchaToken })
            });

            const data = await response.json();
            
            if (response.ok) {
                alert(data.message || 'Registration process initiated. Please check your email.');
                window.location.href = `/signin?status=email_verification_pending&email=${encodeURIComponent(email)}`;
            } else {
                handleSignupError(response, data, generalFormErrorDiv);
            }
        } catch (error) {
            displayGeneralFormMessage(generalFormErrorDiv, 
                'A network error occurred. Please check your connection.');
        } finally {
            if (typeof toggleFormElementsDisabled === "function") {
                toggleFormElementsDisabled(signupForm, false);
            }
            if (typeof turnstile !== 'undefined' && turnstile.reset) {
                turnstile.reset();
            }
        }
    });
}

function setupCommonAuthPageLogic() {
    const googleSignInBtn = document.getElementById('googleSignInBtn');
    if (googleSignInBtn) {
        googleSignInBtn.addEventListener('click', () => {
            const generalErrorDivCurrentPage = document.getElementById('generalFormError');
            if(generalErrorDivCurrentPage && typeof displayGeneralFormMessage === "function"){
                 displayGeneralFormMessage(generalErrorDivCurrentPage, '');
            }
            window.location.href = '/api/auth/google';
        });
    }
}


// --- KHỞI TẠO KHI DOM ĐÃ SẴN SÀNG ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("--- auth.js DOMContentLoaded event fired (v2.10) ---");
    const accessToken = localStorage.getItem('accessToken');
    if (accessToken) {
        enforcePinSessionProtection();
    }
    setupCommonAuthPageLogic();
    if (document.getElementById('signupForm')) {
        setupSignupPageEventListeners();
    }
    console.log("--- auth.js DOMContentLoaded event listener finished (v2.10) ---");
});