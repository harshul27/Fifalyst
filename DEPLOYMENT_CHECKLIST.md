# ✅ FIFA Shadow Coach Deployment Checklist

**Status: Ready to Deploy**  
**Target: GitHub → Render**  
**Estimated Time: 15-20 minutes**

---

## 🚀 QUICK START (Copy-Paste Ready)

### Step 1️⃣: Create GitHub Repo
- [ ] Go to **[github.com/new](https://github.com/new)**
- [ ] **Name**: `fifa-shadow-coach`
- [ ] **Visibility**: Public
- [ ] Click **Create repository**
- [ ] **Copy the URL** shown (looks like `https://github.com/YOUR_USERNAME/fifa-shadow-coach.git`)

### Step 2️⃣: Push Code from Local

Open terminal/CLI in your `fifa-shadow-coach` folder and run:

```bash
# Navigate to project
cd ~/Documents/Claude/Projects/fifa-shadow-coach

# Initialize git
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit: FIFA Shadow Coach v3.1"

# Add GitHub remote
git remote add origin https://github.com/YOUR_USERNAME/fifa-shadow-coach.git

# Rename to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

**Expected output:**
```
✓ Enumerating objects...
✓ Counting objects...
✓ Compressing objects...
✓ Writing objects...
✓ Create pull request: https://github.com/YOUR_USERNAME/fifa-shadow-coach/pull/new/main
```

### Step 3️⃣: Verify on GitHub
- [ ] Visit `https://github.com/YOUR_USERNAME/fifa-shadow-coach`
- [ ] Check you see: `app.py`, `src/`, `requirements.txt`, `Dockerfile`, etc.

### Step 4️⃣: Create Render Account
- [ ] Go to **[render.com](https://render.com)**
- [ ] Click **Sign up** → **Continue with GitHub** (easiest!)
- [ ] Authorize Render

### Step 5️⃣: Create Web Service on Render
In Render Dashboard:
- [ ] Click **New +** → **Web Service**
- [ ] Select `fifa-shadow-coach` repo
- [ ] Click **Connect**

### Step 6️⃣: Configure Service Settings

| Setting | Value |
|---------|-------|
| **Name** | `fifa-shadow-coach` |
| **Environment** | Python 3 |
| **Region** | Pick closest to you |
| **Branch** | `main` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn src.main:app --host 0.0.0.0 --port 8000 & streamlit run app.py --server.port 8501 --server.address 0.0.0.0` |
| **Instance** | Free |

- [ ] Click **Create Web Service**

### Step 7️⃣: Add Environment Variables
On Render Dashboard:
- [ ] Go to **Environment** tab
- [ ] Add these:

```
CLAUDE_API_KEY = sk-your-key-here
BACKEND_URL = https://fifa-shadow-coach.onrender.com
LOG_LEVEL = info
```

### Step 8️⃣: Monitor Deployment
- [ ] Watch **Logs** tab
- [ ] Wait for: `Service started successfully` ✓
- [ ] Takes ~2-3 minutes

### Step 9️⃣: Test Live App
- [ ] Visit: `https://fifa-shadow-coach.onrender.com`
- [ ] You should see the Streamlit dashboard

### Step 🔟: Verify Backend
```bash
curl https://fifa-shadow-coach.onrender.com/health
```

Should return:
```json
{"status": "healthy"}
```

---

## 🔄 From Now On

Every time you push code:
```bash
git add .
git commit -m "Update: describe change"
git push origin main
```

Render auto-deploys in ~2-3 minutes. ✓

---

## 🆘 Troubleshooting

| Issue | Fix |
|-------|-----|
| `git push` auth fails | Run `gh auth login` and retry |
| Files not on GitHub | Check `git status`, make sure committed |
| Render can't find repo | Ensure repo is Public, not Private |
| Build fails on Render | Check Render **Logs** tab for error details |
| App loads but errors | Backend URL might be wrong in env vars |

---

## 📊 Deployment Status

```
✅ Code ready
✅ GitHub config ready
✅ Render config ready
⏳ Waiting: Step 1 - Create GitHub repo
⏳ Waiting: Step 2 - Push code
⏳ Waiting: Step 3 - Create Render account
⏳ Waiting: Step 4-10 - Full deployment
```

---

**Ready? Start with Step 1 above! 🎯**

