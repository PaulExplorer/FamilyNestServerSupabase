let currentTreeId = null;

// Modal utilities
function showModal(modalId) {
  document.getElementById(modalId).classList.add("active");
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove("active");
}

function showConfirm(title, message, onConfirm) {
  document.getElementById("confirmModalTitle").textContent = title;
  document.getElementById("confirmModalBody").textContent = message;
  document.getElementById("confirmModalBtn").onclick = () => {
    closeModal("confirmModal");
    onConfirm();
  };
  showModal("confirmModal");
}

function showAlert(title, message) {
  document.getElementById("alertModalTitle").textContent = title;
  document.getElementById("alertModalBody").textContent = message;
  showModal("alertModal");
}

function showSuccess(title, message) {
  document.getElementById("successModalTitle").textContent = title;
  document.getElementById("successModalBody").textContent = message;
  showModal("successModal");
}

function showPrompt(title, message, defaultValue, onConfirm) {
  document.getElementById("promptModalTitle").textContent = title;
  document.getElementById("promptModalBody").textContent = message;
  const input = document.getElementById("promptModalInput");
  input.value = defaultValue || "";
  input.focus();

  const btn = document.getElementById("promptModalBtn");
  btn.onclick = () => {
    const value = input.value;
    closeModal("promptModal");
    onConfirm(value);
  };

  input.onkeypress = (e) => {
    if (e.key === "Enter") {
      btn.click();
    }
  };

  showModal("promptModal");
}

let currentLink = "";
function showLinkModal(link) {
  currentLink = link;
  document.getElementById("linkModalContent").textContent = link;
  showModal("linkModal");
}

function copyLinkAndClose() {
  navigator.clipboard
    .writeText(currentLink)
    .then(() => {
      closeModal("linkModal");
      showSuccess(
        translate("HOME_PAGE.LINK_MODAL.COPY_SUCCESS.SHORT"),
        translate("HOME_PAGE.LINK_MODAL.COPY_SUCCESS.LONG")
      );
    })
    .catch(() => {
      showAlert(
        translate("HOME_PAGE.LINK_MODAL.COPY_ERROR.SHORT"),
        translate("HOME_PAGE.LINK_MODAL.COPY_ERROR.LONG")
      );
    });
}

// Close modals when clicking overlay
document.querySelectorAll(".modal-overlay").forEach((overlay) => {
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      closeModal(overlay.id);
    }
  });
});

// Create tree form
document
  .getElementById("new-tree-form")
  .addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("tree-name").value;
    const is_public = document.getElementById("tree-public").checked;
    const statusDiv = document.getElementById("status");

    const response = await fetch("/api/trees", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf_token,
      },
      body: JSON.stringify({ name, is_public }),
    });

    const data = await response.json();

    if (data.success) {
      statusDiv.style.color = "var(--success-color)";
      statusDiv.textContent = translate("HOME_PAGE.CREATE_MODAL.CREATED", {
        id: data.tree.id,
      });
      setTimeout(() => window.location.reload(), 2000);
    } else {
      statusDiv.style.color = "var(--danger-color)";
      statusDiv.textContent = `Erreur : ${data.error}`;
    }
  });

// Delete tree
function deleteTree(button) {
  const treeId = button.dataset.treeId;
  const treeName = button.dataset.treeName;

  showConfirm(
    translate("HOME_PAGE.DELETE_MODAL.DELETE_TREE.SHORT"),
    translate("HOME_PAGE.DELETE_MODAL.DELETE_TREE.LONG", {
      treeName: treeName,
    }),
    async () => {
      const response = await fetch(`/api/tree/${treeId}`, {
        method: "DELETE",
        headers: {
          "X-CSRFToken": csrf_token,
        },
      });

      if (response.ok) {
        showSuccess(
          translate("HOME_PAGE.DELETE_MODAL.DELETE_SUCESS.SHORT"),
          translate("HOME_PAGE.DELETE_MODAL.DELETE_SUCESS.LONG")
        );
        setTimeout(() => window.location.reload(), 1500);
      } else {
        const data = await response.json();
        showAlert(
          translate("HOME_PAGE.DELETE_MODAL.DELETE_ERROR.SHORT"),
          translate("HOME_PAGE.DELETE_MODAL.DELETE_ERROR.LONG", {
            error: data.error || response.statusText,
          })
        );
      }
    }
  );
}

