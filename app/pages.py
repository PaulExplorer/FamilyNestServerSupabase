from flask import (
    Blueprint,
    request,
    render_template,
    session,
    redirect,
    url_for,
    send_from_directory,
)
from datetime import datetime, timezone
import uuid

from .utils import login_required, no_cache
from . import supabase, demo_id, support_email

bp = Blueprint(
    "pages", __name__, template_folder="../templates", static_folder="../static"
)


@bp.route("/favicon.ico")
def favicon():
    return send_from_directory(
        bp.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon"
    )


@bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("pages.home"))
    return render_template("landing.html", demo_id=demo_id)


@bp.route("/contact")
def contact():
    return render_template("contact.html", support_email=support_email)


@bp.route("/legal-notice")
def legal_notice():
    return render_template("legal_notice.html", support_email=support_email)


@bp.route("/terms-of-service")
def terms_of_service():
    return render_template("terms_of_service.html")


@bp.route("/privacy-policy")
def privacy_policy():
    return render_template("privacy_policy.html", support_email=support_email)


@bp.route("/home")
@no_cache
@login_required
def home():
    user_id = session.get("user_id")
    error = request.args.get("error", None)

    trees_response = (
        supabase.table("trees")
        .select("id, name, owner_id, editor_ids, viewer_ids, created_at, updated_at")
        .or_(
            f"owner_id.eq.{user_id}, editor_ids.cs.{{{user_id}}}, viewer_ids.cs.{{{user_id}}}"
        )
        .execute()
    )
    user_trees = trees_response.data if trees_response.data else []

    # Retrieve active invitation links for trees where the user is the owner
    owned_tree_ids = [
        tree["id"] for tree in user_trees if tree.get("owner_id") == user_id
    ]
    invitations_map = {}
    if owned_tree_ids:
        invitations_resp = (
            supabase.table("tree_invitations")
            .select("token, tree_id, role, usage_limit, used_by_users, expires_at")
            .in_("tree_id", owned_tree_ids)
            .gt("expires_at", datetime.now(timezone.utc).isoformat())
            .execute()
        )

        if invitations_resp.data:
            active_invitations = []
            for inv in invitations_resp.data:
                used_count = len(inv.get("used_by_users") or [])
                if inv.get("usage_limit") is None or used_count < inv.get(
                    "usage_limit"
                ):
                    inv["used_count"] = used_count
                    active_invitations.append(inv)

            # Group invitations by tree_id
            for inv in active_invitations:
                if inv["tree_id"] not in invitations_map:
                    invitations_map[inv["tree_id"]] = []
                invitations_map[inv["tree_id"]].append(inv)

    all_user_ids = set()
    for tree in user_trees:
        tree["created_at"] = datetime.fromisoformat(tree["created_at"]).strftime(
            "%d/%m/%Y"
        )
        tree["updated_at"] = (
            datetime.fromisoformat(tree["updated_at"]).strftime("%d/%m/%Y")
            if tree.get("updated_at")
            else None
        )

        if tree["owner_id"] == user_id:
            tree["admin"] = True
            all_user_ids.update(tree.get("editor_ids") or [])
            all_user_ids.update(tree.get("viewer_ids") or [])
        else:
            tree["admin"] = False

        tree["invitations"] = invitations_map.get(tree["id"], [])

    users_map = {}
    if all_user_ids:
        # Fetch user details (assuming admin privileges or proper Supabase setup for this RPC)
        users_response = [
            supabase.auth.admin.get_user_by_id(uid).user for uid in all_user_ids
        ]
        users_map = {
            str(user.id): {"id": str(user.id), "email": user.email}
            for user in users_response
        }

    for tree in user_trees:
        tree["editors"] = [
            users_map[uid] for uid in tree.get("editor_ids", []) if uid in users_map
        ]
        tree["viewers"] = [
            users_map[uid] for uid in tree.get("viewer_ids", []) if uid in users_map
        ]

    return render_template(
        "home.html", user_email=session.get("user_email"), trees=user_trees, error=error
    )


@bp.route("/tree/<uuid:tree_id>", methods=["GET"])
def tree_page(tree_id: uuid.UUID):
    """Displays the HTML page for the family tree."""
    return render_template("tree.html", tree_id=str(tree_id))
