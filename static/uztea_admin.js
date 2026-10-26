(function () {
    "use strict";

    var storageKey = "uztea-admin-theme";

    function applyTheme(theme) {
        var dark = theme === "dark";
        document.body.classList.toggle("dark-mode", dark);
        var button = document.querySelector(".uztea-theme-toggle");
        if (button) {
            button.innerHTML = dark
                ? '<i class="fas fa-sun" aria-hidden="true"></i>'
                : '<i class="fas fa-moon" aria-hidden="true"></i>';
            button.setAttribute("aria-label", dark ? "Light mode" : "Dark mode");
            button.setAttribute("title", dark ? "Light mode" : "Dark mode");
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        var savedTheme = localStorage.getItem(storageKey) || "light";
        var userMenu = document.querySelector(".main-header .navbar-nav.ml-auto");
        if (userMenu && !document.querySelector(".uztea-theme-toggle")) {
            var item = document.createElement("li");
            item.className = "nav-item";
            item.innerHTML = '<button type="button" class="uztea-theme-toggle"></button>';
            userMenu.insertBefore(item, userMenu.firstChild);
        }
        applyTheme(savedTheme);

        var toggle = document.querySelector(".uztea-theme-toggle");
        if (toggle) {
            toggle.addEventListener("click", function () {
                var nextTheme = document.body.classList.contains("dark-mode") ? "light" : "dark";
                localStorage.setItem(storageKey, nextTheme);
                applyTheme(nextTheme);
            });
        }
    });
}());
