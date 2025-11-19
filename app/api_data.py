from flask import Blueprint, request, session, jsonify
import uuid, nh3

from .utils import (
    login_required,
    get_tree_and_user_permissions,
    no_cache,
    csrf_protect_api,
)
from . import supabase, STORAGE_BUCKET_NAME

bp = Blueprint("api_data", __name__, template_folder="templates")


@bp.route("/api/tree/<uuid:tree_id>/data", methods=["GET"])
@no_cache
@csrf_protect_api
def get_family_tree_data(tree_id: uuid.UUID):
    """Retrieves the person data for a tree if it is public or the user is authorized."""
    user_id = session.get("user_id")

    permissions = get_tree_and_user_permissions(tree_id, user_id)
    if not permissions:
        return jsonify({"error": "Tree not found", "success": False}), 404
    if not permissions["can_view"]:
        return (
            jsonify(
                {"error": "Access denied. This tree is private.", "success": False}
            ),
            403,
        )

    try:
        response = (
            supabase.table("persons")
            .select("data")
            .eq("tree_id", str(tree_id))
            .execute()
        )
        person_data = [item["data"] for item in response.data]
        return jsonify({"data": person_data, "success": True})
    except Exception as e:
        return jsonify({"error": f"Database error: {e}", "success": False}), 500


new_ids_dict = {}


@bp.route("/api/tree/<uuid:tree_id>/id/new", methods=["GET"])
@login_required
@no_cache
@csrf_protect_api
def get_new_id(tree_id: uuid.UUID):
    """Generates a new ID for a person. Requires edit permission."""
    user_id = session.get("user_id")
    permissions = get_tree_and_user_permissions(tree_id, user_id)
    if not permissions:
        return jsonify({"error": "Tree not found", "success": False}), 404
    if not permissions["can_edit"]:
        return jsonify({"error": "Edit permission denied", "success": False}), 403

    try:
        if new_ids_dict.get(tree_id):  # if two persons add a new person at same time
            new_id = new_ids_dict[tree_id] + 1
        else:
            response = (
                supabase.table("persons")
                .select("id")
                .eq("tree_id", str(tree_id))
                .order("id", desc=True)
                .limit(1)
                .execute()
            )
            new_id = (response.data[0]["id"] + 1) if response.data else 1

        new_ids_dict[tree_id] = new_id

        return jsonify({"id": new_id, "success": True})
    except Exception as e:
        return jsonify({"error": f"Database error: {e}", "success": False}), 500


