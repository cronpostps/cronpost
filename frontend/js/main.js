// frontend/js/main.js
// Version: 1.1
// Mô tả: Logic điều khiển theme và các chức năng UI cơ bản cho Frontend CronPost.
// Duy trì logic hiện có, chỉ cập nhật phiên bản và thêm ghi chú.

const body = document.body;
// googleSignInImg được tìm kiếm ở đây nhưng có thể không tồn tại trên tất cả các trang
// (ví dụ: chỉ có trên signin/signup). Điều này đã được xử lý bằng cách kiểm tra if (googleSignInImg).
const googleSignInImg = document.getElementById('googleSignInImg');

/**
 * Áp dụng theme (dark/light) cho trang web.
 * Cập nhật class trên <body> và lưu lựa chọn vào Local Storage.
 * Thay đổi hình ảnh nút Google Sign-In nếu có.
 * @param {string} theme - Tên theme để áp dụng (ví dụ: 'theme-dark', 'theme-light').
 */
function applyTheme(theme) {
    console.log("Applying theme:", theme); // Ghi log để debug trong môi trường phát triển
    body.classList.remove('theme-dark', 'theme-light'); // Xóa các class theme cũ
    body.classList.add(theme); // Thêm class theme mới
    localStorage.setItem('cronpostTheme', theme); // Lưu lựa chọn theme vào Local Storage để duy trì giữa các phiên

    // Logic thay đổi hình ảnh nút Google Sign-In dựa trên theme.
    // Chỉ thực hiện nếu phần tử googleSignInImg tồn tại trên trang.
    if (googleSignInImg) { 
        if (theme === 'theme-dark') {
            googleSignInImg.src = 'img/gg_light_sq_ctn.svg'; // Sử dụng icon sáng cho nền tối
        } else {
            googleSignInImg.src = 'img/gg_dark_sq_ctn.svg'; // Sử dụng icon tối cho nền sáng
        }
        console.log("Google sign-in image src set to:", googleSignInImg.src); // Ghi log để debug
    }
    // else {
    //     console.log("Google sign-in image element not found on this page."); // Bỏ comment nếu muốn debug chi tiết hơn
    // }
    console.log("Body class list after apply:", body.classList.toString()); // Ghi log trạng thái class của <body>
}

// Sẽ bổ sung thêm logic đổi ngôn ngữ trong tương lai.
function changeLanguage(code, label) {
    console.log("Changing language to:", code);
    // Thêm logic đổi ngôn ngữ ở đây
    // Ví dụ: localStorage.setItem("language", code);
    // location.reload(); // nếu cần load lại trang
}

// Sử dụng sự kiện DOMContentLoaded của JavaScript thuần để đảm bảo DOM đã được tải hoàn chỉnh.
document.addEventListener('DOMContentLoaded', function() {
    console.log("--- main.js (vanilla) DOMContentLoaded fired ---");

    const themeSwitch = document.getElementById('theme-dropdown'); // Lấy phần tử dropdown chọn theme

    // Tải theme đã lưu từ Local Storage hoặc sử dụng 'theme-dark' làm mặc định.
    const savedTheme = localStorage.getItem('cronpostTheme') || 'theme-dark';
    console.log("Initial saved theme in main.js (vanilla):", savedTheme);
    applyTheme(savedTheme); // Áp dụng theme ngay khi tải trang
    if (themeSwitch) {
        themeSwitch.value = savedTheme; // Cập nhật giá trị của dropdown để khớp với theme đã tải
    }

    // Event listener cho sự kiện thay đổi lựa chọn theme từ dropdown.
    if (themeSwitch) {
        themeSwitch.addEventListener('change', function() {
            console.log("Theme switched to via dropdown in main.js (vanilla):", this.value);
            applyTheme(this.value); // Gọi hàm applyTheme với giá trị mới từ dropdown
        });
    }

    // Cập nhật năm hiện tại trong footer.
    const currentYearSpan = document.getElementById('current-year');
    if (currentYearSpan) {
        currentYearSpan.textContent = new Date().getFullYear(); // Lấy năm hiện tại và gán vào phần tử <span>
    }
    console.log("--- main.js (vanilla) DOMContentLoaded finished ---");
});