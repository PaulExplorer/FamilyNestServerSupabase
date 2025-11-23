from flask import (
    Blueprint,
    jsonify,
    request,
    render_template,
    session,
    redirect,
    url_for,
)
from supabase import create_client, AuthApiError
from datetime import datetime, timezone
import os

from . import supabase, csrf
from .utils import process_invitation, login_required

bp = Blueprint("auth", __name__, template_folder="templates")


@bp.route("/login", methods=["GET", "POST"])
def login(signup=False):
    message = request.args.get("message", "")
    message_t = request.args.get("message_t", "")

    if request.method == "POST":
        csrf.protect()

        email = request.form.get("email")
        password = request.form.get("password")
        try:
            auth_client = create_client(
                os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
            )
            auth_response = auth_client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )

            session["user_id"] = str(auth_response.user.id)
            session["user_email"] = auth_response.user.email
            session.permanent = True

            if "join_token" in session:
                token = session.pop("join_token")
                tree_id_to_join = process_invitation(token, session["user_id"])

                if tree_id_to_join:
                    return redirect(url_for("pages.tree_page", tree_id=tree_id_to_join))
                else:
                    return redirect(
                        url_for(
                            "pages.home", error="The invitation is no longer valid."
                        )
                    )
            return redirect(url_for("pages.home"))
        except AuthApiError as e:
            return render_template("login.html", error=e.message, error_t="")
    return render_template(
        "login.html", message=message, message_t=message_t, signup=signup
    )


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        csrf.protect()

        pseudo = request.form.get("pseudo")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        if password != confirm_password:
            return render_template(
                "login.html",
                error="Passwords do not match.",
                error_t="LOGIN_PAGE.MESSAGES.PASSWORDS_DONT_MATCH",
                signup=True,
            )

        try:
            supabase.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {"data": {"pseudo": pseudo}},
                }
            )
            # Redirect to login after successful signup
            return redirect(
                url_for(
                    "auth.login",
                    message="Signup successful! Please check your email to confirm your account and then log in.",
                    message_t="LOGIN_PAGE.MESSAGES.SIGNUP_SUCCESS",
                )
            )
        except AuthApiError as e:
            return render_template("login.html", error=e.message)
    # The signup form will be on the same page as login
    return login(signup=True)


@bp.route("/logout")
def logout():
    session.clear()  # Clears the session
    return redirect(url_for("auth.login"))


@bp.route("/join/<uuid:token>")
def join_by_token(token):
    token_str = str(token)
    try:
        invitation_resp = (
            supabase.table("tree_invitations")
            .select("expires_at, used_by_users, usage_limit")
            .eq("token", token_str)
            .single()
            .execute()
        )
        invitation = invitation_resp.data
        is_expired = datetime.fromisoformat(invitation["expires_at"]) < datetime.now(
            timezone.utc
        )
        usage_limit = invitation.get("usage_limit")
        is_full = (
            usage_limit is not None
            and len(invitation.get("used_by_users") or []) >= usage_limit
        )
        if not invitation or is_expired or is_full:
            return (
                render_template(
                    "invalid_link.html",
                    message="This invitation link is invalid, expired, or has reached its usage limit.",
                ),
                400,
            )
    except Exception:
        return (
            render_template(
                "invalid_link.html",
                message="This invitation link is invalid or has expired.",
            ),
            400,
        )

    if "user_id" in session:
        tree_id_to_join = process_invitation(token_str, session["user_id"])
        if tree_id_to_join:
            return redirect(url_for("pages.tree_page", tree_id=tree_id_to_join))
        else:
            return (
                render_template(
                    "invalid_link.html", message="Could not process this invitation."
                ),
                500,
            )
    else:
        session["join_token"] = token_str
        return redirect(
            url_for(
                "auth.login",
                message="Please log in or create an account to join the tree.",
                message_t="LOGIN_PAGE.MESSAGES.JOIN_TREE_PROMPT",
            )
        )


@bp.route("/set-session", methods=["POST"])
def set_session():
    """
    API route to set the user session from access and refresh tokens.
    Used after email confirmation or magic link login.
    """
    data = request.get_json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    if not access_token or not refresh_token:
        return jsonify({"success": False, "error": "Missing tokens"}), 400

    try:
        auth_client = create_client(
            os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
        )
        # Set the session in the Supabase client for subsequent API calls
        auth_response = auth_client.auth.set_session(access_token, refresh_token)

        # Store user info in Flask session
        session["user_id"] = str(auth_response.user.id)
        session["user_email"] = auth_response.user.email

        # Handle a pending invitation
        redirect_url = url_for("pages.home")
        if "join_token" in session:
            token = session.pop("join_token")
            tree_id_to_join = process_invitation(token, session["user_id"])
            if tree_id_to_join:
                redirect_url = url_for("pages.tree_page", tree_id=tree_id_to_join)

        return jsonify({"success": True, "redirect_url": redirect_url})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/request-password-reset", methods=["GET", "POST"])