@bp.route("/api/tree/<uuid:tree_id>/persons/batch", methods=["POST"])
@login_required
@no_cache
@csrf_protect_api
def batch_update_persons(tree_id: uuid.UUID):
    """Adds, modifies, or deletes persons. Requires edit permission."""
    user_id = session.get("user_id")
    permissions = get_tree_and_user_permissions(tree_id, user_id)
    if not permissions:
        return jsonify({"error": "Tree not found", "success": False}), 404
    if not permissions["can_edit"]:
        return jsonify({"error": "Edit permission denied", "success": False}), 403

    payload = request.get_json()
    if not isinstance(payload, dict):
        return (
            jsonify(
                {"error": "Invalid payload: JSON object expected", "success": False}
            ),
            400,
        )

    persons_to_add = payload.get("add", [])
    persons_to_modify = payload.get("modify", [])
    ids_to_delete = payload.get("delete", [])

    # Basic validation for persons_to_add and persons_to_modify
    for person_list in [persons_to_add, persons_to_modify]:
        for person_data in person_list:
            for key, value in person_data.items():
                if isinstance(value, str) and key not in ["id", "photo", "documents"]:
                    person_data[key] = nh3.clean(value)

            # Check person.photo.url
            if "photo" in person_data and isinstance(person_data["photo"], str):
                photo_url = person_data["photo"].strip().lower()

                if photo_url:
                    is_valid_scheme = (
                        photo_url.startswith("http:")
                        or photo_url.startswith("https:")
                        or photo_url.startswith("/")
                    )

                    is_dangerous = (
                        photo_url.startswith("javascript:")
                        or photo_url.startswith("data:")
                        or photo_url.startswith("vbscript:")
                    )

                    if not is_valid_scheme or is_dangerous:
                        return (
                            jsonify(
                                {
                                    "error": "Security check failed: Illegal URL scheme",
                                    "success": False,
                                }
                            ),
                            400,
                        )

            # Check person.documents[].url
            if "documents" in person_data and isinstance(
                person_data["documents"], list
            ):
                for doc in person_data["documents"]:
                    if (
                        isinstance(doc, dict)
                        and "url" in doc
                        and isinstance(doc["url"], str)
                    ):
                        doc_url = doc["url"].strip().lower()

                        if doc_url:
                            is_valid_scheme = (
                                doc_url.startswith("http:")
                                or doc_url.startswith("https:")
                                or doc_url.startswith("/")
                            )

                            is_dangerous = (
                                doc_url.startswith("javascript:")
                                or doc_url.startswith("data:")
                                or doc_url.startswith("vbscript:")
                            )

                            if not is_valid_scheme or is_dangerous:
                                return (
                                    jsonify(
                                        {
                                            "error": "Invalid URL in person.documents.url",
                                            "success": False,
                                        }
                                    ),
                                    400,
                                )

    try:
        files_to_delete = []
        api_file_prefix = f"/api/tree/{tree_id}/file/"

        # --- File deletion management for modified persons ---
        if persons_to_modify:
            modified_ids = [p["id"] for p in persons_to_modify]
            # Retrieve current data for persons being modified
            response = (
                supabase.table("persons")
                .select("id, data")
                .eq("tree_id", str(tree_id))
                .in_("id", modified_ids)
                .execute()
            )
            current_persons_data = {item["id"]: item["data"] for item in response.data}

            for new_person_data in persons_to_modify:
                person_id = new_person_data["id"]
                if person_id in current_persons_data:
                    old_data = current_persons_data[person_id]
                    new_data = new_person_data

                    # Compare photo
                    old_photo_url = old_data.get("photo", "")
                    new_photo_url = new_data.get("photo", "")
                    if (
                        old_photo_url
                        and old_photo_url != new_photo_url
                        and old_photo_url.startswith(api_file_prefix)
                    ):
                        files_to_delete.append(
                            old_photo_url.replace(api_file_prefix, "")
                        )

                    # Compare documents
                    old_docs_urls = {
                        doc["url"]
                        for doc in old_data.get("documents", [])
                        if "url" in doc and doc["url"].startswith(api_file_prefix)
                    }
                    new_docs_urls = {
                        doc["url"]
                        for doc in new_data.get("documents", [])
                        if "url" in doc
                    }
                    deleted_docs_urls = old_docs_urls - new_docs_urls
                    for url in deleted_docs_urls:
                        files_to_delete.append(url.replace(api_file_prefix, ""))

        # --- File deletion management for deleted persons ---
        if ids_to_delete:
            response = (
                supabase.table("persons")
                .select("data")
                .eq("tree_id", str(tree_id))
                .in_("id", ids_to_delete)
                .execute()
            )
            for person_data in response.data:
                data = person_data["data"]
                # Delete photo
                photo_url = (
                    data.get("photo", {}).get("url", "")
                    if isinstance(data.get("photo"), dict)
                    else data.get("photo", "")
                )
                if photo_url and photo_url.startswith(api_file_prefix):
                    files_to_delete.append(photo_url.replace(api_file_prefix, ""))

                # Delete documents
                if "documents" in data:
                    for doc in data["documents"]:
                        doc_url = doc.get("url")
                        if doc_url and doc_url.startswith(api_file_prefix):
                            files_to_delete.append(doc_url.replace(api_file_prefix, ""))

        # Call the atomic PostgreSQL function
        supabase.rpc(
            "batch_update_persons_atomic",
            {
                "p_tree_id": str(tree_id),
                "p_persons_to_add": persons_to_add,
                "p_persons_to_modify": persons_to_modify,
                "p_ids_to_delete": ids_to_delete,
            },
        ).execute()

        # Delete files from storage if necessary
        if files_to_delete:
            # Remove duplicates in case of, for example, re-setting a photo to null
            unique_files_to_delete = list(set(files_to_delete))
            if unique_files_to_delete:
                supabase.storage.from_(STORAGE_BUCKET_NAME).remove(
                    unique_files_to_delete
                )

        return jsonify({"success": True, "message": "Batch update successful."})
    except Exception as e:
        # Errors from the PostgreSQL function (version conflict, etc.) will be caught here.
        # The supabase-py library encapsulates the PostgREST error into a generic exception.
        return (
            jsonify(
                {"error": f"Error during batch processing: {str(e)}", "success": False}
            ),
            500,
        )
