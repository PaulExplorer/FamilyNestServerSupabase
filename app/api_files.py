from flask import Blueprint, request, session, jsonify, redirect
from PIL import Image, ImageOps
import uuid, io, os

from .utils import (
    login_required,
    get_tree_and_user_permissions,
    no_cache,
    csrf_protect_api,
)
from . import supabase, STORAGE_BUCKET_NAME, SIGNED_URL_EXPIRATION_SECONDS

bp = Blueprint("api_files", __name__, template_folder="templates")


@bp.route("/api/tree/<uuid:tree_id>/upload/<string:type>", methods=["POST"])
@login_required
@no_cache
@csrf_protect_api
def upload_file(tree_id: uuid.UUID, type: str):
    """Uploads a file. Requires edit permission and that uploads are enabled."""
    user_id = session.get("user_id")
    permissions = get_tree_and_user_permissions(tree_id, user_id)
    if not permissions:
        return jsonify({"error": "Tree not found", "success": False}), 404
    if not permissions["can_edit"]:
        return jsonify({"error": "Edit permission denied", "success": False}), 403
    if not permissions["tree"]["allow_file_uploads"]:
        return (
            jsonify(
                {"error": "File uploads are disabled for this tree", "success": False}
            ),
            403,
        )

    if type not in ["image", "document"]:
        return jsonify({"error": "Invalid upload type", "success": False}), 400
    if type not in request.files:
        return jsonify({"error": f"No '{type}' file in request", "success": False}), 400

    file = request.files.get(type)
    if not file or not file.filename:
        return jsonify({"error": "No file selected", "success": False}), 400

    # Generate a random filename using UUID to prevent conflicts and improve security
    _, extension = os.path.splitext(file.filename)
    new_filename = f"{uuid.uuid4()}{extension}"
    file_path = f"{tree_id}/{type}s/{new_filename}"
    file_content = None
    content_type = file.mimetype
    content_disposition = (
        f'attachment; filename="{file.filename}"'  # Default to attachment
    )

    try:
        if type == "image":
            # Compress the image
            img = Image.open(file.stream)

            # Correct image orientation using EXIF data
            img = ImageOps.exif_transpose(img)

            # Ensure the image is in RGB mode to avoid issues with palettes (GIF, etc.)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Resize if the image is too large, maintaining aspect ratio
            max_size = (500, 500)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # Save the compressed image to an in-memory buffer
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format="WebP", quality=80)
            file_content = img_byte_arr.getvalue()
            content_type = "image/webp"
            # The file path needs to be updated to reflect the new .webp format
            new_filename_webp = f"{uuid.uuid4()}.webp"
            file_path = f"{tree_id}/{type}s/{new_filename_webp}"
            # For images, we want them to be displayed inline
            content_disposition = f'inline; filename="{new_filename_webp}"'
        else:
            # For other file types, simply read the content
            file_content = file.read()

        supabase.storage.from_(STORAGE_BUCKET_NAME).upload(
            path=file_path,
            file=file_content,
            file_options={
                "content-type": content_type,
                "upsert": "true",
                "content-disposition": content_disposition,
            },
        )
        # Return the internal file path. The frontend will use this path to call the secured endpoint.
        return (
            jsonify(
                {
                    "success": True,
                    "message": f"{type.capitalize()} uploaded successfully.",
                    "filename": file.filename,
                    "url": "/api/tree/" + str(tree_id) + "/file/" + file_path,
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"error": f"Upload failed: {e}", "success": False}), 500


@bp.route("/api/tree/<uuid:tree_id>/file/<path:file_path>", methods=["GET"])
@no_cache  # Important: do not cache the redirection response itself
def serve_protected_file(tree_id: uuid.UUID, file_path: str):
    """
    Serves a protected file after permission check, using temporary signed URLs.
    """
    user_id = session.get("user_id")

    # 1. Check tree viewing permissions
    permissions = get_tree_and_user_permissions(tree_id, user_id)
    if not permissions:
        return jsonify({"error": "Tree not found", "success": False}), 404
    if not permissions["can_view"]:
        return (
            jsonify(
                {
                    "error": "Access denied. You do not have permission to view this file.",
                    "success": False,
                }
            ),
            403,
        )

    # 2. Security: Ensure the requested file path belongs to this tree.
    # This prevents access attempts to other trees' files via a valid tree_id.
    expected_prefix = f"{tree_id}/"
    if not file_path.startswith(expected_prefix):
        return (
            jsonify({"error": "Invalid file path for this tree.", "success": False}),
            400,
        )

    # 3. Generate a temporary signed URL
    try:
        # The 'file_path' is already the full path in the bucket (e.g., "tree_id/images/photo.jpg")
        signed_url_response = supabase.storage.from_(
            STORAGE_BUCKET_NAME
        ).create_signed_url(file_path, SIGNED_URL_EXPIRATION_SECONDS)
        signed_url = signed_url_response["signedURL"]

        # 4. Redirect the client to the temporary signed URL
        return redirect(
            signed_url, code=302
        )  # Use code 302 (Found) or 307 (Temporary Redirect)
    except Exception as e:
        return (
            jsonify({"error": f"Failed to generate signed URL: {e}", "success": False}),
            500,
        )