def request_password_reset():
    if request.method == "POST":
        csrf.protect()
        email = request.form.get("email")
        try:
            # This will send a password reset email to the user
            supabase.auth.reset_password_for_email(
                email,
                options={"redirect_to": url_for("auth.reset_password", _external=True)},
            )
            return redirect(
                url_for(
                    "auth.login",
                    message="Si un compte existe pour cet email, un lien de réinitialisation a été envoyé.",
                    message_t="LOGIN_PAGE.MESSAGES.RESET_LINK_SENT",
                )
            )
        except AuthApiError as e:
            # Don't reveal if the user exists or not
            return redirect(
                url_for(
                    "auth.login",
                    message="Si un compte existe pour cet email, un lien de réinitialisation a été envoyé.",
                    message_t="LOGIN_PAGE.MESSAGES.RESET_LINK_SENT",
                )
            )
        except Exception as e:
            return render_template(
                "login.html", error=f"An error occurred: {str(e)}", error_t=""
            )

    # This route is POST only for the form, but we can redirect to login if accessed via GET
    return redirect(url_for("auth.login"))


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        csrf.protect()
        access_token = request.form.get("access_token")
        refresh_token = request.form.get("refresh_token")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if not access_token:
            return render_template(
                "reset_password.html",
                error="Le jeton d'accès est manquant ou invalide.",
                error_t="RESET_PASSWORD_PAGE.MESSAGES.INVALID_TOKEN",
            )

        if not new_password or new_password != confirm_password:
            return render_template(
                "reset_password.html",
                error="Les mots de passe ne correspondent pas ou sont vides.",
                error_t="RESET_PASSWORD_PAGE.MESSAGES.PASSWORD_MISMATCH",
                access_token=access_token,
                refresh_token=refresh_token,
            )

        try:
            # Create a temporary client to update the user with the access token
            auth_client = create_client(
                os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
            )

            # The access token from the password reset email is passed here
            auth_client.auth.set_session(
                access_token=access_token, refresh_token=refresh_token
            )
            user_response = auth_client.auth.update_user({"password": new_password})

            return redirect(
                url_for(
                    "auth.login",
                    message="Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.",
                    message_t="LOGIN_PAGE.MESSAGES.PASSWORD_RESET_SUCCESS",
                )
            )
        except AuthApiError as e:
            return render_template(
                "reset_password.html",
                error=e.message,
                error_t="",
                access_token=access_token,
                refresh_token=refresh_token,
            )
        except Exception as e:
            return render_template(
                "reset_password.html",
                error=f"Une erreur est survenue: {str(e)}",
                error_t="",
                access_token=access_token,
                refresh_token=refresh_token,
            )

    return render_template("reset_password.html")


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user_id = session["user_id"]
    message = request.args.get("message", None)
    message_t = request.args.get("message_t", None)
    error = request.args.get("error", None)
    error_t = request.args.get("error_t", None)

    try:
        user = supabase.auth.admin.get_user_by_id(user_id).user

        if request.method == "POST":
            csrf.protect()

            action = request.form.get("action")

            if action == "change_password":
                new_password = request.form.get("new_password")
                confirm_password = request.form.get("confirm_password")

                if not new_password or new_password != confirm_password:
                    error = "Passwords do not match or are empty."
                    return render_template(
                        "account.html",
                        user=user,
                        error=error,
                        error_t="ACCOUNT_PAGE.MESSAGES.PASSWORD_MISMATCH",
                    )

                try:
                    supabase.auth.admin.update_user_by_id(
                        user_id, {"password": new_password}
                    )
                    message = "Your password has been updated successfully."
                    message_t = "ACCOUNT_PAGE.MESSAGES.PASSWORD_UPDATE_SUCCESS"
                except AuthApiError as e:
                    error = f"Failed to update password: {e.message}"
                    error_t = "ACCOUNT_PAGE.MESSAGES.PASSWORD_UPDATE_ERROR"

            elif action == "delete_account":
                try:
                    supabase.auth.admin.delete_user(user_id)

                    trees_response = supabase.table("trees").select("id", "editors", "viewers").or_(
                        f"editors.cs.{{{user_id}}}", f"viewers.cs.{{{user_id}}}"
                    ).execute()

                    if trees_response.data:
                        for tree in trees_response.data:
                            tree_id = tree["id"]
                            editors = tree.get("editors", [])
                            viewers = tree.get("viewers", [])

                            if user_id in editors:
                                editors.remove(user_id)
                            if user_id in viewers:
                                viewers.remove(user_id)

                            supabase.table("trees").update(
                                {"editors": editors, "viewers": viewers}
                            ).eq("id", tree_id).execute()


                    return redirect(
                        url_for(
                            "auth.logout",
                            message="Account deletion initiated. You have been logged out.",
                            message_t="ACCOUNT_PAGE.MESSAGES.ACCOUNT_DELETED",
                        )
                    )
                except Exception as e:
                    error = f"Could not process account deletion: {str(e)}"
                    error_t = "ACCOUNT_PAGE.MESSAGES.DELETE_ACCOUNT_ERROR"

        return render_template(
            "account.html",
            user=user,
            message=message,
            message_t=message_t,
            error=error,
            error_t=error_t,
        )

    except AuthApiError as e:
        return redirect(url_for("auth.login", error=f"Session error: {e.message}"))
    except Exception as e:
        return redirect(url_for("auth.account", error=f"An error occurred: {str(e)}"))
