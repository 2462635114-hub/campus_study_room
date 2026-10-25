/* 全局交互脚本：移动端导航、提示关闭、危险操作确认、管理端侧边栏。
   纯原生 JavaScript，无外部依赖。 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    setupNavToggle();
    setupAlertDismiss();
    setupConfirmActions();
    setupSidebar();
    setupFormSubmitState();
  });

  /** 顶部导航：移动端展开/收起。 */
  function setupNavToggle() {
    var toggle = document.querySelector("[data-nav-toggle]");
    var nav = document.getElementById("mainNav");
    if (!toggle || !nav) {
      return;
    }
    toggle.addEventListener("click", function () {
      var isOpen = nav.classList.toggle("nav--open");
      toggle.setAttribute("aria-expanded", String(isOpen));
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.classList.contains("nav--open")) {
        nav.classList.remove("nav--open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });
  }

  /** 提示条：手动关闭 + 成功/信息提示自动淡出。 */
  function setupAlertDismiss() {
    var alerts = document.querySelectorAll("[data-dismiss-alert]");
    Array.prototype.forEach.call(alerts, function (button) {
      button.addEventListener("click", function () {
        var alert = button.closest(".alert");
        if (alert && alert.parentNode) {
          alert.parentNode.removeChild(alert);
        }
      });
    });
    Array.prototype.forEach.call(
      document.querySelectorAll(".alert--success[data-auto-dismiss], .alert--info[data-auto-dismiss]"),
      function (alert) {
        window.setTimeout(function () {
          if (alert && alert.parentNode) {
            alert.parentNode.removeChild(alert);
          }
        }, 9000);
      }
    );
  }

  /** 危险操作二次确认：form[data-confirm]、a[data-confirm]、button[data-confirm]。 */
  function setupConfirmActions() {
    document.addEventListener("submit", function (event) {
      var form = event.target;
      if (!form || !form.matches || !form.matches("form[data-confirm]")) {
        return;
      }
      if (form.getAttribute("data-confirmed") === "true") {
        return;
      }
      var message = form.getAttribute("data-confirm") || "确定执行该操作吗？";
      if (!window.confirm(message)) {
        event.preventDefault();
        return;
      }
      form.setAttribute("data-confirmed", "true");
    });
    document.addEventListener("click", function (event) {
      var target = event.target.closest ? event.target.closest("a[data-confirm]") : null;
      if (!target) {
        return;
      }
      var message = target.getAttribute("data-confirm") || "确定执行该操作吗？";
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  }

  /** 管理端移动端侧边栏。 */
  function setupSidebar() {
    var sidebar = document.querySelector(".sidebar");
    var backdrop = document.querySelector(".sidebar-backdrop");
    var toggles = document.querySelectorAll("[data-sidebar-toggle]");
    if (!sidebar || !toggles.length) {
      return;
    }
    function openSidebar() {
      sidebar.classList.add("sidebar--open");
      if (backdrop) {
        backdrop.classList.add("is-visible");
      }
      Array.prototype.forEach.call(toggles, function (button) {
        button.setAttribute("aria-expanded", "true");
      });
    }
    function closeSidebar() {
      sidebar.classList.remove("sidebar--open");
      if (backdrop) {
        backdrop.classList.remove("is-visible");
      }
      Array.prototype.forEach.call(toggles, function (button) {
        button.setAttribute("aria-expanded", "false");
      });
    }
    Array.prototype.forEach.call(toggles, function (button) {
      button.addEventListener("click", function () {
        if (sidebar.classList.contains("sidebar--open")) {
          closeSidebar();
        } else {
          openSidebar();
        }
      });
    });
    if (backdrop) {
      backdrop.addEventListener("click", closeSidebar);
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeSidebar();
      }
    });
  }

  /** 提交按钮防重复点击（提交后禁用并显示处理中）。 */
  function setupFormSubmitState() {
    document.addEventListener("submit", function (event) {
      var form = event.target;
      if (!form || !form.matches || !form.matches("form.js-submit-once")) {
        return;
      }
      if (form.getAttribute("data-submitting") === "true") {
        event.preventDefault();
        return;
      }
      form.setAttribute("data-submitting", "true");
      var button = form.querySelector("button[type='submit']");
      if (button) {
        window.setTimeout(function () {
          button.disabled = true;
          button.textContent = button.getAttribute("data-loading-text") || "处理中…";
        }, 0);
      }
    });
  }
})();
