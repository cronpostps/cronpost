// frontend/js/dashboard.js
// Version: 1.9.0
// - Refactored all API calls to use the global fetchWithAuth wrapper.
// - Refactored PIN actions (Check-in, Stop FNS) to use the executeActionWithPinVerification utility.

console.log("--- dashboard.js SCRIPT STARTED (v1.9.0) ---");

document.addEventListener('DOMContentLoaded', async () => {
    console.log("--- dashboard.js DOMContentLoaded event fired (v1.9.0) ---");

    // --- START: ROBUST TOKEN HANDLING ---
    // Token handling logic remains the same, but now relies on fetchWithAuth for expiry
    const url = new URL(window.location.href);
    const tokenFromUrl = url.searchParams.get("token");

    if (tokenFromUrl) {
        console.log("DASHBOARD (1.9.0): Token found in URL:", tokenFromUrl.substring(0, 15) + "..."); // Log a snippet
        localStorage.setItem('accessToken', tokenFromUrl);
        console.log("DASHBOARD (1.9.0): Token has been set in localStorage.");

        // Clean the token from the URL more safely
        url.searchParams.delete("token");
        window.history.replaceState({}, document.title, url.toString());
        console.log("DASHBOARD (1.9.0): URL has been cleaned.");
    }

    const accessToken = localStorage.getItem('accessToken');
    console.log("DASHBOARD (1.9.0): Checking for accessToken in localStorage. Found:", !!accessToken);

    if (!accessToken) {
        console.error("DASHBOARD (1.9.0): No accessToken found after check. Redirecting to signin.");
        window.location.href = '/signin?status=session_expired';
        return; // Stop execution
    }
    // --- END: ROBUST TOKEN HANDLING ---

    let clockInterval;

    function updateUserClock(userTimezone) {
        if (clockInterval) clearInterval(clockInterval);
        
        const clockEl = document.getElementById('userCurrentTime');
        if (!clockEl) return;
        if (!userTimezone) {
            clockEl.textContent = "Timezone not set";
            return;
        }

        const updateClock = () => {
            try {
                const now = new Date();
                const timeString = now.toLocaleTimeString("en-GB", {
                    timeZone: userTimezone,
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false
                });
                const dateString = now.toLocaleDateString("en-GB", {
                    timeZone: userTimezone,
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit'
                });

                // {* THÊM LOGIC TÍNH TOÁN GMT OFFSET *}
                let gmtString = '';
                // {* Kiểm tra xem các hàm tiện ích có tồn tại không *}
                if (typeof formatGmtOffset === 'function' && typeof getIanaTimezoneOffsetMinutes === 'function') {
                    const offsetMinutes = getIanaTimezoneOffsetMinutes(userTimezone);
                    gmtString = formatGmtOffset(offsetMinutes);
                }
                // {* KẾT THÚC LOGIC MỚI *}

                // {* Cập nhật text hiển thị với định dạng mới *}
                clockEl.textContent = `${timeString} - ${dateString} [${gmtString}]`;

            } catch (e) {
                console.error("Error updating clock with timezone:", userTimezone, e);
                clockEl.textContent = `Invalid Timezone: ${userTimezone}`;
                clearInterval(clockInterval);
            }
        };
        
        updateClock();
        clockInterval = setInterval(updateClock, 1000);
    }

    
    let currentUserSettings = {
        use_pin_for_all_actions: false
    };

    const welcomeMessageEl = document.getElementById('welcomeMessage');
    const accountStatusEl = document.getElementById('accountStatus');
    const countdownTimerEl = document.getElementById('countdownTimer');
    const countdownLabelEl = document.getElementById('countdownLabel');
    const mainActionButton = document.getElementById('mainActionButton');
    const generalDashboardMessageEl = document.getElementById('generalDashboardMessage');

    const dashUserNameEl = document.getElementById('dashUserName');
    const dashMembershipTypeEl = document.getElementById('dashMembershipType');
    const upgradeNowBtn = document.getElementById('upgradeNowBtn');
    const manageSubscriptionBtn = document.getElementById('manageSubscriptionBtn');
    const dashUserTimezoneEl = document.getElementById('dashUserTimezone');
    const dashUserLanguageEl = document.getElementById('dashUserLanguage');
    const dashMessagesRemainingEl = document.getElementById('dashMessagesRemaining');
    const dashStorageUsedEl = document.getElementById('dashStorageUsed');
    const dashStorageLimitEl = document.getElementById('dashStorageLimit');

    const imStatusEl = document.getElementById('imStatus');
    const fmActiveCountEl = document.getElementById('fmActiveCount');
    const fmInactiveCountEl = document.getElementById('fmInactiveCount');
    const scmActiveCountEl = document.getElementById('scmActiveCount');
    const scmInactiveCountEl = document.getElementById('scmInactiveCount');

    const createCronMessageBtn = document.getElementById('createCronMessageBtn');
    const createSimpleMessageBtn = document.getElementById('createSimpleMessageBtn');
    const inAppMessagingQuickBtn = document.getElementById('inAppMessagingQuickBtn');

    const headerUserIdentifier = document.getElementById('headerUserIdentifier');
    const logoutButton = document.getElementById('logoutButton');
    const inAppUnreadCountSpanHeader = document.getElementById('inAppUnreadCount');
    const quickActionUnreadCountSpan = document.getElementById('quickActionUnreadCount');

    function displayDashboardMessage(message, isSuccess = false) {
        if (generalDashboardMessageEl) {
            generalDashboardMessageEl.textContent = message;
            generalDashboardMessageEl.className = 'alert mt-3';
            if (message) {
                generalDashboardMessageEl.classList.add(isSuccess ? 'alert-success' : 'alert-danger');
                generalDashboardMessageEl.style.display = 'block';
            } else {
                generalDashboardMessageEl.style.display = 'none';
            }
        } else if (message) {
            alert(message);
        }
    }

    async function fetchAndDisplayUserData() {
        displayDashboardMessage("");
        try {
            // {* SỬ DỤNG fetchWithAuth, bỏ header và kiểm tra 401 thủ công *}
            const response = await fetchWithAuth('/api/users/me');

            if (response.ok) {
                const userData = await response.json();
                console.log("User data received for dashboard:", userData);
                currentUserSettings.use_pin_for_all_actions = userData.use_pin_for_all_actions || false;

                if (headerUserIdentifier) headerUserIdentifier.textContent = userData.user_name || userData.email;
                if (welcomeMessageEl) welcomeMessageEl.textContent = `Welcome, ${userData.user_name || userData.email}!`;
                if (accountStatusEl) accountStatusEl.textContent = formatAccountStatus(userData.account_status);
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

                // {* THAY ĐỔI LOGIC HIỂN THỊ TIMEZONE TẠI ĐÂY *}
                if (dashUserTimezoneEl) {
                    const ianaTimezone = userData.timezone;
                    if (ianaTimezone && typeof formatGmtOffset === 'function' && typeof getIanaTimezoneOffsetMinutes === 'function') {
                        const offsetMinutes = getIanaTimezoneOffsetMinutes(ianaTimezone);
                        const gmtString = formatGmtOffset(offsetMinutes);
                        dashUserTimezoneEl.textContent = `[${gmtString}] - ${ianaTimezone}`;
                    } else {
                        // {* Fallback nếu không có timezone hoặc không tìm thấy hàm tiện ích *}
                        dashUserTimezoneEl.textContent = ianaTimezone || 'N/A';
                    }
                }
                // {* KẾT THÚC THAY ĐỔI *}

                if (dashUserLanguageEl) dashUserLanguageEl.textContent = userData.language || 'N/A';
                if (dashMessagesRemainingEl) dashMessagesRemainingEl.textContent = userData.messages_remaining !== null ? String(userData.messages_remaining) : 'N/A';
                if (dashStorageUsedEl) dashStorageUsedEl.textContent = formatBytes(userData.uploaded_storage_bytes || 0);
                if (dashStorageLimitEl) dashStorageLimitEl.textContent = userData.storage_limit_gb !== null ? `${userData.storage_limit_gb} GB` : (userData.membership_type === 'premium' ? '1 GB' : '0 GB');
                
                updateUserClock(userData.timezone); 
                updateCountdownAndAction(
                    userData.account_status, 
                    userData.next_clc_prompt_at, 
                    userData.wct_active_ends_at,
                    userData.next_fns_send_at
                );
                
                await fetchAndDisplayMessageOverview();
                await fetchAndUpdateUnreadCount();

            } else {
                const errorText = await response.text();
                console.error("Failed to fetch user data:", response.status, errorText);
                displayDashboardMessage(`Error loading user data: ${response.status}. Please try refreshing.`, false);
                if (headerUserIdentifier) headerUserIdentifier.textContent = "User";
            }
        } catch (error) {
            console.error("Error fetching user data:", error);
            // {* fetchWithAuth sẽ xử lý lỗi session, các lỗi mạng khác sẽ hiển thị ở đây *}
            if (error.message !== 'Session expired.' && error.message !== 'Request failed with status 401') { // Bổ sung kiểm tra để tránh trùng lặp thông báo
                displayDashboardMessage("Network error while loading user data. Please check your connection.", false);
            }
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
        // {* Luôn xóa interval cũ trước khi bắt đầu cái mới để tránh nhiều interval chạy song song *}
        if (countdownInterval) clearInterval(countdownInterval);

        const currentMainActionButton = document.getElementById('mainActionButton');
        if (!countdownTimerEl || !countdownLabelEl || !currentMainActionButton) return;

        let targetTime = null;
        let labelText = "";
        let actionButtonText = "";
        let actionButtonVisible = false;
        let actionButtonHandler = null;

        if (accountStatus === 'ANS_CLC' && nextClcPromptAt) {
            targetTime = new Date(nextClcPromptAt);
            labelText = "Next check-in prompt in:";
        } else if (accountStatus === 'ANS_WCT' && wctActiveEndsAt) {
            targetTime = new Date(wctActiveEndsAt);
            labelText = "Check-in window closes in:";
            actionButtonText = "Check-in Now";
            actionButtonVisible = true;
            actionButtonHandler = handleCheckIn;
        } else if (accountStatus === 'FNS') {
            labelText = nextFnsSendAt ? "The next message will be sent in:" : "Account is Frozen. Messages are being processed.";
            targetTime = nextFnsSendAt ? new Date(nextFnsSendAt) : null;
            if (!targetTime) countdownTimerEl.textContent = "PROCESSING";
            actionButtonText = "STOP Sending";
            actionButtonVisible = true;
            actionButtonHandler = handleStopFns;
        } else if (accountStatus === 'INS') {
            labelText = "No active message schedule. Create an Initial Message to start.";
            countdownTimerEl.textContent = "N/A";
            actionButtonText = "Create Initial Message";
            actionButtonVisible = true;
            actionButtonHandler = () => { window.location.href = '/cron-message?type=im'; };
        } else {
            labelText = "Account status is unclear or no active schedule.";
            countdownTimerEl.textContent = "--:--:--";
        }

        countdownLabelEl.textContent = labelText;

        // {* Cập nhật nút hành động *}
        if (actionButtonVisible) {
            currentMainActionButton.textContent = actionButtonText;
            currentMainActionButton.style.display = 'block';
            const freshButton = currentMainActionButton.cloneNode(true);
            currentMainActionButton.parentNode.replaceChild(freshButton, currentMainActionButton);
            if (actionButtonHandler) {
                freshButton.addEventListener('click', actionButtonHandler);
            }
        } else {
            currentMainActionButton.style.display = 'none';
        }
        
        // {* Logic đếm ngược đã được làm chặt chẽ hơn *}
        if (targetTime) {
            countdownInterval = setInterval(() => {
                const distance = targetTime.getTime() - new Date().getTime();

                if (distance < 0) {
                    // {* ĐIỂM SỬA QUAN TRỌNG NHẤT *}
                    // {* Dừng vòng lặp và chỉ gọi làm mới dữ liệu MỘT LẦN *}
                    clearInterval(countdownInterval); 
                    console.log("Countdown finished. Refreshing data once...");
                    countdownTimerEl.textContent = "UPDATING...";
                    fetchAndDisplayUserData(); // {* Gọi làm mới dữ liệu *}
                    return; // {* Thoát khỏi interval này *}
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
        }
    }

    // {* === PIN ACTION HANDLERS (REFACTORED) === *}
    async function handleCheckIn() {
        displayDashboardMessage("");
        const currentMainActionButton = document.getElementById('mainActionButton');
        
        try {
            const apiCallback = async (pin) => {
                const response = await fetchWithAuth('/api/users/check-in', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }, // fetchWithAuth đã xử lý Auth header
                    body: JSON.stringify({ pin_code: pin })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || "Check-in API call failed.");
                return result;
            };

            // {* Sử dụng hàm tiện ích thay vì prompt() và logic enable/disable nút *}
            await executeActionWithPinVerification(
                "Please enter your 4-digit PIN to check-in:", 
                apiCallback, 
                currentUserSettings.use_pin_for_all_actions,
                currentMainActionButton,
                "Checking In..."
            );
            
            displayDashboardMessage("Check-in successful! Reloading dashboard...", true);
            // {* Tải lại dữ liệu dashboard sau khi thành công *}
            await fetchAndDisplayUserData();

        } catch (error) {
            console.error("Error during check-in:", error);
            if (error.message !== 'Session expired.' && error.message !== 'Action cancelled.' && error.message !== 'Request failed with status 401') {
                displayDashboardMessage(`Error during check-in: ${error.message}`, false);
            }
        } finally {
            // {* executeActionWithPinVerification sẽ tự handle trạng thái nút *}
            // {* Đảm bảo nút được khôi phục trạng thái nếu có lỗi xảy ra mà không thông qua executeActionWithPinVerification *}
            if (currentMainActionButton) {
                currentMainActionButton.disabled = false;
            }
        }
    }

    async function handleStopFns() {
        displayDashboardMessage("");
        const currentMainActionButton = document.getElementById('mainActionButton');

        try {
            // {* Luôn yêu cầu PIN để dừng FNS, dùng hàm tiện ích *}
            const apiCallback = async (pin) => {
                const response = await fetchWithAuth('/api/users/stop-fns', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }, // fetchWithAuth đã xử lý Auth header
                    body: JSON.stringify({ pin_code: pin })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || "Stop FNS API call failed.");
                return result;
            };

            await executeActionWithPinVerification(
                "To stop FNS, please enter your 4-digit PIN:", 
                apiCallback, 
                true, // Luôn yêu cầu PIN cho Stop FNS
                currentMainActionButton,
                "Stopping FNS..."
            );
            
            displayDashboardMessage("FNS stopped successfully! Reloading dashboard...", true);
            // {* Tải lại dữ liệu dashboard sau khi thành công *}
            await fetchAndDisplayUserData();

        } catch (error) {
            console.error("Error during stop FNS:", error);
            if (error.message !== 'Session expired.' && error.message !== 'Action cancelled.' && error.message !== 'Request failed with status 401') {
                displayDashboardMessage(`Error stopping FNS: ${error.message}`, false);
            }
        } finally {
            if (currentMainActionButton) {
                currentMainActionButton.disabled = false;
            }
        }
    }
    
    async function fetchAndDisplayMessageOverview() { 
        if (imStatusEl) imStatusEl.textContent = "Loading...";
        if (fmActiveCountEl) fmActiveCountEl.textContent = "Loading...";
        if (fmInactiveCountEl) fmInactiveCountEl.textContent = "Loading...";
        if (scmActiveCountEl) scmActiveCountEl.textContent = "Loading...";
        if (scmInactiveCountEl) scmInactiveCountEl.textContent = "Loading...";

        try {
            // {* SỬ DỤNG fetchWithAuth *}
            const response = await fetchWithAuth('/api/messages/overview');
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
                if (fmActiveCountEl) fmActiveCountEl.textContent = "-";
                if (fmInactiveCountEl) fmInactiveCountEl.textContent = "-";
                if (scmActiveCountEl) scmActiveCountEl.textContent = "-";
                if (scmInactiveCountEl) scmInactiveCountEl.textContent = "-";
            }
        } catch (error) {
            console.error("Error fetching message overview:", error);
            if (imStatusEl) imStatusEl.textContent = "Error";
        }
    }

    // {* Event Listeners *}
    if (createCronMessageBtn) createCronMessageBtn.onclick = () => { window.location.href = '/ucm'; };
    if (createSimpleMessageBtn) createSimpleMessageBtn.onclick = () => { window.location.href = '/scm'; };
    if (inAppMessagingQuickBtn) inAppMessagingQuickBtn.onclick = () => { window.location.href = '/iam'; };
    if (logoutButton) { 
        logoutButton.addEventListener('click', async (e) => {
            e.preventDefault();
            console.log("Logout button clicked");
            try {
                // {* SỬ DỤNG fetchWithAuth *}
                const signOutResponse = await fetchWithAuth('/api/auth/signout', {
                    method: 'POST' 
                    // {* fetchWithAuth đã xử lý Authorization header *}
                });
                if(signOutResponse.ok){
                    console.log("Successfully signed out from backend.");
                } else {
                    console.warn("Backend signout call failed or not implemented, proceeding with client-side logout.");
                }
            } catch (err) { 
                console.error("Error calling signout API:", err); 
                // {* Không cần alert vì fetchWithAuth sẽ xử lý lỗi session chung *}
            }
            
            localStorage.removeItem('accessToken');
            localStorage.removeItem('refreshToken');
            window.location.href = '/signin?status=signout_success';
        });
    }

    fetchAndDisplayUserData();

    console.log("--- dashboard.js DOMContentLoaded event listener finished (v1.9.0) ---");
});