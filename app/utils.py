import uuid
from flask import jsonify, request, session, redirect, url_for, make_response
from functools import wraps
from datetime import datetime, timezone

from . import supabase, csrf


def login_required(f):
    """
    Checks if a user is in the session.
    For pages, redirects to login. For APIs, returns a 401 error.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            # If the request is for an API, return JSON
            if request.path.startswith("/api/"):
                return (
                    jsonify({"error": "Authentication required", "success": False}),
                    401,
                )
            # Otherwise, redirect to login page
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated_function


def csrf_protect_api(f):
    """
    Decorator to protect API routes with CSRF.
    It should be used on API routes that modify data (POST, PUT, DELETE).
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            csrf.protect()
        except Exception as e:
            return (
                jsonify({"error": "CSRF token missing or incorrect", "success": False}),
                403,
            )
        return f(*args, **kwargs)

    return decorated_function


def process_invitation(token_str: str, user_id_str: str) -> str | None:
    """
    Validates a token, adds a user to a tree, and records the usage.
    Handles multi-use invitations.
    Returns the tree ID if successful, otherwise None.
    """
    try:
        invitation_resp = (
            supabase.table("tree_invitations")
            .select("*")
            .eq("token", token_str)
            .single()
            .execute()
        )
        invitation = invitation_resp.data
        if not invitation:
            return None

        expires_at = datetime.fromisoformat(invitation["expires_at"])
        if expires_at < datetime.now(timezone.utc):
            return None

        used_by_users = invitation.get("used_by_users") or []
        usage_limit = invitation.get("usage_limit")

        if usage_limit is not None and len(used_by_users) >= usage_limit:
            return None

        if user_id_str in used_by_users:
            return invitation["tree_id"]

        tree_id = invitation["tree_id"]
        role = invitation["role"]

        tree_resp = (
            supabase.table("trees")
            .select("owner_id, editor_ids, viewer_ids")
            .eq("id", tree_id)
            .single()
            .execute()
        )
        tree = tree_resp.data

        is_already_member = (
            user_id_str == tree["owner_id"]
            or user_id_str in (tree.get("editor_ids") or [])
            or user_id_str in (tree.get("viewer_ids") or [])
        )
        if not is_already_member:
            if role == "editor":
                new_editors = (tree.get("editor_ids") or []) + [user_id_str]
                supabase.table("trees").update({"editor_ids": new_editors}).eq(
                    "id", tree_id
                ).execute()
            elif role == "viewer":
                new_viewers = (tree.get("viewer_ids") or []) + [user_id_str]
                supabase.table("trees").update({"viewer_ids": new_viewers}).eq(
                    "id", tree_id
                ).execute()

        updated_used_by_list = used_by_users + [user_id_str]
        supabase.table("tree_invitations").update(
            {"used_by_users": updated_used_by_list}
        ).eq("token", token_str).execute()

        return tree_id
    except Exception as e:
        print(f"Error processing invitation: {e}")
        return None


def get_tree_and_user_permissions(
    tree_id: uuid.UUID, user_id: uuid.UUID | None
) -> dict | None:
    """Retrieves a tree and calculates user permissions (including for anonymous users if public)."""
    try:
        response = (
            supabase.table("trees")
            .select("*")
            .eq("id", str(tree_id))
            .single()
            .execute()
        )
        tree_data = response.data

        can_view = tree_data.get("is_public", False)
        can_edit = False

        if user_id:
            user_uuid_str = str(user_id)
            is_owner = tree_data.get("owner_id") == user_uuid_str
            is_editor = user_uuid_str in (tree_data.get("editor_ids") or [])
            is_viewer = user_uuid_str in (tree_data.get("viewer_ids") or [])

            can_edit = is_owner or is_editor
            can_view = can_view or is_owner or is_editor or is_viewer

        return {"can_edit": can_edit, "can_view": can_view, "tree": tree_data}
    except Exception:
        return None


def no_cache(f):
    """Decorator to disable caching on responses."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = f(*args, **kwargs)
        resp_obj = make_response(response)
        resp_obj.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp_obj.headers["Pragma"] = "no-cache"
        resp_obj.headers["Expires"] = "0"
        return response

    return decorated_function
