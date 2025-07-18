# OAuth Setup Guide for Bioforklift Dashboard

This guide explains how to set up Google OAuth authentication for the Bioforklift Dashboard.

## Prerequisites

1. A Google Cloud Project with BigQuery access
2. Access to Google Cloud Console
3. The dashboard deployed or ready to deploy

## Step 1: Create OAuth Credentials

### 1.1 Navigate to Google Cloud Console
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Select your project or create a new one
3. Navigate to **APIs & Services** → **Credentials**

### 1.2 Configure OAuth Consent Screen
1. Click **OAuth consent screen** in the sidebar
2. Choose **Internal** (for organization use) or **External** (for public use)
3. Fill in the required information:
   - **App name**: `Bioforklift Dashboard`
   - **User support email**: Your email
   - **App logo**: Optional
   - **App domain**: Your dashboard domain
   - **Developer contact information**: Your email
4. Click **Save and Continue**
5. Add scopes (click **Add or Remove Scopes**):
   - `openid`
   - `email`
   - `profile`
   - `https://www.googleapis.com/auth/cloud-platform.read-only`
6. Click **Save and Continue**
7. Review and submit

### 1.3 Create OAuth Client ID
1. Click **Credentials** in the sidebar
2. Click **+ Create Credentials** → **OAuth 2.0 Client IDs**
3. Choose **Web application**
4. Configure the client:
   - **Name**: `Bioforklift Dashboard`
   - **Authorized JavaScript origins**: 
     - `http://localhost:8000` (for local development)
     - `https://your-dashboard-domain.com` (for production)
   - **Authorized redirect URIs**:
     - `http://localhost:8000/auth/callback` (for local development)
     - `https://your-dashboard-domain.com/auth/callback` (for production)
5. Click **Create**
6. **Save the Client ID and Client Secret** - you'll need these for environment variables

## Step 2: Configure Environment Variables

### 2.1 Copy the Example Environment File
```bash
cd /Users/michalbabinski/bioforklift/dashboard/backend
cp .env.example .env
```

### 2.2 Update Environment Variables
Edit the `.env` file with your values:

```bash
# OAuth Configuration
GOOGLE_CLIENT_ID=your-actual-client-id-here
GOOGLE_CLIENT_SECRET=your-actual-client-secret-here
SECRET_KEY=generate-a-long-random-string-here

# GCP Project Configuration
TARGET_PROJECT_ID=your-target-gcp-project
DATASET_ID=your-bigquery-dataset

# Application Configuration
ENVIRONMENT=production
FRONTEND_URL=http://localhost:5173  # Update for production
```

### 2.3 Generate a Secret Key
For the `SECRET_KEY`, generate a secure random string:

```bash
# Option 1: Using Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Option 2: Using OpenSSL
openssl rand -base64 32

# Option 3: Using online generator
# Visit: https://generate-random.org/api-key-generator
```

## Step 3: Set Up IAM Permissions

### 3.1 Grant BigQuery Access
Users need appropriate IAM roles on your GCP project:

**Minimum Required Roles:**
- `BigQuery Data Viewer` on the specific dataset
- OR `BigQuery User` on the project
- OR `Project Viewer` on the project

**Recommended Role Assignment:**
```bash
# Grant BigQuery Data Viewer on specific dataset
gcloud projects add-iam-policy-binding PROJECT_ID \
    --member="user:user@company.com" \
    --role="roles/bigquery.dataViewer" \
    --condition="expression=resource.name.startsWith('projects/PROJECT_ID/datasets/DATASET_ID')"

# OR grant BigQuery User on entire project (more permissive)
gcloud projects add-iam-policy-binding PROJECT_ID \
    --member="user:user@company.com" \
    --role="roles/bigquery.user"
```

### 3.2 Test Access
Users can test their access with:
```bash
# List datasets
bq ls --project_id=PROJECT_ID

# Query the specific dataset
bq query --use_legacy_sql=false "SELECT COUNT(*) FROM \`PROJECT_ID.DATASET_ID.samples\` LIMIT 1"
```

## Step 4: Deploy and Test

### 4.1 Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Visit `http://localhost:8000` and test the OAuth flow.

### 4.2 Production Deployment (Cloud Run)

#### Build and Push Container
```bash
# Build the container
gcloud builds submit --tag gcr.io/PROJECT_ID/bioforklift-dashboard

# Deploy to Cloud Run
gcloud run deploy bioforklift-dashboard \
    --image gcr.io/PROJECT_ID/bioforklift-dashboard \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars="TARGET_PROJECT_ID=your-project,DATASET_ID=samples,ENVIRONMENT=production" \
    --set-secrets="GOOGLE_CLIENT_ID=google-client-id:latest,GOOGLE_CLIENT_SECRET=google-client-secret:latest,SECRET_KEY=session-secret:latest"
```

#### Using Secret Manager (Recommended)
```bash
# Store secrets in Secret Manager
echo -n "your-client-id" | gcloud secrets create google-client-id --data-file=-
echo -n "your-client-secret" | gcloud secrets create google-client-secret --data-file=-
echo -n "your-secret-key" | gcloud secrets create session-secret --data-file=-

# Deploy with secrets
gcloud run deploy bioforklift-dashboard \
    --image gcr.io/PROJECT_ID/bioforklift-dashboard \
    --set-secrets="GOOGLE_CLIENT_ID=google-client-id:latest,GOOGLE_CLIENT_SECRET=google-client-secret:latest,SECRET_KEY=session-secret:latest"
```

## Step 5: Update OAuth Redirect URIs

After deployment, update your OAuth client with the production URL:

1. Go back to Google Cloud Console → APIs & Services → Credentials
2. Click on your OAuth 2.0 Client ID
3. Add the production redirect URI:
   - `https://your-production-domain.com/auth/callback`
4. Save the changes

## Troubleshooting

### Common Issues

**1. "redirect_uri_mismatch" Error**
- Ensure the redirect URI in Google Cloud Console exactly matches your deployment URL
- Check for trailing slashes or protocol mismatches (http vs https)

**2. "Access Denied" After Login**
- Verify the user has appropriate BigQuery permissions
- Check the `TARGET_PROJECT_ID` and `DATASET_ID` environment variables
- Test BigQuery access manually with `bq` command

**3. "Invalid Client" Error**
- Verify `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are correct
- Ensure OAuth consent screen is properly configured

**4. Session Issues**
- Verify `SECRET_KEY` is set and consistent across deployments
- Check that session middleware is properly configured

### Debug Mode

Set `ENVIRONMENT=development` to enable debug logging and relaxed OAuth validation:

```bash
export ENVIRONMENT=development
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Security Considerations

1. **Never commit secrets to version control**
2. **Use HTTPS in production**
3. **Rotate secrets regularly**
4. **Use Secret Manager for production deployments**
5. **Restrict OAuth redirect URIs to your domains only**
6. **Regularly review IAM permissions**

## Testing the Implementation

1. Visit your dashboard URL
2. Click "Sign in with Google"
3. Authenticate with a Google account that has BigQuery access
4. Verify you can access the dashboard and see data
5. Test that users without access get denied appropriately
6. Test the logout functionality

## Next Steps

- Customize the dashboard UI to match your needs
- Add role-based access control if needed
- Integrate with your existing Svelte frontend
- Set up monitoring and alerting for the authentication system