from flask import Blueprint, request, session, jsonify, url_for
from datetime import datetime, timezone, timedelta
import uuid

from .utils import login_required, csrf_protect_api
from . import supabase

bp = Blueprint("api_sharing", __name__, template_folder="templates")


@bp.route("/api/tree/<uuid:tree_id>/invitation", methods=["POST"])
@login_required
@csrf_protect_api
def create_invitation(tree_id: uuid.UUID):
    user_id = session.get("user_id")
    tree_id_str = str(tree_id)

    try:
        tree_resp = (
            supabase.table("trees")
            .select("owner_id")
            .eq("id", tree_id_str)
            .single()
            .execute()
        )
        if tree_resp.data.get("owner_id") != user_id:
            return (
                jsonify(
                    {
                        "error": "Only the owner can create invitations.",
                        "success": False,
                    }
                ),
                403,
            )
    except Exception:
        return jsonify({"error": "Tree not found.", "success": False}), 404

    data = request.get_json()
    role = data.get("role")
    limit = data.get("limit")
    if role not in ["editor", "viewer"]:
        return jsonify({"error": "Invalid role.", "success": False}), 400

    try:
        expires_at = datetime.now(timezone.utc) + timedelta(days=365)
        invitation_data = {
            "tree_id": tree_id_str,
            "role": role,
            "used_by_users": [],
            "expires_at": expires_at.isoformat(),
            "usage_limit": limit,
        }
        response = supabase.table("tree_invitations").insert(invitation_data).execute()
        new_token = response.data[0]["token"]
        invitation_link = url_for("auth.join_by_token", token=new_token, _external=True)
        return jsonify({"success": True, "link": invitation_link})
    except Exception as e:
        return jsonify({"error": f"Error during creation: {e}", "success": False}), 500


@bp.route("/api/tree/<uuid:tree_id>/invitation/<uuid:token>", methods=["DELETE"])
@login_required
@csrf_protect_api
def expire_invitation_link(tree_id: uuid.UUID, token: uuid.UUID):
    """Revokes an invitation link by setting its expiration date to now."""
    user_id = session.get("user_id")
    tree_id_str = str(tree_id)
    token_str = str(token)

    # 1. Check that the user is indeed the owner of the tree
    try:
        tree_resp = (
            supabase.table("trees")
            .select("owner_id")
            .eq("id", tree_id_str)
            .single()
            .execute()
        )
        if tree_resp.data.get("owner_id") != user_id:
            return (
                jsonify(
                    {
                        "error": "Only the owner can revoke an invitation link.",
                        "success": False,
                    }
                ),
                403,
            )
    except Exception:
        return jsonify({"error": "Tree not found.", "success": False}), 404

    # 2. Update the link to expire it
    try:
        update_response = (
            supabase.table("tree_invitations")
            .update({"expires_at": datetime.now(timezone.utc).isoformat()})
            .eq("token", token_str)
            .eq("tree_id", tree_id_str)
            .execute()
        )

        if not update_response.data:
            return (
                jsonify(
                    {
                        "error": "Invitation link not found or does not belong to this tree.",
                        "success": False,
                    }
                ),
                404,
            )

        return jsonify(
            {"success": True, "message": "Invitation link successfully revoked."}
        )
    except Exception as e:
        return (
            jsonify(
                {"error": f"Error during link revocation: {str(e)}", "success": False}
            ),
            500,
        )


@bp.route("/api/tree/<uuid:tree_id>/share", methods=["POST"])
@login_required
@csrf_protect_api
def share_tree(tree_id: uuid.UUID):
    """Shares a tree with another user by email."""
    owner_id = session.get("user_id")
    tree_id_str = str(tree_id)

    data = request.get_json()
    email_to_add = data.get("email")
    role = data.get("role")

    if not email_to_add or not role:
        return jsonify({"error": "Email and role are required.", "success": False}), 400
    if role not in ["editor", "viewer"]:
        return (
            jsonify(
                {
                    "error": "Invalid role. Must be 'editor' or 'viewer'.",
                    "success": False,
                }
            ),
            400,
        )

    # 1. Check if the tree exists and the user is the owner
    try:
        tree_response = (
            supabase.table("trees")
            .select("owner_id, editor_ids, viewer_ids")
            .eq("id", tree_id_str)
            .single()
            .execute()
        )
        tree_data = tree_response.data
        if tree_data.get("owner_id") != owner_id:
            return (
                jsonify(
                    {
                        "error": "Permission denied. Only the owner can share this tree.",
                        "success": False,
                    }
                ),
                403,
            )
    except Exception:
        return jsonify({"error": "Tree not found.", "success": False}), 404

    # 2. Check if the email of the user to add exists
    try:
        user_to_add_id: uuid.UUID = (
            supabase.rpc("get_user_id_by_email", {"email": email_to_add})
            .execute()
            .data[0]
            .get("id")
        )
    except Exception as e:
        print(e)
        return (
            jsonify(
                {
                    "error": f"User with email '{email_to_add}' was not found.",
                    "success": False,
                }
            ),
            404,
        )

    # 3. Update tree permissions
    editor_ids = tree_data.get("editor_ids") or []
    viewer_ids = tree_data.get("viewer_ids") or []

    if (
        user_to_add_id == owner_id
        or user_to_add_id in editor_ids
        or user_to_add_id in viewer_ids
    ):
        return (
            jsonify(
                {
                    "error": "This user already has access to this tree.",
                    "success": False,
                }
            ),
            409,
        )

    if role == "editor":
        editor_ids.append(user_to_add_id)
        supabase.table("trees").update({"editor_ids": editor_ids}).eq(
            "id", tree_id_str
        ).execute()
    elif role == "viewer":
        viewer_ids.append(user_to_add_id)
        supabase.table("trees").update({"viewer_ids": viewer_ids}).eq(
            "id", tree_id_str
        ).execute()

    return jsonify(
        {"success": True, "message": f"User '{email_to_add}' added as {role}."}
    )


