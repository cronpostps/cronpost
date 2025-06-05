// frontend/js/dashboard.js
// Version: 1.2 (Implemented fetchAndDisplayMessageOverview to call API)

console.log("--- dashboard.js SCRIPT STARTED (v1.2) ---");

document.addEventListener('DOMContentLoaded', async () => {
    console.log("--- dashboard.js DOMContentLoaded event fired (v1.2) ---");

    const accessToken = localStorage.getItem('accessToken');
    if (!accessToken) {
        console.log("No access token found, redirecting to signin.");
        window.location.href = '/signin.html?status=session_expired';
        return;
    }

    // --- Lấy DOM Elements ---
    const welcomeMessageEl = document.getElementById('welcomeMessage');
    const accountStatusEl = document.getElementById('accountStatus');
    const countdownTimerEl = document.getElementById('countdownTimer');
    const countdownLabelEl = document.getElementById('countdownLabel');
    const mainActionButton = document.getElementById('mainActionButton');

    // Account Details
    const dashUserNameEl = document.getElementById('dashUserName');
    const dashMembershipTypeEl = document.getElementById('dashMembershipType');
    const upgradeNowBtn = document.getElementById('upgradeNowBtn');
    const manageSubscriptionBtn = document.getElementById('manageSubscriptionBtn');
    const dashUserTimezoneEl = document.getElementById('dashUserTimezone');
    const dashUserLanguageEl = document.getElementById('dashUserLanguage');
    const dashMessagesRemainingEl = document.getElementById('dashMessagesRemaining');
    const dashStorageUsedEl = document.getElementById('dashStorageUsed');
    const dashStorageLimitEl = document.getElementById('dashStorageLimit');

    // Message Overview
    const imStatusEl = document.getElementById('imStatus');
    const fmActiveCountEl = document.getElementById('fmActiveCount');
    const fmInactiveCountEl = document.getElementById('fmInactiveCount');
    const scmActiveCountEl = document.getElementById('scmActiveCount');
    const scmInactiveCountEl = document.getElementById('scmInactiveCount');

    // Quick Actions
    const createCronMessageBtn = document.getElementById('createCronMessageBtn');
    const createSimpleMessageBtn = document.getElementById('createSimpleMessageBtn');
    const uploadFileQuickBtn = document.getElementById('uploadFileQuickBtn');

    // Header elements
    const headerUserIdentifier = document.getElementById('headerUserIdentifier');
    const logoutButton = document.getElementById('logoutButton');
    const inAppUnreadCountSpan = document.getElementById('inAppUnreadCount');


    // --- Hàm Fetch Dữ liệu User và Cập nhật UI ---
    async function fetchAndDisplayUserData() {
        try {
            const response = await fetch('/api/users/me', {
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                }
            });

            if (response.ok) {
                const userData = await response.json();
                console.log("User data received:", userData);

                if (headerUserIdentifier) {
                    headerUserIdentifier.textContent = userData.user_name || userData.email;
                }
                if (welcomeMessageEl) {
                    welcomeMessageEl.textContent = `Welcome, ${userData.user_name || userData.email}!`;
                }
                if (accountStatusEl) {
                    accountStatusEl.textContent = formatAccountStatus(userData.account_status);
                }
                if (dashUserNameEl) dashUserNameEl.textContent = userData.user_name || 'N/A';
                if (dashMembershipTypeEl) dashMembershipTypeEl.textContent = userData.membership_type.charAt(0).toUpperCase() + userData.membership_type.slice(1);
                
                if (upgradeNowBtn && manageSubscriptionBtn) {
                    if (userData.membership_type === 'free') {
                        upgradeNowBtn.style.display = 'inline-block';
                        manageSubscriptionBtn.style.display = 'none';
                    } else if (userData.membership_type === 'premium') {
                        manageSubscriptionBtn.style.display = 'inline-block';
                        upgradeNowBtn.style.display = 'none';
                    } else {
                        upgradeNowBtn.style.display = 'none';
                        manageSubscriptionBtn.style.display = 'none';
                    }
                }

                if (dashUserTimezoneEl) dashUserTimezoneEl.textContent = userData.timezone || 'N/A';
                if (dashUserLanguageEl) dashUserLanguageEl.textContent = userData.language || 'N/A';
                
                if (dashMessagesRemainingEl) {
                    dashMessagesRemainingEl.textContent = userData.messages_remaining !== null 
                        ? String(userData.messages_remaining)
                        : 'N/A';
                }
                if (dashStorageUsedEl) {
                    dashStorageUsedEl.textContent = formatBytes(userData.uploaded_storage_bytes || 0);
                }
                if (dashStorageLimitEl) {
                    dashStorageLimitEl.textContent = userData.storage_limit_gb !== null 
                        ? `${userData.storage_limit_gb} GB` 
                        : (userData.membership_type === 'premium' ? '1 GB' : '0 GB');
                }

                updateCountdownAndAction(
                    userData.account_status, 
                    userData.next_clc_prompt_at, 
                    userData.wct_active_ends_at
                );
                
                // Gọi fetchAndDisplayMessageOverview VÀ fetchAndUpdateUnreadCount sau khi userData đã được tải
                await fetchAndDisplayMessageOverview(); // Sử dụng await để đảm bảo thứ tự nếu cần
                await fetchAndUpdateUnreadCount();

            } else if (response.status === 401) {
                console.log("Token invalid or expired, redirecting to signin.");
                localStorage.removeItem('accessToken');
                localStorage.removeItem('refreshToken');
                window.location.href = '/signin.html?status=session_expired';
            } else {
                const errorText = await response.text();
                console.error("Failed to fetch user data:", response.status, errorText);
                if (welcomeMessageEl) welcomeMessageEl.textContent = "Welcome!";
                if (accountStatusEl) accountStatusEl.textContent = "Error loading status";
                if (headerUserIdentifier) headerUserIdentifier.textContent = "User";
            }
        } catch (error) {
            console.error("Error fetching user data:", error);
            if (welcomeMessageEl) welcomeMessageEl.textContent = "Welcome!";
            if (accountStatusEl) accountStatusEl.textContent = "Error loading status";
        }
    }

    function formatAccountStatus(status) {
        if (!status) return 'Unknown';
        switch (status) {
            case 'INS': return 'Inactive (No Message Schedule)';
            case 'ANS_CLC': return 'Active (Countdown to Check-in Prompt)';
            case 'ANS_WCT': return 'Active (Waiting for Check-in)';
            case 'FNS': return 'Frozen (Sending Messages)';
            default: return status;
        }
    }
    
    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    let countdownInterval;
    function updateCountdownAndAction(accountStatus, nextClcPromptAt, wctActiveEndsAt, nextFnsSendAt = null) {
        if (countdownInterval) clearInterval(countdownInterval);
        if (!countdownTimerEl || !countdownLabelEl || !mainActionButton) return;

        let targetTime = null;
        let labelText = "";
        let actionButtonText = "";
        let actionButtonVisible = false;
        let actionButtonHandler = null;
        
        const currentMainActionButton = document.getElementById('mainActionButton');

        if (accountStatus === 'ANS_CLC' && nextClcPromptAt) {
            targetTime = new Date(nextClcPromptAt);
            labelText = "Next check-in prompt in:";
            actionButtonVisible = false;
        } else if (accountStatus === 'ANS_WCT' && wctActiveEndsAt) {
            targetTime = new Date(wctActiveEndsAt);
            labelText = "Check-in window closes in:";
            actionButtonText = "Check-in Now";
            actionButtonVisible = true;
            actionButtonHandler = handleCheckIn;
        } else if (accountStatus === 'FNS') {
            if (nextFnsSendAt) {
                targetTime = new Date(nextFnsSendAt);
                labelText = "Next message will be sent in:";
            } else {
                targetTime = null;
                labelText = "Account is Frozen. Messages are being processed.";
                countdownTimerEl.textContent = "PROCESSING";
            }
            actionButtonText = "STOP FNS";
            actionButtonVisible = true;
            actionButtonHandler = handleStopFns;
        } else if (accountStatus === 'INS') {
            labelText = "No active message schedule. Create an Initial Message to start.";
            countdownTimerEl.textContent = "N/A";
            actionButtonText = "Create Initial Message";
            actionButtonVisible = true;
            actionButtonHandler = () => { window.location.href = '/cron-message.html?type=im'; };
        } else {
            labelText = "Account status is unclear or no active schedule.";
            countdownTimerEl.textContent = "--:--:--";
            actionButtonVisible = false;
        }

        countdownLabelEl.textContent = labelText;

        if (currentMainActionButton) {
            if (actionButtonVisible) {
                currentMainActionButton.textContent = actionButtonText;
                currentMainActionButton.style.display = 'block';
                if (actionButtonHandler) {
                    const freshButton = currentMainActionButton.cloneNode(true);
                    currentMainActionButton.parentNode.replaceChild(freshButton, currentMainActionButton);
                    freshButton.addEventListener('click', actionButtonHandler);
                }
            } else {
                currentMainActionButton.style.display = 'none';
            }
        }
        
        if (targetTime) {
            countdownInterval = setInterval(() => {
                const now = new Date().getTime();
                const distance = targetTime - now;

                if (distance < 0) {
                    clearInterval(countdownInterval);
                    countdownTimerEl.textContent = "EXPIRED/TRIGGERED";
                    if (accountStatus === 'ANS_WCT') {
                        countdownLabelEl.textContent = "Check-in window closed. Processing messages if not checked-in.";
                    } else if (accountStatus === 'ANS_CLC') {
                        countdownLabelEl.textContent = "Check-in prompt period should have started.";
                    } else {
                        countdownLabelEl.textContent = "Process triggered or schedule ended.";
                    }
                    fetchAndDisplayUserData(); 
                    return;
                }

                const days = Math.floor(distance / (1000 * 60 * 60 * 24));
                const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
                const seconds = Math.floor((distance % (1000 * 60)) / 1000);
                
                let countdownText = "";
                if (days > 0) countdownText += `${days}d `;
                countdownText += `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
                countdownTimerEl.textContent = countdownText;

            }, 1000);
        } else if (accountStatus !== 'FNS' || (accountStatus === 'FNS' && !nextFnsSendAt)) { 
            if(countdownTimerEl && accountStatus !== 'INS' && (accountStatus !== 'FNS' || !nextFnsSendAt)) {
                countdownTimerEl.textContent = "--:--:--";
            }
        }
    }

    function handleCheckIn() {
        alert("Check-in button clicked! (Logic to be implemented - Call API /api/users/check-in)");
    }

    function handleStopFns() {
        alert("STOP FNS button clicked! (Logic to be implemented - Call API /api/users/stop-fns)");
    }
    
    // --- Fetch Message Overview ---
    async function fetchAndDisplayMessageOverview() {
        // Xóa các giá trị "API needed" cũ
        if (imStatusEl) imStatusEl.textContent = "Loading...";
        if (fmActiveCountEl) fmActiveCountEl.textContent = "Loading...";
        if (fmInactiveCountEl) fmInactiveCountEl.textContent = "Loading...";
        if (scmActiveCountEl) scmActiveCountEl.textContent = "Loading...";
        if (scmInactiveCountEl) scmInactiveCountEl.textContent = "Loading...";

        try {
            const response = await fetch('/api/messages/overview', {
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
            if (response.ok) {
                const overviewData = await response.json();
                if (imStatusEl) imStatusEl.textContent = overviewData.im_status || "N/A";
                if (fmActiveCountEl) fmActiveCountEl.textContent = String(overviewData.fm_active_count);
                if (fmInactiveCountEl) fmInactiveCountEl.textContent = String(overviewData.fm_inactive_count);
                if (scmActiveCountEl) scmActiveCountEl.textContent = String(overviewData.scm_active_count);
                if (scmInactiveCountEl) scmInactiveCountEl.textContent = String(overviewData.scm_inactive_count);
            } else {
                console.error("Failed to fetch message overview:", response.status);
                if (imStatusEl) imStatusEl.textContent = "Error";
                // Có thể set các count về "Error" hoặc "-"
            }
        } catch (error) {
            console.error("Error fetching message overview:", error);
            if (imStatusEl) imStatusEl.textContent = "Error";
        }
    }

    // --- Fetch Unread In-App Message Count (Placeholder) ---
    async function fetchAndUpdateUnreadCount() {
        if (!inAppUnreadCountSpan) return;
        const count = 0; 
        inAppUnreadCountSpan.textContent = count > 99 ? "99+" : String(count);
        inAppUnreadCountSpan.classList.remove('bg-danger', 'bg-success', 'bg-secondary');
        if (count > 0) {
            inAppUnreadCountSpan.classList.add('bg-danger');
            inAppUnreadCountSpan.style.display = 'inline-block';
        } else {
            inAppUnreadCountSpan.classList.add('bg-secondary'); 
            inAppUnreadCountSpan.style.display = 'inline-block';
        }
    }

    if (createCronMessageBtn) {
        createCronMessageBtn.onclick = () => { window.location.href = '/cron-message.html'; };
    }
    if (createSimpleMessageBtn) {
        createSimpleMessageBtn.onclick = () => { window.location.href = '/simple-cron-email-message.html'; };
    }
    if (uploadFileQuickBtn) {
        uploadFileQuickBtn.onclick = async () => {
            const userMembership = dashMembershipTypeEl ? dashMembershipTypeEl.textContent.toLowerCase() : 'free';
            if (userMembership !== 'premium') {
                alert("File upload is a Premium feature. Please upgrade your account.");
            } else {
                window.location.href = '/upload-attach-file.html';
            }
        };
    }

    if (logoutButton) {
        logoutButton.addEventListener('click', async (e) => {
            e.preventDefault();
            console.log("Logout button clicked");
            try {
                const signOutResponse = await fetch('/api/auth/signout', {
                    method: 'POST', 
                    headers: { 'Authorization': `Bearer ${accessToken}` }
                });
                if(signOutResponse.ok){
                    console.log("Successfully signed out from backend.");
                } else {
                    console.warn("Backend signout call failed or not implemented, proceeding with client-side logout.");
                }
            } catch (err) { console.error("Error calling signout API:", err); }
            
            localStorage.removeItem('accessToken');
            localStorage.removeItem('refreshToken');
            window.location.href = '/signin.html?status=signout_success';
        });
    }

    fetchAndDisplayUserData();

    console.log("--- dashboard.js DOMContentLoaded event listener finished (v1.2) ---");
});