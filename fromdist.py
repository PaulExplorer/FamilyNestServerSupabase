"""
This script automates the process of taking a 'dist' directory (typically from a frontend build process),
restructuring its contents into a Flask-compatible static and templates directory, and performing
URL rewrites within HTML files.

It performs the following main steps:
1.  **Initialization**: Defines regex patterns for URL transformation and helper functions.
2.  **Directory Setup**: Moves the 'static' folder from 'dist' to the project root, creates
    'static/scripts', 'static/styles', and 'templates' directories.
3.  **File Restructuring**: Iterates through files in the 'dist' directory:
    *   Moves `.js` and `.wasm` files to `static/scripts/` and renames them by removing hash suffixes
        (e.g., `ui-a1b2c3d4.js` becomes `ui.js`).
    *   Moves `.css` files to `static/styles/` and renames them similarly.
    *   Moves `.html` files to the `templates/` directory.
4.  **Cleanup**: Removes the original 'dist' directory.
5.  **Template Processing**: Modifies `templates/index.html` to:
    *   Rewrite URLs to point to the new static asset locations.
    *   Replace a specific API connection string with a Flask URL (`/api/tree/{{tree_id}}`).
    *   Add CSRF token support.
    *   Remove `integrity` attributes from script/link tags.
6.  **Locale Minification**: Minifies JSON locale files in `static/locales`.
7.  **Finalization (User Confirmed)**:
    *   Copies files from an `internal` directory into the `static` directory, merging locale files.
    *   Renames `templates/index.html` to `templates/tree.html`.

This script is designed to be run after a frontend build (e.g., Vite, Webpack) to integrate the
generated assets into a Flask application structure.
"""

import re, os, pathlib, shutil, json
from os import listdir
from os.path import isfile, join
from typing import Dict

print("🔍 Initializing URL pattern and transformation functions...")
PATTERN = re.compile(
    r'(?P<prefix>\b(?:href|src)\s*=\s*|module_or_path\s*:\s*|from\s+)(?P<quote>["\']?)(?P<url>/[^"\'\s>]+?\.(?P<ext>css|js|wasm)(?:\?[^#"\']*)?(?:#[^"\']*)?)(?P=quote)',
    flags=re.IGNORECASE,
)

filename_map: Dict[str, str] = {}


def clean_filename(filename: str) -> str:
    """Removes the hash from a filename (e.g., 'ui-a1b2c3d4.js' -> 'ui.js')."""
    if "-" not in filename:
        return filename

    name, ext = os.path.splitext(filename)
    parts = name.split("-")
    return f"{parts[0]}{ext}"


def transform_url(url: str) -> str:
    if url.startswith("//") or url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/static/"):
        return url
    if url.startswith("/snippets/"):
        return f"/static/scripts{url}"
    path = url
    frag = ""
    if "#" in path:
        path, frag = path.split("#", 1)
        frag = "#" + frag
    q = ""
    if "?" in path:
        path, q = path.split("?", 1)
        q = "?" + q
    basename = os.path.basename(path)
    # Use the new, clean filename if it's in our map
    if basename in filename_map:
        basename = filename_map[basename]

    ext = basename.split(".")[-1].lower()
    if ext == "css":
        new = f"/static/styles/{basename}{q}{frag}"
    else:
        new = f"/static/scripts/{basename}{q}{frag}"
    return new


def replacer(match: re.Match) -> str:
    prefix = match.group("prefix")
    quote = match.group("quote")
    url = match.group("url")
    new = transform_url(url)
    if new == url:
        return match.group(0)
    return f"{prefix}{quote}{new}{quote}"


def process_text_urls(text: str) -> str:
    return PATTERN.sub(replacer, text)


def process_template_file(path: str, inplace: bool = True) -> None:
    p = pathlib.Path(path)
    print(f"📄 Processing file: {path}")
    text = p.read_text(encoding="utf-8")
    # Specific replacement for API connection
    text = text.replace(
        "let a=`main`;const b=new URLSearchParams(window.location.search);const c=b.get(`tree`);if(c){console.log(`Tree parameter from URL:`,c);a=c};initConnection(`http://127.0.0.1:5000/`+ a)",
        "initConnection('/api/tree/{{tree_id}}')",
    )
    text = text.replace(
        "additionalHeaders={}", 'additionalHeaders={"X-CSRFToken":"{{csrf_token()}}"}'
    )

    integrity_pattern = r'\s+integrity\s*=\s*(?:(["\']).*?\1|[^\s>]+)'
    text = re.sub(integrity_pattern, "", text, flags=re.IGNORECASE)

    # First, replace hashed filenames with clean ones
    for old, new in filename_map.items():
        print(old, new)
        text = text.replace(old, new)

    new_text = process_text_urls(text)
    if new_text != text:
        if inplace:
            p.write_text(new_text.replace("\n", ""), encoding="utf-8")
        print(f"✔ Modified: {path}")
    else:
        print(f"- No changes: {path}")


