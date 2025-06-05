// frontend/js/dashboard.js
// Version: 1.0
// Mô tả: Logic cho trang Dashboard (dashboard.html)

console.log("--- dashboard.js SCRIPT STARTED (v1.0) ---");

document.addEventListener('DOMContentLoaded', async () => {
    console.log("--- dashboard.js DOMContentLoaded event fired (v1.0) ---");

    const accessToken = localStorage.getItem('accessToken');
    if (!accessToken) {
        console.log("No access token found, redirecting to signin.");
        window.location.href = '/signin.html?status=session_expired'; // Hoặc một status khác
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
    const dashUserLanguageEl = document.getElementById('dashUserLanguage'); // Thêm từ HTML
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

    // Header elements (nếu dashboard.js quản lý logout và unread count)
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

                // Cập nhật Header
                if (headerUserIdentifier) {
                    headerUserIdentifier.textContent = userData.user_name || userData.email;
                }

                // Cập nhật Dashboard Header
                if (welcomeMessageEl) {
                    welcomeMessageEl.textContent = `Welcome, ${userData.user_name || userData.email}!`;
                }
                if (accountStatusEl) {
                    accountStatusEl.textContent = formatAccountStatus(userData.account_status);
                }

                // Cập nhật Account Details
                if (dashUserNameEl) dashUserNameEl.textContent = userData.user_name || 'N/A';
                if (dashMembershipTypeEl) dashMembershipTypeEl.textContent = userData.membership_type.charAt(0).toUpperCase() + userData.membership_type.slice(1);
                
                if (userData.membership_type === 'free' && upgradeNowBtn) {
                    upgradeNowBtn.style.display = 'inline-block';
                    if(manageSubscriptionBtn) manageSubscriptionBtn.style.display = 'none';
                } else if (userData.membership_type === 'premium' && manageSubscriptionBtn) {
                    manageSubscriptionBtn.style.display = 'inline-block';
                    if(upgradeNowBtn) upgradeNowBtn.style.display = 'none';
                }

                if (dashUserTimezoneEl) dashUserTimezoneEl.textContent = userData.timezone || 'N/A';
                if (dashUserLanguageEl) dashUserLanguageEl.textContent = userData.language || 'N/A';
                
                // Cần API để lấy messages_remaining và storage_limit/used
                // Tạm thời để N/A
                if (dashMessagesRemainingEl) dashMessagesRemainingEl.textContent = userData.messages_remaining !== undefined ? userData.messages_remaining : 'N/A (API needed)';
                if (dashStorageUsedEl) dashStorageUsedEl.textContent = formatBytes(userData.uploaded_storage_bytes || 0);
                if (dashStorageLimitEl) dashStorageLimitEl.textContent = userData.storage_limit_gb ? `${userData.storage_limit_gb} GB` : 'N/A (API needed)';


                // Cập nhật Đồng hồ Đếm ngược và Nút Hành động Chính (Sẽ cần logic phức tạp hơn)
                updateCountdownAndAction(userData.account_status, userData.next_clc_prompt_at, userData.wct_active_ends_at);
                
                // Fetch và cập nhật Message Overview (Sẽ cần API riêng)
                fetchAndDisplayMessageOverview();

                // Fetch và cập nhật số tin nhắn In-App chưa đọc
                fetchAndUpdateUnreadCount();

            } else if (response.status === 401) { // Unauthorized - Token không hợp lệ hoặc hết hạn
                console.log("Token invalid or expired, redirecting to signin.");
                localStorage.removeItem('accessToken');
                localStorage.removeItem('refreshToken');
                window.location.href = '/signin.html?status=session_expired';
            } else {
                console.error("Failed to fetch user data:", response.status, await response.text());
                if (welcomeMessageEl) welcomeMessageEl.textContent = "Welcome!";
                if (accountStatusEl) accountStatusEl.textContent = "Error loading status";
                 if (headerUserIdentifier) headerUserIdentifier.textContent = "User";
            }
        } catch (error) {
            console.error("Error fetching user data:", error);
            if (welcomeMessageEl) welcomeMessageEl.textContent = "Welcome!";
            if (accountStatusEl) accountStatusEl.textContent = "Error loading status";
            // Có thể redirect về signin nếu có lỗi nghiêm trọng
            // localStorage.removeItem('accessToken');
            // window.location.href = '/signin.html?status=error_loading_dashboard';
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

    // --- Đồng hồ đếm ngược và Nút Hành động ---
    let countdownInterval;
    function updateCountdownAndAction(accountStatus, nextClcPromptAt, wctActiveEndsAt, nextFnsSendAt = null) {
        if (countdownInterval) clearInterval(countdownInterval);
        if (!countdownTimerEl || !countdownLabelEl || !mainActionButton) return;

        let targetTime = null;
        let labelText = "";
        let actionButtonText = "";
        let actionButtonVisible = false;
        let actionButtonHandler = null;

        if (accountStatus === 'ANS_CLC' && nextClcPromptAt) {
            targetTime = new Date(nextClcPromptAt);
            labelText = "Next check-in prompt in:";
            actionButtonVisible = false; // Nút check-in bị disable trong CLC
        } else if (accountStatus === 'ANS_WCT' && wctActiveEndsAt) {
            targetTime = new Date(wctActiveEndsAt);
            labelText = "Check-in window closes in (IM will be sent):"; // Hoặc "IM will be sent in:"
            actionButtonText = "Check-in Now";
            actionButtonVisible = true;
            actionButtonHandler = handleCheckIn;
        } else if (accountStatus === 'FNS' && nextFnsSendAt) { // Giả sử có nextFnsSendAt
            targetTime = new Date(nextFnsSendAt);
            labelText = "Next message will be sent in:";
            actionButtonText = "STOP FNS";
            actionButtonVisible = true;
            actionButtonHandler = handleStopFns;
        } else if (accountStatus === 'INS') {
            labelText = "No active message schedule. Create an Initial Message to start.";
            countdownTimerEl.textContent = "N/A";
            actionButtonText = "Create Initial Message"; // Link đến trang tạo IM
            actionButtonVisible = true;
            actionButtonHandler = () => { window.location.href = '/cron-message.html?type=im'; };
        } else {
            labelText = "No active schedule or status unclear.";
            countdownTimerEl.textContent = "--:--:--";
             actionButtonVisible = false;
        }

        countdownLabelEl.textContent = labelText;
        if (actionButtonVisible) {
            mainActionButton.textContent = actionButtonText;
            mainActionButton.style.display = 'block';
            // Gỡ bỏ event listener cũ và thêm mới
            mainActionButton.replaceWith(mainActionButton.cloneNode(true)); // Cách đơn giản để xóa listener
            document.getElementById('mainActionButton').addEventListener('click', actionButtonHandler);

        } else {
            mainActionButton.style.display = 'none';
        }
        
        if (targetTime) {
            countdownInterval = setInterval(() => {
                const now = new Date().getTime();
                const distance = targetTime - now;

                if (distance < 0) {
                    clearInterval(countdownInterval);
                    countdownTimerEl.textContent = "EXPIRED/SENDING";
                    countdownLabelEl.textContent = "Process triggered or schedule ended.";
                    // TODO: Có thể fetch lại user data để cập nhật trạng thái
                    fetchAndDisplayUserData(); // Tải lại dữ liệu khi countdown kết thúc
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
        }
    }

    function handleCheckIn() {
        // TODO: Implement check-in logic (call API, có thể cần PIN)
        alert("Check-in button clicked! (Logic to be implemented - Call API /api/users/check-in)");
        // Sau khi check-in thành công, nên fetchAndDisplayUserData();
    }

    function handleStopFns() {
        // TODO: Implement stop FNS logic (call API, yêu cầu PIN)
        alert("STOP FNS button clicked! (Logic to be implemented - Call API /api/users/stop-fns)");
        // Sau khi dừng FNS thành công, nên fetchAndDisplayUserData();
    }
    
    // --- Fetch Message Overview ---
    async function fetchAndDisplayMessageOverview() {
        // TODO: Tạo API backend GET /api/messages/overview
        // API này sẽ trả về số lượng IM (status), FM (active/inactive), SCM (active/inactive)
        // Ví dụ response:
        // { 
        //   "im_status": "Active" | "Inactive" | "Not Set",
        //   "fm_active_count": 2,
        //   "fm_inactive_count": 1,
        //   "scm_active_count": 0,
        //   "scm_inactive_count": 1 
        // }
        if (imStatusEl) imStatusEl.textContent = "N/A (API needed)";
        if (fmActiveCountEl) fmActiveCountEl.textContent = "0 (API needed)";
        if (fmInactiveCountEl) fmInactiveCountEl.textContent = "0 (API needed)";
        if (scmActiveCountEl) scmActiveCountEl.textContent = "0 (API needed)";
        if (scmInactiveCountEl) scmInactiveCountEl.textContent = "0 (API needed)";
    }

    // --- Fetch Unread In-App Message Count ---
    async function fetchAndUpdateUnreadCount() {
        if (!inAppUnreadCountSpan) return;
        try {
            const response = await fetch('/api/messaging/unread-count', { // Endpoint API cần tạo
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
            if (response.ok) {
                const data = await response.json();
                const count = data.unread_count || 0;
                inAppUnreadCountSpan.textContent = count;
                inAppUnreadCountSpan.classList.remove('bg-danger', 'bg-success', 'bg-secondary');
                if (count > 0) {
                    inAppUnreadCountSpan.classList.add('bg-danger');
                    inAppUnreadCountSpan.style.display = 'inline-block';
                } else {
                    inAppUnreadCountSpan.classList.add('bg-success'); // Hoặc một màu trung tính
                    inAppUnreadCountSpan.style.display = 'inline-block'; // Vẫn hiển thị số 0
                }
            } else { inAppUnreadCountSpan.style.display = 'none'; }
        } catch (error) { console.error("Error fetching unread in-app messages:", error); if(inAppUnreadCountSpan) inAppUnreadCountSpan.style.display = 'none'; }
    }


    // --- Event Listeners cho Quick Actions ---
    if (createCronMessageBtn) {
        createCronMessageBtn.onclick = () => { window.location.href = '/cron-message.html'; };
    }
    if (createSimpleMessageBtn) {
        createSimpleMessageBtn.onclick = () => { window.location.href = '/simple-cron-email-message.html'; };
    }
    if (uploadFileQuickBtn) {
        uploadFileQuickBtn.onclick = async () => {
            // Cần kiểm tra membership_type từ userData (đã fetch trước đó)
            const userMembership = dashMembershipTypeEl ? dashMembershipTypeEl.textContent.toLowerCase() : 'free';
            if (userMembership !== 'premium') {
                alert("File upload is a Premium feature. Please upgrade your account.");
                // TODO: Chuyển hướng đến trang nâng cấp hoặc hiển thị modal
            } else {
                window.location.href = '/upload-attach-file.html';
            }
        };
    }

    // --- Event Listener cho Logout ---
    if (logoutButton) {
        logoutButton.addEventListener('click', async (e) => {
            e.preventDefault();
            console.log("Logout button clicked");
            localStorage.removeItem('accessToken');
            localStorage.removeItem('refreshToken');
            // TODO: Gọi API backend /api/auth/signout để vô hiệu hóa token phía server (nếu cần)
            // try {
            //     await fetch('/api/auth/signout', { 
            //         method: 'POST', 
            //         headers: { 'Authorization': `Bearer ${accessToken}` } // Gửi token hiện tại để backend blacklist
            //     });
            // } catch (err) { console.error("Error calling signout API:", err); }
            window.location.href = '/signin.html?status=signout_success';
        });
    }

    // --- Khởi tạo lần đầu ---
    fetchAndDisplayUserData(); // Gọi hàm để tải dữ liệu user và cập nhật UI

    console.log("--- dashboard.js DOMContentLoaded event listener finished (v1.0) ---");
});