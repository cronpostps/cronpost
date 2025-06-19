// /frontend/js/pin-modal.js
// version 1.4
// - Added checkbox to toggle show/hide PIN functionality.
// - Can now display an initial error message passed to requestPinVerification.
// - Improved promise rejection handling on modal close.

document.addEventListener('DOMContentLoaded', () => {
    const modalElement = document.getElementById('otpPinModal');
    if (!modalElement) return;

    const otpForm = document.getElementById('otpPinForm');
    const otpInputs = document.querySelectorAll('.otp-input');
    const modalPrompt = document.getElementById('otpPinModalPrompt');
    const modalError = document.getElementById('otpPinModalError');
    const submitButton = otpForm.querySelector('button[type="submit"]');
    const showPinCheckbox = document.getElementById('showPinCheckbox'); // {* New: Get checkbox *}

    let resolvePinPromise;
    let rejectPinPromise;
    let isPromiseFulfilled = false; // Flag to check if promise was resolved

    // OTP Input Interaction Logic (no change)
    otpInputs.forEach((input, index) => {
        input.addEventListener('input', () => {
            if (input.value && index < otpInputs.length - 1) { otpInputs[index + 1].focus(); }
        });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Backspace' && !input.value && index > 0) { otpInputs[index - 1].focus(); }
        });
        input.addEventListener('paste', (e) => {
            e.preventDefault();
            const pasteData = (e.clipboardData || window.clipboardData).getData('text').trim();
            if (/^\d{4}$/.test(pasteData)) {
                for (let i = 0; i < otpInputs.length; i++) { otpInputs[i].value = pasteData[i]; }
                otpInputs[otpInputs.length - 1].focus();
            }
        });
    });

    // {* NEW: Toggle PIN visibility based on checkbox *}
    if (showPinCheckbox) {
        showPinCheckbox.addEventListener('change', () => {
            const isChecked = showPinCheckbox.checked;
            otpInputs.forEach(input => {
                input.type = isChecked ? 'text' : 'password';
            });
        });
    }

    // Form Submission Logic (no change)
    otpForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const pin = Array.from(otpInputs).map(input => input.value).join('');
        if (pin.length !== 4 || !/^\d{4}$/.test(pin)) {
            modalError.textContent = 'Please enter a valid 4-digit PIN.';
            modalError.style.display = 'block';
            return;
        }
        if (resolvePinPromise) {
            isPromiseFulfilled = true;
            resolvePinPromise(pin);
        }
        bootstrap.Modal.getInstance(modalElement).hide();
    });
    
    // Auto-focus Logic
    modalElement.addEventListener('shown.bs.modal', () => {
        if (otpInputs.length > 0) { 
            otpInputs[0].focus(); 
            // {* Ensure inputs are password type and checkbox is unchecked when modal shows *}
            otpInputs.forEach(input => { input.type = 'password'; });
            if (showPinCheckbox) { showPinCheckbox.checked = false; }
        }
    });

    // Modal Cleanup Logic
    modalElement.addEventListener('hidden.bs.modal', () => {
        if (rejectPinPromise && !isPromiseFulfilled) {
             rejectPinPromise(new Error('PIN verification cancelled.'));
        }
        // Reset for next use
        otpForm.reset();
        modalError.style.display = 'none';
        submitButton.disabled = false;
        submitButton.textContent = 'Confirm PIN';
        resolvePinPromise = null;
        rejectPinPromise = null;
        isPromiseFulfilled = false;
        // {* Reset PIN input types and checkbox when modal hides *}
        otpInputs.forEach(input => { input.type = 'password'; });
        if (showPinCheckbox) { showPinCheckbox.checked = false; }
    });

    // --- Global Function to Request PIN (UPDATED) ---
    window.requestPinVerification = (promptText = 'Please enter your 4-digit PIN.', initialError = null) => {
        return new Promise((resolve, reject) => {
            resolvePinPromise = resolve;
            rejectPinPromise = reject;

            modalPrompt.textContent = promptText;
            
            // {* Show initial error if provided *}
            if (initialError) {
                modalError.textContent = initialError;
                modalError.style.display = 'block';
            } else {
                modalError.style.display = 'none';
            }
            // {* Reset input values here before showing the modal *}
            otpInputs.forEach(input => { input.value = ''; });
            otpInputs[0].focus(); // {* Focus first input *}
            // {* Ensure inputs are password type and checkbox is unchecked when modal is requested *}
            otpInputs.forEach(input => { input.type = 'password'; });
            if (showPinCheckbox) { showPinCheckbox.checked = false; }
            // ==========================================

            const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
            modal.show();
        });
    };
});