@bp.route("/api/tree/<uuid:tree_id>/revoke", methods=["POST"])
@login_required
@csrf_protect_api
def revoke_tree_access(tree_id: uuid.UUID):
    """Revokes access of a user (editor or viewer) to a tree."""
    owner_id = session.get("user_id")
    tree_id_str = str(tree_id)

    data = request.get_json()
    user_id_to_revoke = data.get("user_id_to_revoke")

    if not user_id_to_revoke:
        return (
            jsonify(
                {"error": "The ID of the user to revoke is required.", "success": False}
            ),
            400,
        )

    # 1. Check if the tree exists and the current user is the owner
    try:
        tree_response = (
            supabase.table("trees")
            .select("owner_id, editor_ids, viewer_ids")
            .eq("id", tree_id_str)
            .single()
            .execute()
        )
        tree_data = tree_response.data
        if tree_data.get("owner_id") != owner_id:
            return (
                jsonify(
                    {
                        "error": "Permission denied. Only the owner can revoke access.",
                        "success": False,
                    }
                ),
                403,
            )
    except Exception:
        return jsonify({"error": "Tree not found.", "success": False}), 404

    if user_id_to_revoke == owner_id:
        return (
            jsonify(
                {"error": "The owner cannot revoke their own access.", "success": False}
            ),
            400,
        )

    # 2. Remove the user from the permission lists
    editor_ids = tree_data.get("editor_ids") or []
    viewer_ids = tree_data.get("viewer_ids") or []

    if user_id_to_revoke in editor_ids:
        editor_ids.remove(user_id_to_revoke)
        supabase.table("trees").update({"editor_ids": editor_ids}).eq(
            "id", tree_id_str
        ).execute()
    elif user_id_to_revoke in viewer_ids:
        viewer_ids.remove(user_id_to_revoke)
        supabase.table("trees").update({"viewer_ids": viewer_ids}).eq(
            "id", tree_id_str
        ).execute()
    else:
        return (
            jsonify(
                {
                    "error": "The specified user does not have access to this tree.",
                    "success": False,
                }
            ),
            404,
        )

    return jsonify({"success": True, "message": "User access successfully revoked."})


@bp.route("/api/tree/<uuid:tree_id>/permission", methods=["POST"])
@login_required
@csrf_protect_api
def change_tree_permission(tree_id: uuid.UUID):
    """Changes a user's permission from 'viewer' to 'editor' or vice-versa."""
    owner_id = session.get("user_id")
    tree_id_str = str(tree_id)

    data = request.get_json()
    user_id_to_change = data.get("user_id_to_change")
    new_role = data.get("new_role")

    if not user_id_to_change or not new_role:
        return (
            jsonify({"error": "User ID and new role are required.", "success": False}),
            400,
        )
    if new_role not in ["editor", "viewer"]:
        return (
            jsonify(
                {
                    "error": "Invalid role. Must be 'editor' or 'viewer'.",
                    "success": False,
                }
            ),
            400,
        )

    # 1. Check if the tree exists and the current user is the owner
    try:
        tree_response = (
            supabase.table("trees")
            .select("owner_id, editor_ids, viewer_ids")
            .eq("id", tree_id_str)
            .single()
            .execute()
        )
        tree_data = tree_response.data
        if tree_data.get("owner_id") != owner_id:
            return (
                jsonify(
                    {
                        "error": "Permission denied. Only the owner can modify permissions.",
                        "success": False,
                    }
                ),
                403,
            )
    except Exception:
        return jsonify({"error": "Tree not found.", "success": False}), 404

    if user_id_to_change == owner_id:
        return (
            jsonify(
                {"error": "The owner cannot change their own role.", "success": False}
            ),
            400,
        )

    # 2. Change the user's role
    editor_ids = tree_data.get("editor_ids") or []
    viewer_ids = tree_data.get("viewer_ids") or []

    if user_id_to_change not in editor_ids and user_id_to_change not in viewer_ids:
        return (
            jsonify(
                {
                    "error": "The specified user does not have access to this tree.",
                    "success": False,
                }
            ),
            404,
        )

    # Remove user from both lists to avoid duplicates
    if user_id_to_change in editor_ids:
        editor_ids.remove(user_id_to_change)
    if user_id_to_change in viewer_ids:
        viewer_ids.remove(user_id_to_change)

    if new_role == "editor":
        editor_ids.append(user_id_to_change)
    else:
        viewer_ids.append(user_id_to_change)

    supabase.table("trees").update(
        {"editor_ids": editor_ids, "viewer_ids": viewer_ids}
    ).eq("id", tree_id_str).execute()

    return jsonify({"success": True, "message": f"User role changed to '{new_role}'."})
