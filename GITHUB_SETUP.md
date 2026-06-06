# 🔗 Connect GitHub to Claude & Deploy to Render

**Complete guide: GitHub → Claude Code → Render deployment**

---

## 📋 Prerequisites

You need:
- GitHub account (free at github.com)
- Claude Code or Cowork mode
- Your FIFA Shadow Coach project folder

---

## PART 1: Create GitHub Repository

### Step 1.1: Create Repo on GitHub

1. Go to **[github.com/new](https://github.com/new)**
2. Login (or create account if needed)
3. Fill in:
   - **Repository name**: `fifa-shadow-coach`
   - **Description**: `AI-powered football match analytics • Open-source • Free to run`
   - **Visibility**: `Public` (free plan)
   - **Initialize with**: Leave unchecked (we have files already)
4. Click **"Create repository"**

### Step 1.2: Copy Your Repository URL

After creating, you'll see:
```
https://github.com/YOUR_USERNAME/fifa-shadow-coach.git
```

**Save this URL** - you'll need it in next step.

---

## PART 2: Connect Project to GitHub from Claude

### Step 2.1: Open Terminal in Claude Code

```bash
# Navigate to your project
cd ~/Documents/Claude/Projects/fifa-shadow-coach

# Verify you're in right place
ls -la
# Should show: app.py, src/, requirements.txt, etc.
```

### Step 2.2: Initialize Git

```bash
# Check if git already initialized
git status

# If "fatal: not a git repository", run:
git init
```

### Step 2.3: Add All Files

```bash
git add .
git status
# Should show all your files ready to commit
```

### Step 2.4: Create Initial Commit

```bash
git commit -m "Initial commit: FIFA Shadow Coach v3.1 - Open-source football analytics"
```

### Step 2.5: Connect to GitHub

```bash
# Replace YOUR_USERNAME with your actual GitHub username
git remote add origin https://github.com/YOUR_USERNAME/fifa-shadow-coach.git

# Verify connection
git remote -v
# Should show:
# origin  https://github.com/YOUR_USERNAME/fifa-shadow-coach.git (fetch)
# origin  https://github.com/YOUR_USERNAME/fifa-shadow-coach.git (push)
```

### Step 2.6: Rename Branch to Main (if needed)

```bash
git branch -M main
```

### Step 2.7: Push to GitHub

```bash
git push -u origin main
```

**First time?** You may be asked to authenticate:
- Option 1: GitHub Personal Access Token (recommended)
- Option 2: GitHub username + password

### If Authentication Fails:

```bash
# Use GitHub CLI (easiest)
gh auth login

# Follow prompts to authenticate
# Then retry:
git push -u origin main
```

---

## ✅ Verify GitHub Connection

1. Go to **[github.com/YOUR_USERNAME/fifa-shadow-coach](https://github.com/YOUR_USERNAME/fifa-shadow-coach)**
2. You should see all your files:
   - ✅ `app.py`
   - ✅ `src/` folder
   - ✅ `requirements.txt`
   - ✅ `Dockerfile`
   - ✅ `DEPLOY_STEPS.md`
   - ✅ etc.

3. If you see them → **Success!** ✅

---

## PART 3: Connect Claude Code to GitHub

### Step 3.1: Enable Git Integration in Claude Code

If using Claude Code:

```bash
# Configure git user (if not already done)
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"

# Verify
git config --global user.name
git config --global user.email
```

### Step 3.2: Make Changes and Push from Claude

Now whenever you make changes:

```bash
# See what changed
git status

# Stage changes
git add .

# Commit
git commit -m "Update: describe your change"

# Push to GitHub
git push origin main
```

### Step 3.3: (Optional) Set Up Auto-Push

For easier workflow, you can add a Git hook:

```bash
# Create hook file
mkdir -p .git/hooks

cat > .git/hooks/post-commit << 'HOOK'
#!/bin/bash
git push origin main 2>/dev/null || true
HOOK

chmod +x .git/hooks/post-commit
```

Now every commit auto-pushes!

---

## PART 4: Connect Render to GitHub

### Step 4.1: Create Render Account

1. Go to **[render.com](https://render.com)**
2. Click **"Sign up"**
3. Choose **"Continue with GitHub"** (easiest!)
4. Authorize Render to access your GitHub

### Step 4.2: Create Web Service

In Render Dashboard:

1. Click **"New +"** → **"Web Service"**
2. Select **`fifa-shadow-coach`** from your repos
3. Click **"Connect"**

### Step 4.3: Configure Service

Fill in the form:

| Field | Value |
|-------|-------|
| **Name** | `fifa-shadow-coach` |
| **Environment** | `Python 3` |
| **Region** | Pick closest to you |
| **Branch** | `main` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn src.main:app --host 0.0.0.0 --port 8000 & streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --logger.level=info` |
| **Instance Type** | `Free` |

### Step 4.4: Add Environment Variables

After creation, click **"Environment"** tab and add:

```
CLAUDE_API_KEY = sk-your-key-here (optional)
BACKEND_URL = https://fifa-shadow-coach.onrender.com
LOG_LEVEL = info
```

### Step 4.5: Deploy!

Render will automatically:
1. Start building (2-3 minutes)
2. Install dependencies
3. Start your app
4. Make it live!

Watch the **Logs** tab for progress.

---

## ✅ Verify Deployment

Once Render says "Service started successfully":

```bash
# Test health endpoint
curl https://fifa-shadow-coach.onrender.com/health

# Or in browser
https://fifa-shadow-coach.onrender.com
```

---

## 🔄 The Workflow (From Now On)

```
You make changes in Claude Code
        ↓
git add . && git commit -m "..."
        ↓
git push origin main
        ↓
GitHub webhook notifies Render
        ↓
Render auto-rebuilds and deploys
        ↓
Your changes are live!
```

**Total deployment time: ~3 minutes**

---

## 🐛 Troubleshooting

### "Authentication failed"

```bash
# Use GitHub CLI
gh auth login

# Then retry
git push origin main
```

### "Files not showing on GitHub"

```bash
# Verify they were committed
git log

# If not committed:
git add .
git commit -m "Add missing files"
git push origin main
```

### "Render won't find the repo"

- Make sure repo is Public (not Private)
- Make sure you authorized Render to access GitHub
- Try reconnecting: Render Dashboard → Settings → Git Provider

### "Build fails on Render"

- Check **Logs** tab on Render
- Common issues:
  - Missing `requirements.txt` ❌
  - Wrong Start Command ❌
  - Missing environment variables ❌

---

## 📚 Your Deployment Chain

```
GitHub Repo
    ↓ (Webhook)
Render CI/CD
    ↓ (Build & Deploy)
Live App
    ↓ (Every push auto-deploys)
Always Up-to-Date
```

---

## 🎯 Checklist

- [ ] Created GitHub repo
- [ ] Pushed FIFA Shadow Coach code
- [ ] Created Render account
- [ ] Connected GitHub to Render
- [ ] Configured build/start commands
- [ ] Set environment variables
- [ ] Deployment successful
- [ ] App is live at https://your-url.onrender.com

---

## 🎉 You're Connected!

Your setup:
- ✅ Local code → Claude Code
- ✅ Code changes → GitHub
- ✅ GitHub updates → Auto-deploy to Render
- ✅ Live app always in sync

**Next**: Make a change locally, push it, and watch it deploy automatically! 🚀