// Share modal
function openShareModal(treeId, editors, viewers, invitations) {
  currentTreeId = treeId;
  const shareList = document.getElementById("shareList");
  const invitationsList = document.getElementById("invitationsList");
  shareList.innerHTML = "";

  editors.forEach((editor) => {
    const li = document.createElement("li");
    li.dataset.userId = editor.id;
    li.innerHTML = `
            <div class="user-info">
              <span>${editor.email}</span>
              <span class="user-role">${translate(
                "HOME_PAGE.SHARE_MODAL.EDITOR"
              )}</span>
            </div>
            <div class="user-actions">
              <button class="action-btn change-role-btn" onclick="handleChangeRole('${
                editor.id
              }', 'viewer')">
                ${translate("HOME_PAGE.SHARE_MODAL.SET_VIEWER")}
              </button>
              <button class="action-btn revoke-btn" onclick="handleRevoke('${
                editor.id
              }')">
                ${translate("HOME_PAGE.SHARE_MODAL.REVOKE")}
              </button>
            </div>
          `;
    shareList.appendChild(li);
  });

  viewers.forEach((viewer) => {
    const li = document.createElement("li");
    li.dataset.userId = viewer.id;
    li.innerHTML = `
            <div class="user-info">
              <span>${viewer.email}</span>
              <span class="user-role">${translate(
                "HOME_PAGE.SHARE_MODAL.VIEWER"
              )}</span>
            </div>
            <div class="user-actions">
              <button class="action-btn change-role-btn" onclick="handleChangeRole('${
                viewer.id
              }', 'editor')">
                ${translate("HOME_PAGE.SHARE_MODAL.SET_EDITOR")}
              </button>
              <button class="action-btn revoke-btn" onclick="handleRevoke('${
                viewer.id
              }')">
                ${translate("HOME_PAGE.SHARE_MODAL.REVOKE")}
              </button>
            </div>
          `;
    shareList.appendChild(li);
  });

  if (editors.length === 0 && viewers.length === 0) {
    shareList.innerHTML = `<li style="color: var(--text-secondary); font-style: italic;">${translate(
      "HOME_PAGE.SHARE_MODAL.NO_USERS"
    )}</li>`;
  }

  invitationsList.innerHTML = "";
  if (invitations && invitations.length > 0) {
    invitations.forEach((inv) => {
      const li = document.createElement("li");
      li.dataset.tokenId = inv.token;
      const usageText =
        inv.usage_limit === null
          ? "illimité"
          : `${inv.used_count} / ${inv.usage_limit}`;
      li.innerHTML = `
              <div class="user-info">
                <span><span>${translate(
                  "HOME_PAGE.SHARE_MODAL.LINK"
                )}</span> <span class="user-role">(${inv.role})</span></span>
                <span style="font-size: 0.8em; color: var(--text-secondary)">${translate(
                  "HOME_PAGE.SHARE_MODAL.USAGE",
                  { usage: usageText }
                )}</span>
              </div>
              <div class="user-actions">
                <button class="action-btn revoke-btn" onclick="handleRevokeLink('${
                  inv.token
                }')">
                  ${translate("HOME_PAGE.SHARE_MODAL.REVOKE")}
                </button>
              </div>
            `;
      invitationsList.appendChild(li);
    });
  } else {
    invitationsList.innerHTML = `<li style="color: var(--text-secondary); font-style: italic;">${translate(
      "HOME_PAGE.SHARE_MODAL.NO_INVITATIONS"
    )}</li>`;
  }

  showModal("shareModal");
}

