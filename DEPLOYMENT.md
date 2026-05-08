# Deployment Guide

This guide walks you through deploying your MCP Browser Agent to production.

## Architecture

- **Backend**: Python FastAPI on Render (free tier available)
- **Frontend**: Next.js on Vercel
- **API Key**: Securely stored on Render, never exposed to frontend

## Step 1: Backend Deployment (Render)

### 1.1 Create a Render Account
- Go to [render.com](https://render.com)
- Sign up with GitHub (recommended) or email

### 1.2 Deploy from Git
1. Click "New +" → "Web Service"
2. Connect your GitHub repository
3. Select your `Browser-MCP-Agent` repo
4. Configure the service:
   - **Name**: `browser-mcp-agent` (or your choice)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free tier is fine

### 1.3 Set Environment Variables on Render
1. In the Render dashboard, go to your service
2. Click "Environment" tab
3. Add these variables:
   - **Key**: `OPENAI_API_KEY`
   - **Value**: Your OpenAI API key (get from https://platform.openai.com/api-keys)
   - **Key**: `ALLOWED_ORIGINS`
   - **Value**: Will be set after Vercel deployment (for now: leave empty or use `*`)

4. Click "Deploy" to start deployment
5. Your backend URL will be something like: `https://browser-mcp-agent.onrender.com`
6. **Copy this URL** - you'll need it for the frontend

## Step 2: Frontend Deployment (Vercel)

### 2.1 Create a Vercel Account
- Go to [vercel.com](https://vercel.com)
- Sign up with GitHub (recommended)

### 2.2 Import and Deploy Project
1. Click "Add New..." → "Project"
2. Select your `Browser-MCP-Agent` repository
3. Vercel should auto-detect it's a Next.js project
4. In "Configure Project":
   - **Root Directory**: `frontend` (or let Vercel auto-detect)
5. Click "Deploy"

### 2.3 Add Environment Variables to Vercel
Before or after deployment:
1. Go to your Vercel project dashboard
2. Click "Settings" → "Environment Variables"
3. Add:
   - **Name**: `NEXT_PUBLIC_API_URL`
   - **Value**: `https://browser-mcp-agent.onrender.com` (or your Render URL from Step 1.6)
   - **Environments**: All (Production, Preview, Development)

4. Trigger a redeployment:
   - Go to "Deployments" tab
   - Click "..." on the latest deployment
   - Select "Redeploy"

Your frontend will be available at: `https://your-project.vercel.app`

## Step 3: Update Backend CORS (Important!)

Once Vercel deployment is complete:
1. Go back to Render dashboard
2. Navigate to your `browser-mcp-agent` service
3. Click "Environment" tab
4. Update `ALLOWED_ORIGINS`:
   - **Value**: `https://your-project.vercel.app,https://yourdomain.com` (if you add a custom domain)

5. Click "Save" to trigger a redeploy

## Step 4: Buy and Configure Custom Domain (Optional)

### 4.1 Buy Domain on Vercel
1. In Vercel dashboard, go to "Settings" → "Domains"
2. Click "Add" → "Purchase New Domain"
3. Search for and purchase your `.com` domain
4. Vercel automatically configures DNS and SSL

### 4.2 Update Backend CORS Again
After setting your custom domain:
1. Return to Render
2. Update `ALLOWED_ORIGINS` to include your custom domain:
   ```
   https://yourdomain.com,https://www.yourdomain.com,https://your-project.vercel.app
   ```

## Step 5: Test Your Deployment

1. Visit your Vercel URL or custom domain
2. Type a command: "Go to Google and search for Python"
3. Click "Run Command"
4. The response should appear within 10-30 seconds (depending on task complexity)

## Troubleshooting

### Frontend not connecting to backend
- Check that `NEXT_PUBLIC_API_URL` is set correctly in Vercel
- Verify backend CORS `ALLOWED_ORIGINS` includes your frontend URL
- Open browser DevTools → Network tab → check for CORS errors

### Backend giving errors
- Go to Render dashboard → Logs tab
- Check for Python import errors or missing environment variables
- Verify `OPENAI_API_KEY` is set and valid

### Slow response times
- Free Render tier spins down after inactivity. First request may take 30+ seconds
- Consider upgrading to paid tier for consistent performance

## Next Steps (After Going Live)

1. **Monitor Usage**: Check OpenAI API usage to track costs
2. **Set Budget Alerts**: Configure OpenAI billing alerts to avoid surprises
3. **Update Domain MX Records**: If you want to add email later
4. **Enable Vercel Analytics**: Optional, for performance monitoring

## Local Development

To test locally before deploying:
```bash
# Terminal 1: Backend
export OPENAI_API_KEY="your-key-here"
cd backend && uvicorn app:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
# Visit http://localhost:3000
```
