// frontend/js/utils.js
// Version: 1.0
// Mô tả: Các hàm tiện ích dùng chung cho frontend

console.log("--- utils.js SCRIPT STARTED (v1.0) ---");

/**
 * Hiển thị lỗi/thành công cho một trường input cụ thể.
 * @param {HTMLElement} errorElement - Element div để hiển thị thông báo.
 * @param {string} message - Nội dung thông báo.
 * @param {string} type - 'error' hoặc 'success'. Default là 'error'.
 */
function displayFieldError(errorElement, message, type = 'error') {
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.display = message ? 'block' : 'none';
        // Giả định input nằm ngay trước div lỗi và có class form-control
        const inputElement = errorElement.previousElementSibling; 
        if (inputElement && inputElement.tagName === 'INPUT' && inputElement.classList.contains('form-control')) {
            inputElement.classList.remove('is-invalid', 'is-valid');
            if (message) {
                inputElement.classList.add(type === 'error' ? 'is-invalid' : 'is-valid');
            }
        }
        // Thêm class cho chính errorElement nếu muốn
        errorElement.className = message ? (type === 'error' ? 'invalid-feedback' : 'valid-feedback') : 'invalid-feedback';
    }
}

/**
 * Hiển thị thông báo chung của form (thường là alert).
 * @param {HTMLElement} alertElement - Element div alert để hiển thị thông báo.
 * @param {string} message - Nội dung thông báo.
 * @param {boolean} isSuccess - True nếu là thông báo thành công.
 */
function displayGeneralFormMessage(alertElement, message, isSuccess = false) {
    if (alertElement) {
        alertElement.textContent = message;
        alertElement.style.display = message ? 'block' : 'none';
        alertElement.className = 'alert mt-3'; // Reset các class alert cũ
        if (message) {
            alertElement.classList.add(isSuccess ? 'alert-success' : 'alert-danger');
        }
    }
}

/**
 * Xóa tất cả các thông báo lỗi/thành công trên một form cụ thể.
 * Cần truyền vào các element của form đó.
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
    if (formElements.confirmPasswordErrorDiv && formElements.confirmPasswordInput) { // Cho signup
        displayFieldError(formElements.confirmPasswordErrorDiv, '');
        formElements.confirmPasswordInput.classList.remove('is-invalid', 'is-valid');
    }
    // Thêm cho các trường khác nếu cần
}

/**
 * Vô hiệu hóa/Kích hoạt các input và button chính trên form.
 * @param {HTMLFormElement} formElement - Form element.
 * @param {boolean} disable - True để vô hiệu hóa.
 * @param {string} [buttonTextWhileDisabled] - Optional text cho nút submit khi đang disabled.
 */
function toggleFormElementsDisabled(formElement, disable, buttonTextWhileDisabled = null) {
    if (!formElement) return;

    const submitButton = formElement.querySelector('button[type="submit"]');
    const inputs = formElement.querySelectorAll('input:not([type="checkbox"]), select, textarea'); // Không disable checkbox

    if (submitButton) {
        submitButton.disabled = disable;
        if (disable && buttonTextWhileDisabled) {
            // Lưu text gốc nếu chưa có
            if (!submitButton.dataset.originalText) {
                submitButton.dataset.originalText = submitButton.textContent;
            }
            submitButton.textContent = buttonTextWhileDisabled;
        } else if (!disable && submitButton.dataset.originalText) {
            submitButton.textContent = submitButton.dataset.originalText;
        }
    }
    inputs.forEach(input => {
        input.disabled = disable;
    });

    // Cần xử lý riêng cho các nút khác như Google Sign-In nếu chúng nằm ngoài form
    const googleBtn = document.getElementById('googleSignInBtn'); // Giả sử có ID này
    if (googleBtn) {
        googleBtn.disabled = disable;
    }
}

/**
 * Formats an ISO timestamp string into a human-readable string in a specific timezone.
 * @param {string} isoTimestamp - The ISO 8601 timestamp string from the backend.
 * @param {string} targetTimezone - The IANA timezone string (e.g., 'Asia/Ho_Chi_Minh').
 * @returns {string} A formatted date-time string or 'N/A'.
 */