async function handleApiAction(url, method, body, statusElement) {
  try {
    const response = await fetch(url, {
      method: method,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf_token,
      },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (response.ok) {
      statusElement.style.color = "var(--success-color)";
      statusElement.textContent =
        data.message || translate("HOME_PAGE.API_MESSAGES.SUCCESS");
      setTimeout(() => window.location.reload(), 1500);
    } else {
      statusElement.style.color = "var(--danger-color)";
      statusElement.textContent = translate("HOME_PAGE.API_MESSAGES.ERROR", {
        error: data.error || translate("HOME_PAGE.API_MESSAGES.ERROR_OCCURED"),
      });
    }
  } catch (error) {
    statusElement.style.color = "var(--danger-color)";
    statusElement.textContent = translate(
      "HOME_PAGE.API_MESSAGES.NETWORK_ERROR",
      {
        error: error.message,
      }
    );
  }
}

function handleShare(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const email = form.querySelector('input[name="email"]').value;
  const role = form.querySelector('select[name="role"]').value;
  const statusElement = document.getElementById("shareStatus");

  handleApiAction(
    `/api/tree/${currentTreeId}/share`,
    "POST",
    { email, role },
    statusElement
  );
}

function handleChangeRole(userId, newRole) {
  const statusElement = document.getElementById("shareStatus");

  showConfirm(
    translate("HOME_PAGE.SHARE_MODAL.CHANGE_ROLE.SHORT"),
    translate("HOME_PAGE.SHARE_MODAL.CHANGE_ROLE.LONG", {
      newRole: newRole,
    }),
    () => {
      handleApiAction(
        `/api/tree/${currentTreeId}/permission`,
        "POST",
        { user_id_to_change: userId, new_role: newRole },
        statusElement
      );
    }
  );
}

function handleRevoke(userId) {
  const statusElement = document.getElementById("shareStatus");

  showConfirm(
    translate("HOME_PAGE.SHARE_MODAL.REVOKE_ACCESS.SHORT"),
    translate("HOME_PAGE.SHARE_MODAL.REVOKE_ACCESS.LONG"),
    () => {
      handleApiAction(
        `/api/tree/${currentTreeId}/revoke`,
        "POST",
        { user_id_to_revoke: userId },
        statusElement
      );
    }
  );
}

function handleRevokeLink(token) {
  const statusElement = document.getElementById("shareStatus");

  showConfirm(
    translate("HOME_PAGE.SHARE_MODAL.REVOKE_LINK.SHORT"),
    translate("HOME_PAGE.SHARE_MODAL.REVOKE_LINK.LONG"),
    () => {
      handleApiAction(
        `/api/tree/${currentTreeId}/invitation/${token}`,
        "DELETE",
        {},
        statusElement
      );
    }
  );
}

function generateInviteLinkFromModal(role) {
  showPrompt(
    translate("HOME_PAGE.SHARE_MODAL.LIMIT_USER.SHORT"),
    translate("HOME_PAGE.SHARE_MODAL.LIMIT_USER.LONG"),
    "",
    async (limitInput) => {
      if (limitInput === null) return;

      const limit = limitInput === "" ? null : parseInt(limitInput, 10);

      if (limitInput !== "" && (isNaN(limit) || limit <= 0)) {
        showAlert(
          translate("HOME_PAGE.SHARE_MODAL.LIMIT_USER.ERROR"),
          translate("HOME_PAGE.SHARE_MODAL.LIMIT_USER.INVALID_NUMBER")
        );
        return;
      }

      try {
        const response = await fetch(`/api/tree/${currentTreeId}/invitation`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf_token,
          },
          body: JSON.stringify({ role: role, limit: limit }),
        });
        const result = await response.json();
        if (result.success) {
          showLinkModal(result.link);
        } else {
          showAlert(
            translate("HOME_PAGE.SHARE_MODAL.CREATE_LINK.ERROR"),
            result.error
          );
        }
      } catch (error) {
        console.error("Error while generating link :", error);
        showAlert(
          translate("HOME_PAGE.SHARE_MODAL.CREATE_LINK.ERROR"),
          translate("HOME_PAGE.SHARE_MODAL.CREATE_LINK.ERROR_GEN_LINK")
        );
      }
    }
  );
}

document.addEventListener("DOMContentLoaded", () => {
  initTranslations("fr");
});
