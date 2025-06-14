// /frontend/js/header.js
// version 1.0
// Handles all logic for the shared _header-dashboard partial.

console.log("--- header.js SCRIPT STARTED (v1.0) ---");

function initializeSharedHeader() {
    const accessToken = localStorage.getItem('accessToken');
    if (!accessToken) {
        // If there's no token, no need to do anything here.
        // Page-specific scripts will handle redirects.
        return;
    }

    // --- DOM Elements from Header ---
    const headerUserIdentifier = document.getElementById('headerUserIdentifier');
    const logoutButton = document.getElementById('logoutButton');
    const inAppUnreadCountSpanHeader = document.getElementById('inAppUnreadCount');

    // --- Functions for Header ---

    // Fetches minimal user data needed for the header
    async function fetchHeaderUserData() {
        if (!headerUserIdentifier) return;
        try {
            const response = await fetch('/api/users/me', {
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
            if (response.ok) {
                const userData = await response.json();
                headerUserIdentifier.textContent = userData.user_name || userData.email;
            } else {
                 headerUserIdentifier.textContent = "User";
                 console.error("Header: Failed to fetch user data", response.status);
            }
        } catch (error) {
            headerUserIdentifier.textContent = "User";
            console.error("Header: Network error fetching user data", error);
        }
    }

    // Fetches the unread message count for the notification badge
    async function fetchAndUpdateUnreadCount() {
        if (!inAppUnreadCountSpanHeader) return;
        
        inAppUnreadCountSpanHeader.style.display = 'none'; 
        
        try {
            const response = await fetch('/api/messaging/unread-count', {
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
            if (response.ok) {
                const data = await response.json();
                const count = data.unread_count || 0;
                
                if (count > 0) {
                    inAppUnreadCountSpanHeader.textContent = count > 99 ? "99+" : String(count);
                    inAppUnreadCountSpanHeader.classList.add('bg-danger');
                    inAppUnreadCountSpanHeader.style.display = 'inline-block';
                }
            } else {
                console.error("Header: Failed to fetch unread message count:", response.status);
            }
        } catch (error) {
            console.error("Header: Error fetching unread message count:", error);
        }
    }

    // --- Event Listeners for Header ---

    if (logoutButton) {
        logoutButton.addEventListener('click', async (e) => {
            e.preventDefault();
            try {
                await fetch('/api/auth/signout', {
                    method: 'POST', 
                    headers: { 'Authorization': `Bearer ${accessToken}` }
                });
            } catch (err) {
                console.error("Error calling signout API, proceeding with client-side logout anyway.", err);
            }
            
            localStorage.removeItem('accessToken');
            localStorage.removeItem('refreshToken');
            window.location.href = '/signin?status=signout_success';
        });
    }

    // --- Initial Calls for Header ---
    fetchHeaderUserData();
    fetchAndUpdateUnreadCount();
}

// Ensure the header logic runs after the DOM is loaded.
document.addEventListener('DOMContentLoaded', initializeSharedHeader);