function formatTimestampInZone(isoTimestamp, targetTimezone) {
    if (!isoTimestamp) {
        return 'N/A';
    }

    // Validate the targetTimezone to prevent errors
    let validTimezone = 'UTC'; // Default to UTC
    try {
        // The 'timeZone' option in Intl.DateTimeFormat will throw an error for invalid timezones.
        // We can use this to validate.
        new Intl.DateTimeFormat(undefined, { timeZone: targetTimezone });
        validTimezone = targetTimezone;
    } catch (e) {
        console.warn(`Invalid or unsupported timezone provided: "${targetTimezone}". Falling back to UTC.`);
    }

    try {
        const date = new Date(isoTimestamp);
        
        // Use Intl.DateTimeFormat for robust, localized formatting
        const formatter = new Intl.DateTimeFormat('en-GB', { // en-GB for dd/mm/yyyy format
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false, // Use 24-hour format
            timeZone: validTimezone
        });

        return formatter.format(date);
    } catch (error) {
        console.error(`Error formatting date for timezone ${validTimezone}:`, error);
        // Fallback for safety
        return new Date(isoTimestamp).toLocaleString();
    }
}

/**
 * Calculates the GMT offset in minutes for a given IANA timezone.
 * @param {string} ianaTimeZone - The IANA timezone string (e.g., 'Asia/Ho_Chi_Minh').
 * @returns {number} The offset from GMT in minutes.
 */
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

/**
 * Formats a minute offset into a [GMT ±HH:mm] string.
 * @param {number} offsetMinutes - The offset in minutes.
 * @returns {string} The formatted GMT string.
 */
function formatGmtOffset(offsetMinutes) {
    const sign = offsetMinutes >= 0 ? '+' : '-';
    const absOffset = Math.abs(offsetMinutes);
    const hours = String(Math.floor(absOffset / 60)).padStart(2, '0');
    const minutes = String(absOffset % 60).padStart(2, '0');
    return `GMT ${sign}${hours}:${minutes}`;
}

/**
 * Formats an ISO timestamp string into a human-readable string in a specific timezone.
 * @param {string} isoTimestamp - The ISO 8601 timestamp string from the backend.
 * @param {string} targetTimezone - The IANA timezone string (e.g., 'Asia/Ho_Chi_Minh').
 * @returns {string} A formatted date-time string or 'N/A'.
 */
function formatTimestampInZone(isoTimestamp, targetTimezone) {
    if (!isoTimestamp) {
        return 'N/A';
    }

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
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
            timeZone: validTimezone
        });
        return formatter.format(date);
    } catch (error) {
        console.error(`Error formatting date for timezone ${validTimezone}:`, error);
        return new Date(isoTimestamp).toLocaleString();
    }
}

// /**
//  * Calculates the GMT offset in minutes for a given IANA timezone.
//  * @param {string} ianaTimeZone - The IANA timezone string (e.g., 'Asia/Ho_Chi_Minh').
//  * @returns {number} The offset from GMT in minutes.
//  */
// function getIanaTimezoneOffsetMinutes(ianaTimeZone) {
//     try {
//         const date = new Date();
//         const utcDate = new Date(date.toLocaleString('en-US', { timeZone: 'UTC' }));
//         const targetDate = new Date(date.toLocaleString('en-US', { timeZone: ianaTimeZone }));
//         return (targetDate.getTime() - utcDate.getTime()) / (1000 * 60);
//     } catch (e) {
//         console.error(`Could not calculate offset for timezone: ${ianaTimeZone}`, e);
//         return 0; // Fallback to 0 offset on error
//     }
// }

// /**
//  * Formats a minute offset into a [GMT ±HH:mm] string.
//  * @param {number} offsetMinutes - The offset in minutes.
//  * @returns {string} The formatted GMT string.
//  */
// function formatGmtOffset(offsetMinutes) {
//     const sign = offsetMinutes >= 0 ? '+' : '-';
//     const absOffset = Math.abs(offsetMinutes);
//     const hours = String(Math.floor(absOffset / 60)).padStart(2, '0');
//     const minutes = String(absOffset % 60).padStart(2, '0');
//     return `GMT ${sign}${hours}:${minutes}`;
// }