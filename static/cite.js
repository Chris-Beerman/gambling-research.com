// The copy button on a page's suggested citation. Progressive: the citation is
// selectable text with or without this, and the button only appears to work when
// the clipboard is actually available.
(function () {
  "use strict";
  var buttons = document.querySelectorAll(".cite-copy[data-copy]");
  if (!buttons.length) return;
  if (!navigator.clipboard || !navigator.clipboard.writeText) {
    buttons.forEach(function (b) { b.hidden = true; });
    return;
  }
  buttons.forEach(function (button) {
    var target = document.getElementById(button.getAttribute("data-copy"));
    if (!target) { button.hidden = true; return; }
    var label = button.textContent;
    var timer = null;
    button.addEventListener("click", function () {
      navigator.clipboard.writeText(target.textContent.trim()).then(function () {
        button.textContent = button.getAttribute("data-done") || "Copied";
        button.classList.add("is-done");
        clearTimeout(timer);
        timer = setTimeout(function () {
          button.textContent = label;
          button.classList.remove("is-done");
        }, 2500);
      }, function () {
        button.textContent = "Press ⌘C or Ctrl+C";
        var range = document.createRange();
        range.selectNodeContents(target);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      });
    });
  });
})();
