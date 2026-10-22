(function () {
  "use strict";

  var tabs = {
    login: document.getElementById("tab-login"),
    signup: document.getElementById("tab-signup"),
  };
  var panels = {
    login: document.getElementById("panel-login"),
    signup: document.getElementById("panel-signup"),
  };

  function selectTab(name, moveFocus) {
    Object.keys(tabs).forEach(function (key) {
      var active = key === name;
      tabs[key].setAttribute("aria-selected", active ? "true" : "false");
      tabs[key].tabIndex = active ? 0 : -1;
      panels[key].hidden = !active;
    });
    if (moveFocus) {
      tabs[name].focus();
    }
  }

  tabs.login.addEventListener("click", function () {
    selectTab("login");
  });
  tabs.signup.addEventListener("click", function () {
    selectTab("signup");
  });

  /* Arrow keys switch tabs, as expected for a tab list. */
  [tabs.login, tabs.signup].forEach(function (tab) {
    tab.addEventListener("keydown", function (event) {
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        selectTab(tab === tabs.login ? "signup" : "login", true);
      }
    });
  });

  var params = new URLSearchParams(window.location.search);
  if (params.get("tab") === "signup") {
    selectTab("signup");
  }

  /* Show / hide password */
  document.querySelectorAll(".pw-toggle").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.getElementById(button.dataset.toggle);
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? "Hide" : "Show";
      button.setAttribute("aria-pressed", show ? "true" : "false");
    });
  });

  function showError(box, message, field) {
    box.textContent = message;
    box.hidden = false;
    if (field) {
      field.setAttribute("aria-invalid", "true");
      field.focus();
    }
  }

  function clearErrors(form, box) {
    box.hidden = true;
    box.textContent = "";
    form.querySelectorAll("[aria-invalid]").forEach(function (el) {
      el.removeAttribute("aria-invalid");
    });
  }

  function setSubmitting(button, busy) {
    button.disabled = busy;
    Ink.setBusy(button, busy);
  }

  /* Hide an old error as soon as the person starts correcting the form. */
  [["login-form", "login-error"], ["signup-form", "signup-error"]].forEach(function (pair) {
    var form = document.getElementById(pair[0]);
    var box = document.getElementById(pair[1]);
    ["input", "change"].forEach(function (type) {
      form.addEventListener(type, function () {
        clearErrors(form, box);
      });
    });
  });

  /* ---------------------------------------------------------- log in */
  var loginForm = document.getElementById("login-form");
  var loginError = document.getElementById("login-error");
  var loginSubmit = document.getElementById("login-submit");

  loginForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    clearErrors(loginForm, loginError);

    var usernameField = document.getElementById("login-username");
    var passwordField = document.getElementById("login-password");
    var username = usernameField.value.trim();
    var password = passwordField.value;

    if (!username) {
      showError(loginError, "Enter your username.", usernameField);
      return;
    }
    if (!password) {
      showError(loginError, "Enter your password.", passwordField);
      return;
    }

    setSubmitting(loginSubmit, true);
    try {
      await Ink.postJSON("/api/auth/login", { username: username, password: password });
      window.location.href = "/app";
    } catch (error) {
      showError(loginError, error.message);
      setSubmitting(loginSubmit, false);
    }
  });

  /* --------------------------------------------------------- sign up */
  var signupForm = document.getElementById("signup-form");
  var signupError = document.getElementById("signup-error");
  var signupSubmit = document.getElementById("signup-submit");

  signupForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    clearErrors(signupForm, signupError);

    var nameField = document.getElementById("signup-name");
    var emailField = document.getElementById("signup-email");
    var usernameField = document.getElementById("signup-username");
    var passwordField = document.getElementById("signup-password");
    var termsField = document.getElementById("signup-terms");

    var name = nameField.value.trim();
    var email = emailField.value.trim();
    var username = usernameField.value.trim();
    var password = passwordField.value;

    if (!name) {
      showError(signupError, "Enter your full name.", nameField);
      return;
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      showError(signupError, "Enter a valid email address.", emailField);
      return;
    }
    if (!/^[A-Za-z0-9_.-]{3,32}$/.test(username)) {
      showError(
        signupError,
        "Username must be 3 to 32 characters: letters, numbers, dot, dash or underscore.",
        usernameField
      );
      return;
    }
    if (password.length < 8) {
      showError(signupError, "Password must be at least 8 characters.", passwordField);
      return;
    }
    if (!termsField.checked) {
      showError(signupError, "Accept the Terms and Conditions to create an account.", termsField);
      return;
    }

    setSubmitting(signupSubmit, true);
    try {
      await Ink.postJSON("/api/auth/signup", {
        name: name,
        email: email,
        username: username,
        password: password,
        accept_terms: true,
      });
      window.location.href = "/app";
    } catch (error) {
      showError(signupError, error.message);
      setSubmitting(signupSubmit, false);
    }
  });
})();