print("\n📁 Organizing static and template files...")
dist_path = "dist"
static_path = "static"

if os.path.exists(static_path):
    print(f"🗑️  Removing existing '{static_path}' directory...")
    shutil.rmtree(static_path)

shutil.move(os.path.join(dist_path, "static"), static_path)
print(f"🚚 Moved '{os.path.join(dist_path, 'static')}' to '{static_path}'")

for folder in [
    os.path.join(static_path, "scripts"),
    os.path.join(static_path, "styles"),
    "templates",
]:
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"📂 Created directory: {folder}")

dist_files = [f for f in listdir(dist_path) if isfile(join(dist_path, f))]

for filename in dist_files:
    new_filename = clean_filename(filename)
    filename_map[filename] = new_filename

    source = os.path.join(dist_path, filename)
    if filename.endswith(".js") or filename.endswith(".wasm"):
        destination = os.path.join(static_path, "scripts", new_filename)
        shutil.move(source, destination)
        print(f"📥 Moved and renamed JS/WASM: {filename} -> {new_filename}")
    elif filename.endswith(".css"):
        destination = os.path.join(static_path, "styles", new_filename)
        shutil.move(source, destination)
        print(f"📥 Moved and renamed CSS: {filename} -> {new_filename}")
    elif filename.endswith(".html"):
        shutil.move(source, "templates/" + filename)
        print(f"📥 Moved HTML file: {filename}")

shutil.move(
    os.path.join(dist_path, "snippets/"), os.path.join(static_path, "scripts/snippets/")
)
print("🗑️  Removing empty 'dist' directory...")
shutil.rmtree(dist_path)

print("🔧 Processing main template file...")
process_template_file("templates/index.html")

print("📜 Minifying locale files...")
mypath = "static/locales"
onlylang = [f for f in listdir(mypath) if isfile(join(mypath, f))]
for file in onlylang:
    with open(f"static/locales/{file}", "r+", encoding="utf-8") as f:
        content = json.load(f)
        f.seek(0)
        f.truncate()
        json.dump(content, f, separators=(",", ":"))
    print(f"✔ Minified locale file: {file}")

print("✨ All tasks completed successfully!")

# --- START OF CORRECTED BLOCK ---

print("\n--- Finalization step of the migration ---")
confirmation = input(
    "Do you want to finalize the migration (copy 'internal' files and rename 'index.html')? (y/n): "
)

if confirmation.lower().strip() in ["o", "oui", "y", "yes"]:
    print("\n✅ Confirmation received. Executing final steps...")

    # 1. Copy each file from the 'internal' folder to its destination
    source_dir = "internal"
    dest_base_dir = "static"

    if os.path.isdir(source_dir):
        print(f"\n📁 Copying files from folder '{source_dir}' to '{dest_base_dir}'...")
        # os.walk iterates through the source folder structure
        for root, dirs, files in os.walk(source_dir):
            for filename in files:
                # Build the full path of the source file
                source_file = os.path.join(root, filename)

                # Create the destination path preserving the structure
                # Example: 'internal/styles/style.css' -> 'static/styles/style.css'
                relative_path = os.path.relpath(source_file, source_dir)
                dest_file = os.path.join(dest_base_dir, relative_path)

                # Ensure the destination directory exists
                dest_folder = os.path.dirname(dest_file)
                os.makedirs(dest_folder, exist_ok=True)

                if "locales" in root:
                    with open(source_file, "r", encoding="utf-8") as f:
                        translations = json.load(f)
                    with open(dest_file, "r+", encoding="utf-8") as f:
                        existing_translations = json.load(f)
                        existing_translations.update(translations)
                        f.seek(0)
                        f.truncate()
                        json.dump(existing_translations, f, separators=(",", ":"))
                        print(f"  -> Merged and minified {source_file} to {dest_file}")
                        continue  # Skip file copy for locales as we merge

                # Copy the file
                shutil.copy2(source_file, dest_file)
                print(f"  -> Copied {source_file} to {dest_file}")
        print("✔ Copying of 'internal' files completed.")
    else:
        print(
            f"⚠️  Warning: Directory '{source_dir}' not found. Skipping file copy step."
        )

    # 2. Rename the templates/index.html file to templates/tree.html
    source_html = "templates/index.html"
    dest_html = "templates/tree.html"
    print(f"\n🔄 Renaming '{source_html}' to '{dest_html}'...")
    if os.path.exists(source_html):
        # Ensure destination is removed if it exists to prevent error on some systems
        if os.path.exists(dest_html):
            os.remove(dest_html)
        os.rename(source_html, dest_html)
        print("✔ File renamed successfully.")
    else:
        print(f"⚠️  Warning: File '{source_html}' not found, rename skipped.")

    print("\n🎉 Final migration completed successfully!")

else:
    print("\n❌ Operation cancelled by user. No final modifications were made.")
