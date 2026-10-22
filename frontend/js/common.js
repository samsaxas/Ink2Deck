/* Shared helpers for every page. Exposes a single global: Ink. */
(function () {
  "use strict";

  var GENERIC_ERROR = "Something went wrong. Try again.";

  async function request(path, options) {
    var response;
    try {
      response = await fetch(path, Object.assign({ credentials: "same-origin" }, options));
    } catch (networkError) {
      var offline = new Error("Cannot reach the server. Check your connection and try again.");
      offline.status = 0;
      throw offline;
    }

    if (response.ok) {
      return response;
    }

    var message = GENERIC_ERROR;
    try {
      var data = await response.json();
      if (data && typeof data.detail === "string") {
        message = data.detail;
      }
    } catch (ignore) {
      /* body was not JSON */
    }
    var error = new Error(message);
    error.status = response.status;
    throw error;
  }

  async function postJSON(path, body) {
    var response = await request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return response.json();
  }

  function toast(message, isError) {
    var host = document.getElementById("toasts");
    if (!host) {
      return;
    }
    var node = document.createElement("div");
    node.className = "toast" + (isError ? " is-error" : "");
    node.textContent = message;
    host.appendChild(node);
    setTimeout(function () {
      node.remove();
    }, 4500);
  }

  function setBusy(button, busy) {
    button.classList.toggle("is-loading", busy);
    button.setAttribute("aria-busy", busy ? "true" : "false");
  }

  async function logout() {
    try {
      await postJSON("/api/auth/logout", {});
    } catch (ignore) {
      /* the cookie may already be gone; go home either way */
    }
    window.location.href = "/";
  }

  async function currentUser() {
    try {
      var response = await request("/api/auth/me");
      var data = await response.json();
      return data.authenticated ? data.user : null;
    } catch (ignore) {
      return null;
    }
  }

  /* On the landing page, swap the sign-up buttons for a link to the workspace. */
  async function adaptNavigation() {
    var starts = document.querySelectorAll("[data-start]");
    var logins = document.querySelectorAll("[data-login]");
    if (!starts.length) {
      return;
    }
    var user = await currentUser();
    if (!user) {
      return;
    }
    starts.forEach(function (link) {
      link.textContent = "Open workspace";
      link.setAttribute("href", "/app");
    });
    logins.forEach(function (link) {
      link.hidden = true;
    });
  }

  window.Ink = {
    request: request,
    postJSON: postJSON,
    toast: toast,
    setBusy: setBusy,
    logout: logout,
    currentUser: currentUser,
  };

  document.addEventListener("DOMContentLoaded", adaptNavigation);
})();
