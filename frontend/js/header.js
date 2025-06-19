// /frontend/js/header.js
// version 1.2 (Final)
// Handles shared header logic and initializes real-time SSE connection.

console.log("--- header.js SCRIPT STARTED (v1.2) ---");

function initializeSharedHeader() {
    const accessToken = localStorage.getItem('accessToken');
    if (!accessToken) {
        return;
    }

    // --- Real-time connection via Server-Sent Events ---
    function connectToSSE() {
        const token = localStorage.getItem('accessToken');
        if (!token) return;

        // Note: The /api/sse/notifications endpoint needs to be created on the backend.
        // It should use sse_manager.py and validate the token from the query parameter.
        const sse = new EventSource(`/api/sse/notifications?token=${token}`);

        sse.onopen = () => {
            console.log("SSE connection established successfully.");
        };

        // Listen for the 'unread_update' event from the server
        sse.addEventListener('unread_update', (event) => {
            try {
                const eventData = JSON.parse(event.data);
                console.log("Received unread_update event from server:", eventData);
                const count = eventData.unread_count || 0;

                // Call the global UI update function from utils.js
                updateUnreadCountUI(count);

            } catch (e) {
                console.error("Error parsing SSE data:", e);
            }
        });

        sse.onerror = (error) => {
            console.error("SSE connection error:", error);
            // The browser will automatically try to reconnect.
            // We can close the connection here if the error persists.
            sse.close();
        };
    }

    // --- DOM Elements from Header ---
    const headerUserIdentifier = document.getElementById('headerUserIdentifier');
    const logoutButton = document.getElementById('logoutButton');
    // Note: The 'inAppUnreadCountSpanHeader' element is now handled by the global updateUnreadCountUI function.

    // --- Functions for Header ---
    async function fetchHeaderUserData() {
        if (!headerUserIdentifier) return;
        try {
            // Using the global fetchWithAuth from utils.js
            const response = await fetchWithAuth('/api/users/me');

            if (response.ok) {
                const userData = await response.json();
                headerUserIdentifier.textContent = userData.user_name || userData.email;

                const navItemUpload = document.getElementById('nav-item-upload');
                if (navItemUpload) {
                    if (userData.membership_type === 'premium') {
                        navItemUpload.style.display = 'block';
                    } else {
                        navItemUpload.style.display = 'none';
                    }
                }
            } else {
                headerUserIdentifier.textContent = "User";
                console.error("Header: Failed to fetch user data", response.status);
                const navItemUpload = document.getElementById('nav-item-upload');
                if(navItemUpload) navItemUpload.style.display = 'none';
            }
        } catch (error) {
            headerUserIdentifier.textContent = "User";
            console.error("Header: Network error fetching user data", error);
            const navItemUpload = document.getElementById('nav-item-upload');
            if(navItemUpload) navItemUpload.style.display = 'none';
        }
    }

    // --- Event Listeners for Header ---
    if (logoutButton) {
        logoutButton.addEventListener('click', async (e) => {
            e.preventDefault();
            try {
                await fetchWithAuth('/api/auth/signout', { method: 'POST' });
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
    fetchAndUpdateUnreadCount(); // Uses the global function from utils.js
    connectToSSE();
}

// Ensure the header logic runs after the DOM is loaded.
document.addEventListener('DOMContentLoaded', initializeSharedHeader);