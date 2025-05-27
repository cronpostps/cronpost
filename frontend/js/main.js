// Trong frontend/js/main.js

const body = document.body; // Khai báo body ở phạm vi toàn cục

function applyTheme(theme) {
    console.log("Applying theme:", theme);
    // Bây giờ applyTheme có thể thấy biến body toàn cục
    body.classList.remove('theme-dark', 'theme-light');
    body.classList.add(theme);
    localStorage.setItem('cronpostTheme', theme);
    console.log("Body class list after apply:", body.classList.toString());
    console.log("Theme saved to localStorage:", localStorage.getItem('cronpostTheme'));
}

// Định nghĩa hàm changeLanguage ở phạm vi toàn cục (nếu bạn đã có)
function changeLanguage(langCode, langDisplay) {
    // ...
}


$(document).ready(function(){
    // Kích hoạt tất cả các dropdown của Bootstrap trên trang
    $('[data-toggle="dropdown"]').dropdown();

    const themeSwitch = document.getElementById('theme-dropdown');
    // Không cần khai báo lại `const body = document.body;` ở đây nữa

    // Load saved theme or default
    const savedTheme = localStorage.getItem('cronpostTheme') || 'theme-dark';
    console.log("Initial saved theme:", savedTheme);
    applyTheme(savedTheme); // Gọi hàm applyTheme
    if (themeSwitch) {
        themeSwitch.value = savedTheme;
    }

    // Event listener for theme change
    if (themeSwitch) {
        themeSwitch.addEventListener('change', function() {
            console.log("Theme switched to via dropdown:", this.value);
            applyTheme(this.value); // Gọi hàm applyTheme
        });
    }

    // Set current year in footer
    const currentYearSpan = document.getElementById('current-year');
    if (currentYearSpan) {
        currentYearSpan.textContent = new Date().getFullYear();
    }
});