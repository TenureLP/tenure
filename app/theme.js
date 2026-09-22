/* Which look the page wears: Paper or Night.

   Loaded in the head, before the stylesheet has anything to paint, so the page never flashes the
   other look first. A reader who has chosen is remembered in this browser only; one who has not
   follows their system, and keeps following it if it changes while the page is open. Storage can
   be missing or refuse (a private window, blocked site data), and then the choice simply lasts as
   long as the page does. */

(function () {
  "use strict";

  var KEY = "tenure.look";
  var root = document.documentElement;
  var dark = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function chosen() {
    try {
      var v = localStorage.getItem(KEY);
      return v === "paper" || v === "night" ? v : null;
    } catch (e) {
      return null;
    }
  }

  function remember(look) {
    try { localStorage.setItem(KEY, look); } catch (e) { /* this page only, then */ }
  }

  function system() { return dark && dark.matches ? "night" : "paper"; }

  function wear(look) {
    root.setAttribute("data-theme", look);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", look === "night" ? "#09101D" : "#EFE9DD");
    var button = document.getElementById("theme");
    if (button) {
      var other = look === "night" ? "paper" : "night";
      button.setAttribute("aria-label", "Switch to the " + other + " look");
      button.title = "Switch to the " + other + " look";
    }
  }

  wear(chosen() || system());

  if (dark && dark.addEventListener) {
    dark.addEventListener("change", function () { if (!chosen()) wear(system()); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var button = document.getElementById("theme");
    if (!button) return;
    wear(root.getAttribute("data-theme"));
    button.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "night" ? "paper" : "night";
      remember(next);
      wear(next);
    });
  });
})();
