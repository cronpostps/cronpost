// /frontend/js/signup.js
// version 1.0

document.addEventListener('DOMContentLoaded', () => {
    const signupForm = document.getElementById('signupForm');
    const formStatusMessage = document.getElementById('formStatusMessage');

    if (signupForm) {
        signupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            toggleFormElementsDisabled(signupForm, true, 'Creating Account...');

            const email = document.getElementById('email').value;
            const userName = document.getElementById('userName').value;
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;

            if (password !== confirmPassword) {
                displayGeneralFormMessage(formStatusMessage, "Passwords do not match.", false);
                toggleFormElementsDisabled(signupForm, false);
                return;
            }

            // Tự động lấy timezone từ trình duyệt
            const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

            try {
                const response = await fetch('/api/auth/signup', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        email: email,
                        user_name: userName,
                        password: password,
                        confirm_password: confirmPassword,
                        timezone: userTimezone // Gửi timezone lên backend
                    })
                });

                const result = await response.json();

                if (!response.ok) {
                    throw new Error(result.detail || 'An unknown error occurred.');
                }

                // Nếu thành công, có thể chuyển hướng hoặc hiển thị thông báo
                displayGeneralFormMessage(formStatusMessage, 'Account created successfully! Please check your email to confirm your account.', true);
                signupForm.reset();

            } catch (error) {
                displayGeneralFormMessage(formStatusMessage, error.message, false);
            } finally {
                toggleFormElementsDisabled(signupForm, false);
            }
        });
    }
});