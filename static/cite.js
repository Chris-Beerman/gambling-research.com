/* Adds a copy button to the citation block. Progressive enhancement: without
   JS, or without clipboard permission, the citation is still there to select. */
(function () {
  "use strict";
  var line = document.querySelector("[data-cite]");
  if (!line || !navigator.clipboard) return;

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "cite-copy";
  btn.textContent = "Copy";
  btn.setAttribute("aria-label", "Copy the citation to the clipboard");

  var status = document.createElement("span");
  status.className = "cite-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");

  var timer;
  btn.addEventListener("click", function () {
    navigator.clipboard.writeText((line.textContent || "").trim()).then(
      function () {
        status.textContent = "Copied";
        btn.textContent = "Copied";
      },
      function () {
        status.textContent = "Press Ctrl+C or Cmd+C to copy";
      }
    );
    clearTimeout(timer);
    timer = setTimeout(function () {
      status.textContent = "";
      btn.textContent = "Copy";
    }, 4000);
  });

  var row = document.createElement("p");
  row.className = "cite-actions";
  row.appendChild(btn);
  row.appendChild(status);
  line.parentNode.insertBefore(row, line.nextSibling);
})();
