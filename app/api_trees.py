from flask import Blueprint, request, session, jsonify
import uuid

from .utils import (
    login_required,
    no_cache,
    get_tree_and_user_permissions,
    csrf_protect_api,
)
from . import supabase, STORAGE_BUCKET_NAME

bp = Blueprint("api_trees", __name__, template_folder="templates")


@bp.route("/api/trees", methods=["POST"])
@login_required
@csrf_protect_api
def create_tree():
    """Creates a new family tree for the logged-in user."""
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "Tree name is required", "success": False}), 400

    user_id = session.get("user_id")
    new_tree_data = {
        "name": data["name"],
        "owner_id": str(user_id),
        "is_public": data.get("is_public", False),
    }
    try:
        result = supabase.table("trees").insert(new_tree_data).execute()
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Tree created successfully",
                    "tree": result.data[0],
                }
            ),
            201,
        )
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500


@bp.route("/api/tree/<uuid:tree_id>", methods=["DELETE"])
@login_required
@csrf_protect_api
def delete_tree(tree_id: uuid.UUID):
    """Deletes a tree and all its data (persons, files). Only the owner can do this."""
    user_id = session.get("user_id")
    tree_id_str = str(tree_id)

    # 1. Check if the tree exists and the user is the owner
    try:
        response = (
            supabase.table("trees")
            .select("owner_id")
            .eq("id", tree_id_str)
            .single()
            .execute()
        )
        tree_data = response.data
        if tree_data.get("owner_id") != user_id:
            return (
                jsonify(
                    {
                        "error": "Permission denied. Only the owner can delete this tree.",
                        "success": False,
                    }
                ),
                403,
            )
    except Exception:
        return jsonify({"error": "Tree not found", "success": False}), 404

    try:
        # 2. Delete associated persons
        supabase.table("persons").delete().eq("tree_id", tree_id_str).execute()

        # 3. Delete files from storage
        # List all files in the tree's folder
        files_in_storage = supabase.storage.from_(STORAGE_BUCKET_NAME).list(
            path=tree_id_str, options={"limit": 1000}
        )
        if files_in_storage:
            # Create the list of full file paths to remove
            file_paths_to_remove = [
                f"{tree_id_str}/{file['name']}" for file in files_in_storage
            ]
            if file_paths_to_remove:
                supabase.storage.from_(STORAGE_BUCKET_NAME).remove(file_paths_to_remove)

        # 4. Delete the tree itself
        supabase.table("trees").delete().eq("id", tree_id_str).execute()

        return jsonify({"success": True, "message": "Tree successfully deleted."}), 200

    except Exception as e:
        # In case of error, deletion might be partial.
        return (
            jsonify(
                {
                    "error": f"An error occurred while deleting the tree: {e}",
                    "success": False,
                }
            ),
            500,
        )


@bp.route("/api/tree/<uuid:tree_id>", methods=["GET"])
@no_cache
@csrf_protect_api
def get_family_tree_info(tree_id: uuid.UUID):
    """Retrieves tree information if it is public or the user is authorized."""
    user_id = session.get("user_id")

    permissions = get_tree_and_user_permissions(tree_id, user_id)
    if not permissions:
        return (
            jsonify({"exist": False, "success": False, "error": "Tree not found"}),
            404,
        )

    if not permissions["can_view"]:
        return (
            jsonify(
                {"error": "Access denied. This tree is private.", "success": False}
            ),
            403,
        )

    tree_data = permissions["tree"]
    return jsonify(
        {
            "exist": True,
            "success": True,
            "editable": permissions["can_edit"],
            "file": tree_data["allow_file_uploads"]
            and not (tree_data["is_demo"] and not permissions["can_edit"]),
            "demo": tree_data["is_demo"],
            "error": "",
        }
    )
