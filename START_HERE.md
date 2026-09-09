# Start your Cortex Research AI project

This folder contains the full application, authentication, tests, sample document, and deployment configuration. It contains no working API key or pre-created user account.

## Upload the code to GitHub

1. Extract **Cortex-Research-AI.zip**.
2. Open the extracted **Cortex-Research-AI** folder.
3. Upload its **contents** to the root of your repository. `app.py`, `requirements.txt`, `auth/`, `rag/`, and `utils/` must be at the repository root.
4. Include the hidden folders `.streamlit/` and `.github/`, plus `.gitignore` and `.env.example`.
5. Do not upload a real `.env`, `.streamlit/secrets.toml`, `data/`, or `.venv/`. Uploading only the ZIP does not deploy the app.

## Try it on your computer

Open a terminal in the project folder and run:

~~~powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
~~~

Put your Gemini API key in the new local `.env` file, then run:

~~~powershell
python -m streamlit run app.py
~~~

Choose **Create account** on the welcome screen. Save the recovery code displayed after registration; it is needed if you forget your password. Log in, upload `examples/research-notes.txt`, and choose **Process documents**. A Gemini key and available quota are required for AI processing.

## Put it on Streamlit Community Cloud

Use **Google / OIDC sign-in** for the hosted app. The built-in local accounts use a database file; Community Cloud storage is not a durable place to keep that database.

1. Choose your GitHub repository and branch, set the main file to **app.py**, and select Python **3.12** in Advanced settings.
2. Follow [AUTHENTICATION.md](AUTHENTICATION.md#google-sign-in-on-streamlit-community-cloud) to create your Google sign-in client and set private Streamlit Secrets, including `CORTEX_AUTH_MODE = "oidc"` and `[auth]`.
3. Set your actual Gemini API key in those private Secrets. Use `.streamlit/secrets.toml.example` as the configuration reference.
4. Deploy, make sure the Google callback URL matches your deployed URL, and test sign-in, document processing, a question, and a summary.

For an existing deployment, update GitHub and use **App settings → Secrets**. Account registration and password recovery in Google mode are managed by Google. Local accounts do not transfer to Google mode.

[README.md](README.md) covers supported uploads, local setup, testing, and troubleshooting. [AUTHENTICATION.md](AUTHENTICATION.md) explains account storage and both sign-in modes. [VERIFICATION.md](VERIFICATION.md) records what was tested and what still needs your private credentials.
