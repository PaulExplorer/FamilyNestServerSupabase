# FamilyNest Supabase Server

This repository contains the backend server for the [FamilyNestWeb](https://github.com/PaulExplorer/FamilyNestWeb) application. It is built with Flask and integrates deeply with Supabase for database management, authentication, and file storage.

## Features

- **User Management**: Secure user registration and login handled by Supabase Auth.
- **Tree Management**: Create, delete, and manage multiple family trees per user.
- **Collaboration**:
  - Share trees with other users via email with role-based permissions (owner, editor, viewer).
  - Generate secure, time-limited, and usage-capped invitation links.
- **Data Operations**: Atomic batch updates for person data (add, modify, delete) using a PostgreSQL function to prevent race conditions with optimistic locking (versioning).
- **Secure File Handling**:
  - Upload images and documents to a private Supabase Storage bucket.
  - On-the-fly image compression and optimization.
  - Serve files securely using temporary signed URLs.
- **Multi-language Support**: Built-in translation system to support multiple languages.

## Technologies

- **Backend**: [Flask](https://flask.palletsprojects.com/)
- **Database & Auth**: [Supabase](https://supabase.com/) (Supabase API)
- **Python Libraries**:
  - `Flask-Minify` for minifying HTML, CSS, and JS.
  - `Flask-Compress` for GZip compression.
  - `Flask-Talisman` for enforcing HTTPS and Content Security Policy.
  - `Flask-WTF` for Flask-WTF forms and CSRF protection.
  - `supabase-py` for Supabase interaction.
  - `Pillow` for image processing.
  - `python-dotenv` for environment variable management.

## Project Structure

Here's an overview of the key files and directories in this project:

- `main.py`: The entry point for the Flask application.
- `fromdist.py`: A utility script designed to automate the process of updating the FamilyNest front-end. It takes the compiled output from `trunk` (the `dist` directory), reorganizes files, updates asset paths, and merges new translations, simplifying version migrations.
- `app/`: This directory contains the core application logic, organized into blueprints for better modularity.
- `sql/`: This directory contains all the necessary SQL scripts to set up the Supabase database. This includes table creation (`trees`, `persons`, etc.) and the definitions of PostgreSQL functions used by the application (e.g., for batch operations).
- `static/`: Contains all static assets for both the FamilyNest interface and the server's own pages. This includes CSS, JavaScript, images, and locale files for translations.
- `internal/`: Holds static files that are specific to this server implementation (like custom styles or scripts for the home page). This separation makes it easier to update the core FamilyNest front-end without overwriting custom modifications. The `fromdist.py` script handles merging these files during an update.
- `templates/`: This directory holds the HTML templates rendered by Flask.
  - `tree.html`: The main single-page application for the FamilyNest editor. It's the entry point for the family tree interface.
  - Other `.html` files: These are the templates for the server's own pages, such as the landing page, login, user dashboard (`home.html`), etc.

## Getting Started

### Prerequisites

- Python 3.8+
- A Supabase account (you can create one [here](https://supabase.com/))

### Installation

1. Clone the repository:

   ```sh
   git clone https://github.com/PaulExplorer/FamilyNestWebSupabase.git
   cd FamilyNestWebSupabase
   ```

2. Create and activate a virtual environment:

   ```sh
   python -m venv venv
   # On Windows
   .\venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   ```

3. Install the required dependencies:

   ```sh
   pip install -r requirements.txt
   ```

4. **Set up your Supabase project:**

   - Create a new project on the [Supabase Dashboard](https://app.supabase.com).
   - Go to the **SQL Editor** in your project dashboard.
   - Run all the SQL queries located in the `sql/` directory of this repository. This will create the necessary tables (`trees`, `persons`, `tree_invitations`) and database functions.
   - Go to **Storage** and create a new **private** bucket named `tree_files`.

5. **Configure environment variables:**

   - Create a `.env` file in the root of the project by copying the example:
     ```sh
     cp .env.example .env
     ```
   - Fill in the `.env` file with your Supabase project URL and `anon` key. You can find these in your Supabase project's "API" settings.
     ```
     SUPABASE_URL="YOUR_SUPABASE_URL"
     SUPABASE_KEY="YOUR_SUPABASE_ANON_KEY"
     FLASK_SECRET_KEY="a-strong-and-random-secret-key"
     DEMO_TREE_ID="YOUR_DEMO_TREE_ID" # should be a public tree and in demo mode
     SUPPORT_EMAIL="your.email@support.com"
     ENV="development" # or production
     ```

6. Start the server:
   ```sh
   python main.py
   ```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request or open an issue for any bugs or feature requests.

## License

This project is licensed under the **AGPLv3 License**.
