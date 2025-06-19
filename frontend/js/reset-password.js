// frontend/js/reset-password.js
// Version: 1.0
// Mô tả: Xử lý logic cho trang "Reset Password"

console.log("--- reset-password.js SCRIPT STARTED (v1.0) ---");

document.addEventListener('DOMContentLoaded', () => {
    console.log("--- reset-password.js DOMContentLoaded event fired (v1.0) ---");

    const resetPasswordForm = document.getElementById('resetPasswordForm');
    const newPasswordInput = document.getElementById('newPassword');
    const confirmNewPasswordInput = document.getElementById('confirmNewPassword');
    
    const newPasswordErrorDiv = document.getElementById('newPasswordError');
    const confirmNewPasswordErrorDiv = document.getElementById('confirmNewPasswordError');
    const generalFormMessageDiv = document.getElementById('generalFormMessage'); // Đổi tên từ generalFormError để phản ánh việc dùng cả cho success
    
    const showNewPasswordCheck = document.getElementById('showNewPasswordCheck');
    const showConfirmNewPasswordCheck = document.getElementById('showConfirmNewPasswordCheck');

    const loadingMessageDiv = document.getElementById('loadingMessage');
    const invalidTokenMessageDiv = document.getElementById('invalidTokenMessage');

    // Khởi tạo các element cho hàm tiện ích
    const formElements = {
        generalErrorDiv: generalFormMessageDiv, // Dùng chung generalFormMessageDiv làm generalErrorDiv
        newPasswordErrorDiv: newPasswordErrorDiv, newPasswordInput: newPasswordInput,
        confirmNewPasswordErrorDiv: confirmNewPasswordErrorDiv, confirmNewPasswordInput: confirmNewPasswordInput
    };

    // Clear messages và validation ban đầu
    if (typeof clearFormMessagesAndValidation === "function") {
        clearFormMessagesAndValidation(formElements);
    } else {
        console.error("reset-password.js: function clearFormMessagesAndValidation from utils.js is not available.");
    }

    // Xử lý Show/Hide Password
    if (showNewPasswordCheck && newPasswordInput && confirmNewPasswordInput) {
        showNewPasswordCheck.addEventListener('change', () => {
            const isChecked = showNewPasswordCheck.checked;
            newPasswordInput.type = isChecked ? 'text' : 'password';
            confirmNewPasswordInput.type = isChecked ? 'text' : 'password';
        });
    }

    function validateResetPasswordForm() {
        let isValid = true;
        if (typeof displayFieldError !== "function") {
            console.error("reset-password.js: function displayFieldError from utils.js is not available.");
            if (generalFormMessageDiv && typeof displayGeneralFormMessage === "function") {
                displayGeneralFormMessage(generalFormMessageDiv, "Page error. Please refresh.");
            }
            return false;
        }

        // Validate new password
        if (!newPasswordInput || !newPasswordInput.value) {
            displayFieldError(newPasswordErrorDiv, 'New password is required.');
            isValid = false;
        } else if (newPasswordInput.value.length < 6 || newPasswordInput.value.length > 20) {
            displayFieldError(newPasswordErrorDiv, 'Password must be 6-20 characters long.');
            isValid = false;
        } else {
            displayFieldError(newPasswordErrorDiv, '', 'success');
        }

        // Validate confirm new password
        if (!confirmNewPasswordInput || !confirmNewPasswordInput.value) {
            displayFieldError(confirmNewPasswordErrorDiv, 'Confirm new password is required.');
            isValid = false;
        } else if (newPasswordInput && newPasswordInput.value !== confirmNewPasswordInput.value) {
            displayFieldError(confirmNewPasswordErrorDiv, 'Passwords do not match.');
            isValid = false;
        } else {
            displayFieldError(confirmNewPasswordErrorDiv, '', 'success');
        }
        return isValid;
    }

    // Lấy token từ URL
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');

    if (!token) {
        loadingMessageDiv.classList.add('d-none'); // Ẩn loading
        invalidTokenMessageDiv.classList.remove('d-none'); // Hiện thông báo lỗi
        console.warn("reset-password.js: Token not found in URL.");
        return; // Dừng xử lý nếu không có token
    } else {
        // Có token, hiển thị form và ẩn loading
        loadingMessageDiv.classList.add('d-none');
        resetPasswordForm.classList.remove('d-none');
        console.log("reset-password.js: Token found, showing reset form.");
    }

    if (resetPasswordForm) {
        resetPasswordForm.addEventListener('submit', async (event) => {
            event.preventDefault();

            // Clear previous messages
            if (typeof clearFormMessagesAndValidation === "function") {
                clearFormMessagesAndValidation(formElements);
            }

            if (!validateResetPasswordForm()) {
                if (typeof displayGeneralFormMessage === "function") {
                    displayGeneralFormMessage(generalFormMessageDiv, 'Please correct the errors in the form.');
                }
                return;
            }

            const newPassword = newPasswordInput.value;
            const confirmNewPassword = confirmNewPasswordInput.value;
            const submitButton = resetPasswordForm.querySelector('button[type="submit"]');

            if (typeof toggleFormElementsDisabled === "function") {
                toggleFormElementsDisabled(resetPasswordForm, true, 'Resetting...');
            } else if (submitButton) {
                submitButton.disabled = true;
                if (!submitButton.dataset.originalText) submitButton.dataset.originalText = submitButton.textContent;
                submitButton.textContent = 'Resetting...';
            }

            try {
                // Gọi API backend để reset mật khẩu
                // Endpoint sẽ là /api/auth/reset-password
                const response = await fetch('/api/auth/reset-password', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ 
                        token: token,
                        new_password: newPassword,
                        confirm_new_password: confirmNewPassword 
                    }),
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
                    const messageToDisplay = data.message || 'Your password has been successfully reset! Redirecting to Sign In...';
                    if (typeof displayGeneralFormMessage === "function") {
                        displayGeneralFormMessage(generalFormMessageDiv, messageToDisplay, true); // True for success
                    } else {
                        alert(messageToDisplay);
                    }
                    resetPasswordForm.reset(); // Clear form
                    // Tự động chuyển hướng về trang signin sau 3 giây
                    setTimeout(() => {
                        window.location.href = '/signin?status=password_reset_success';
                    }, 3000);
                } else {
                    const errorMsg = data?.detail ? String(data.detail) : 'An unknown error occurred. Please try again.';
                    if (typeof displayGeneralFormMessage === "function") {
                        displayGeneralFormMessage(generalFormMessageDiv, errorMsg); // False for error (default)
                    } else {
                        alert(errorMsg);
                    }
                    // Nếu lỗi do token không hợp lệ/hết hạn, hiển thị lại thông báo lỗi token
                    if (data?.detail && (data.detail.includes("invalid reset token") || data.detail.includes("token has expired"))) {
                        resetPasswordForm.classList.add('d-none'); // Ẩn form
                        invalidTokenMessageDiv.classList.remove('d-none'); // Hiện thông báo lỗi token
                    }
                }
            } catch (error) {
                console.error('Network or unexpected error during password reset:', error);
                if (typeof displayGeneralFormMessage === "function") {
                    displayGeneralFormMessage(generalFormMessageDiv, 'A network error occurred. Please check your connection and try again.');
                } else {
                    alert('A network error occurred. Please check your connection and try again.');
                }
            } finally {
                if (typeof toggleFormElementsDisabled === "function") {
                    toggleFormElementsDisabled(resetPasswordForm, false);
                } else if (submitButton) {
                    submitButton.disabled = false;
                    if (submitButton.dataset.originalText) submitButton.textContent = submitButton.dataset.originalText;
                    else submitButton.textContent = "Reset Password";
                }
            }
        });
    }

    console.log("--- reset-password.js DOMContentLoaded event listener finished (v1.0) ---");
});