// frontend/js/auth.js
// Version: 2.4 (Added captchaToken to signup request body for Turnstile verification)
// Mô tả: Logic điều khiển đăng ký người dùng thủ công và Google OAuth.

console.log("--- auth.js SCRIPT STARTED (v2.4) ---"); // Cập nhật version

/**
 * Thiết lập các event listener chỉ dành cho trang signup.
 */
function setupSignupPageEventListeners() {
    const signupForm = document.getElementById('signupForm');
    // Chỉ tiếp tục nếu signupForm tồn tại (tức là đang ở trang signup.html)
    if (!signupForm) {
        // console.log("auth.js: signupForm not found, skipping signup-specific listeners.");
        return;
    }
    console.log("auth.js: Setting up signup page specific event listeners.");

    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const confirmPasswordInput = document.getElementById('confirmPassword');
    
    const emailErrorDiv = document.getElementById('emailError');
    const passwordErrorDiv = document.getElementById('passwordError');
    const confirmPasswordErrorDiv = document.getElementById('confirmPasswordError');
    const generalFormErrorDiv = document.getElementById('generalFormError');

    const showPasswordCheck = document.getElementById('showPasswordCheck');
    const showConfirmPasswordCheck = document.getElementById('showConfirmPasswordCheck');

    // Đối tượng chứa các element của signup form để truyền cho hàm utils
    const signupFormElements = {
        generalErrorDiv: generalFormErrorDiv,
        emailErrorDiv: emailErrorDiv, emailInput: emailInput,
        passwordErrorDiv: passwordErrorDiv, passwordInput: passwordInput,
        confirmPasswordErrorDiv: confirmPasswordErrorDiv, confirmPasswordInput: confirmPasswordInput
    };

    // --- Hàm Validate Form Đăng ký (riêng cho signup) ---
    function validateSignupFormInternal() {
        let isValid = true;
        if (typeof displayFieldError !== "function") {
            console.error("utils.js or displayFieldError function is not loaded.");
            return false;
        }

        if (!emailInput || !emailInput.value) {
            displayFieldError(emailErrorDiv, 'Email is required.'); isValid = false;
        } else if (!/\S+@\S+\.\S+/.test(emailInput.value)) {
            displayFieldError(emailErrorDiv, 'Please enter a valid email address.'); isValid = false;
        } else {
            displayFieldError(emailErrorDiv, '');
        }

        if (!passwordInput || !passwordInput.value) {
            displayFieldError(passwordErrorDiv, 'Password is required.'); isValid = false;
        } else if (passwordInput.value.length < 6 || passwordInput.value.length > 20) {
            displayFieldError(passwordErrorDiv, 'Password must be 6-20 characters long.'); isValid = false;
        } else {
            displayFieldError(passwordErrorDiv, '');
        }

        if (confirmPasswordInput) {
            if (!confirmPasswordInput.value) {
                displayFieldError(confirmPasswordErrorDiv, 'Confirm password is required.'); isValid = false;
            } else if (passwordInput && passwordInput.value !== confirmPasswordInput.value) {
                displayFieldError(confirmPasswordErrorDiv, 'Passwords do not match.'); isValid = false;
            } else {
                displayFieldError(confirmPasswordErrorDiv, '');
            }
        }
        return isValid;
    }

    // Xử lý Show/Hide Password
    if (showPasswordCheck && passwordInput) {
        showPasswordCheck.addEventListener('change', () => {
            passwordInput.type = showPasswordCheck.checked ? 'text' : 'password';
        });
    }
    if (showConfirmPasswordCheck && confirmPasswordInput) {
        showConfirmPasswordCheck.addEventListener('change', () => {
            confirmPasswordInput.type = showConfirmPasswordCheck.checked ? 'text' : 'password';
        });
    }

    // Event Listener cho Signup Form
    signupForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        
        if (typeof clearFormMessagesAndValidation === "function") {
            clearFormMessagesAndValidation(signupFormElements);
        }
        
        if (!validateSignupFormInternal()) {
            if (typeof displayGeneralFormMessage === "function") {
                displayGeneralFormMessage(generalFormErrorDiv, 'Please correct the errors in the form.');
            }
            return;
        }

        const email = emailInput.value;
        const password = passwordInput.value;
        
        // Lấy Turnstile response từ input ẩn
        const captchaToken = document.querySelector('[name="cf-turnstile-response"]')?.value || null;
        
        if (!captchaToken) {
            if (typeof displayGeneralFormMessage === "function") {
                displayGeneralFormMessage(generalFormErrorDiv, 'CAPTCHA verification is required. Please complete the challenge.');
            }
            if (typeof turnstile !== 'undefined' && turnstile.reset) turnstile.reset();
            return;
        }
        
        const submitButton = signupForm.querySelector('button[type="submit"]');
        if (typeof toggleFormElementsDisabled === "function") {
            toggleFormElementsDisabled(signupForm, true, 'Creating Account...');
        } else if (submitButton) {
            submitButton.disabled = true;
            if (!submitButton.dataset.originalText) submitButton.dataset.originalText = submitButton.textContent;
            submitButton.textContent = 'Creating Account...';
        }

        try {
            const response = await fetch('/api/auth/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, captchaToken }), // THÊM CAPTCHA TOKEN VÀO BODY
            });
            
            let data;
            let responseOk = response.ok; // Ghi lại trạng thái ok trước khi đọc response body
            try {
                data = await response.json();
            } catch (e) {
                data = { detail: "Received non-JSON response or network error from server." };
                if (!responseOk && response.headers.get("content-type")?.includes("text/html")) {
                    data.detail = `Server error (${response.status}). Please try again later.`;
                }
            }

            if (responseOk) { // Status 200-299 (202 cho signup)
                console.log('Signup successful or email resend initiated:', data);
                alert(data.message || 'Registration process initiated. Please check your email to verify your account.'); 
                window.location.href = `/signin.html?status=email_verification_pending&email=${encodeURIComponent(email)}`; 
            } else {
                console.error('Signup failed:', data || response.statusText);
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
                if (typeof turnstile !== 'undefined' && turnstile.reset) turnstile.reset();
            }
        } catch (error) {
            console.error('Network or unexpected error during signup:', error);
            if (typeof displayGeneralFormMessage === "function") {
                displayGeneralFormMessage(generalFormErrorDiv, 'A network error occurred. Please check your connection and try again.');
            } else {
                 alert('A network error occurred. Please check your connection and try again.');
            }
            if (typeof turnstile !== 'undefined' && turnstile.reset) turnstile.reset();
        } finally {
            if (typeof toggleFormElementsDisabled === "function") {
                toggleFormElementsDisabled(signupForm, false);
            } else if (submitButton) {
                submitButton.disabled = false;
                if (submitButton.dataset.originalText) submitButton.textContent = submitButton.dataset.originalText;
                else submitButton.textContent = "Create Account";
            }
        }
    });
}

/**
 * Thiết lập các event listener chung cho các trang xác thực (ví dụ: nút Google).
 */
function setupCommonAuthPageLogic() {
    const googleSignInBtn = document.getElementById('googleSignInBtn');
    if (googleSignInBtn) {
        googleSignInBtn.addEventListener('click', () => {
            const generalErrorDivCurrentPage = document.getElementById('generalFormError');
            if(generalErrorDivCurrentPage && typeof displayGeneralFormMessage === "function"){
                 displayGeneralFormMessage(generalErrorDivCurrentPage, '');
            }
            console.log("Google Sign-In button clicked. Redirecting to backend Google OAuth endpoint.");
            window.location.href = '/api/auth/google';
        });
    }
}


// --- KHỞI TẠO KHI DOM ĐÃ SẴN SÀNG ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("--- auth.js DOMContentLoaded event fired (v2.4) ---");
    
    setupCommonAuthPageLogic();

    if (document.getElementById('signupForm')) {
        console.log("auth.js: Found signupForm, setting up signup page specific event listeners.");
        setupSignupPageEventListeners();
    } else {
        console.log("auth.js: Not on signup page, skipping signup-specific listeners.");
    }
    
    console.log("--- auth.js DOMContentLoaded event listener finished (v2.4) ---");
});