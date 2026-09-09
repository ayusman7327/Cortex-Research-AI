# Authentication setup

Every research workspace requires a sign-in. Choose one account system for a deployment:

| Mode | Best fit | Account storage |
| --- | --- | --- |
| `local` (default) | Your computer or a server with persistent private storage | SQLite database controlled by you |
| `oidc` | Streamlit Community Cloud or another public deployment | Google or another OpenID Connect identity provider |

Both modes clear the current research workspace when the user logs out. Documents and chat are not saved as an account library. Changing authentication modes does not transfer accounts or restore workspaces.

## Local accounts

Use these settings in your private `.env` file:

~~~dotenv
CORTEX_AUTH_MODE=local
CORTEX_ALLOW_REGISTRATION=true
CORTEX_AUTH_DB=data/auth.sqlite3
~~~

Start the app and choose **Create account**. Enter a username, display name, and a password of 12–128 characters. Save the random recovery code shown after registration in a password manager. The application stores an Argon2id password hash and a recovery-code hash, not the original password or recovery code.

Sign in with your username and password. The account controls provide logout and password change. Forgotten passwords can be reset using the username and recovery code. A successful recovery replaces the code; save the newly displayed one. There is no email reset service. Losing both your password and recovery code means you cannot recover that local account through the app.

Local sessions expire after 12 hours or one hour without an application interaction. A new browser session or page reload may require signing in again; there is no persistent local login cookie. Logout revokes the current session. Password changes and recovery revoke existing sessions. Login, recovery, and password change each allow at most five failed attempts per username in a 15-minute window. These limits are checked when the app handles a request.

To stop additional sign-ups after creating your intended accounts, set `CORTEX_ALLOW_REGISTRATION=false` and restart. Existing users can still sign in.

### Preserve account data

The default database is `data/auth.sqlite3`, relative to the project folder. `CORTEX_AUTH_DB` can point to private persistent storage. The process running the app must have permission to create and write that file and its parent directory.

For a simple backup, stop the app, copy the database to secure storage, and restart. To restore, stop the app, restore the saved file at the configured path, and restart. Protect backups like other account data. Never commit the database, its temporary SQLite files, or real secrets. The `data/` folder and database file patterns are ignored by Git.

Local accounts need a single shared persistent database. Do not rely on Streamlit Community Cloud's local filesystem for durable accounts, or run independent replicas with separate database copies. Use OIDC for that hosting model. Use HTTPS for any publicly hosted deployment.

## Google sign-in on Streamlit Community Cloud

The app uses Streamlit's native OpenID Connect sign-in. You need your own Google client credentials and deployed app URL. Follow Google's registration screens with the values below; the official [Streamlit Google sign-in tutorial](https://docs.streamlit.io/develop/tutorials/authentication/google) explains the provider setup.

1. In [Google Cloud Console](https://console.cloud.google.com/), select or create a project. Open **Google Auth Platform** and configure the application branding and audience. While the application is in testing, add the Google accounts that will test it.
2. Under **Clients**, create a **Web application** client. Register the exact callback URL `https://YOUR-APP.streamlit.app/oauth2callback` as an authorized redirect URI. For local OIDC testing, also register `http://localhost:8501/oauth2callback`.
3. Copy the client ID and client secret into your private configuration. Generate a cookie signing secret on your computer:

~~~powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
~~~

4. In Streamlit **App settings → Secrets** (or local `.streamlit/secrets.toml` for local OIDC testing), enter this configuration. Replace every placeholder:

~~~toml
GEMINI_API_KEY = "your_actual_gemini_key"
GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
CORTEX_AUTH_MODE = "oidc"
# Optional: restrict access to these verified addresses.
# CORTEX_ALLOWED_EMAILS = "you@example.com,collaborator@example.com"

[auth]
redirect_uri = "https://YOUR-APP.streamlit.app/oauth2callback"
cookie_secret = "paste_your_random_cookie_secret_here"
client_id = "paste_your_google_client_id_here"
client_secret = "paste_your_google_client_secret_here"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
~~~

Keep the application settings above `[auth]`; TOML values below that heading belong to the auth section. For local testing, change `redirect_uri` to the exact localhost URL you registered and open the app using that hostname. A `127.0.0.1` URL and a `localhost` URL are different callback addresses.

The default provider is configured directly in `[auth]`. Streamlit requires `redirect_uri`, `cookie_secret`, `client_id`, `client_secret`, and `server_metadata_url`; the callback must match both the host and provider registration. See the [Streamlit login reference](https://docs.streamlit.io/develop/api-reference/user/st.login). Google publishes its discovery URL in its [OpenID Connect documentation](https://developers.google.com/identity/openid-connect/openid-connect).

Cortex requires at least 32 characters for the cookie secret and HTTPS for the provider metadata URL. The callback also requires HTTPS, except for local development at `localhost`, `127.0.0.1`, or `[::1]`, where HTTP is accepted. The random-secret command above meets the length requirement.

5. Save the secrets and restart/deploy the app. Sign in with a registered test account. Confirm that logout clears the workspace and a fresh sign-in starts an empty workspace. Before inviting other users, update the provider audience/publishing settings as required by Google.

Google handles account creation, passwords, and account recovery in this mode. The app never receives the Google password. To use another OIDC provider, supply its client credentials and discovery URL in the same `[auth]` structure.

### Restrict who can use the app

When `CORTEX_ALLOWED_EMAILS` is unset, any user accepted by your configured provider can access the app. For a private deployment, configure a comma-separated allowlist of complete email addresses. Matching is case-insensitive, and the provider must report the email as verified. Invalid nonempty allowlist settings block access until corrected.

Streamlit manages the provider identity cookie and logout. Its identity cookie can last up to 30 days; the local 12-hour/one-hour session policy applies only to local accounts. The app validates the provider identity and any supplied expiry claim on application interactions. See [Streamlit authentication behavior](https://docs.streamlit.io/develop/concepts/connections/authentication).

## Before sharing your deployment

Run the offline tests described in the README. Then complete a real provider sign-in and callback, log out, and verify a Gemini upload/question/summary with your private credentials. Mocked tests cannot verify your provider registration, deployed redirect URL, API key, or available Gemini quota. Keep `.env`, `.streamlit/secrets.toml`, cookie secrets, and account databases outside GitHub.
