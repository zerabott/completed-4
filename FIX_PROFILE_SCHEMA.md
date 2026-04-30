# 🔧 Fix: Profile "gender" Column Missing Error

## 🚨 Problem
Your bot crashes with this error when clicking "My Profile":
```
column "gender" does not exist
LINE 1: ...ECT user_id, display_name, emoji, bio, is_active, gender, ag...
```

## 🔍 Root Cause
The `user_profiles` table in your Render PostgreSQL database is **missing the extended profile columns** (gender, age, department, year, religion, relationship_status, other_info).

This happened because there were **two conflicting CREATE TABLE statements** in `db.py` that created the table without these columns.

## ✅ Solution

### Step 1: Update Your Code (Already Fixed)
The code has been fixed in these files:
- ✅ `db.py` - Both CREATE TABLE statements now include all extended fields
- ✅ `migrate_profile_fields.py` - New migration script created

### Step 2: Run the Migration on Render

You have **two options** to fix your production database:

---

#### **Option A: Run Migration via Render Shell (Recommended)**

1. **Go to your Render Dashboard**
   - Navigate to your web service
   - Click on the **"Shell"** tab

2. **Run the migration script**
   ```bash
   python migrate_profile_fields.py
   ```

3. **Verify the output**
   You should see:
   ```
   ✅ Added/verified column 'gender' to user_profiles
   ✅ Added/verified column 'age' to user_profiles
   ✅ Added/verified column 'department' to user_profiles
   ✅ Added/verified column 'year' to user_profiles
   ✅ Added/verified column 'religion' to user_profiles
   ✅ Added/verified column 'relationship_status' to user_profiles
   ✅ Added/verified column 'other_info' to user_profiles
   ✅ Migration completed successfully!
   ```

4. **Restart your service** (optional)
   - The migration takes effect immediately
   - But you can restart to be safe

---

#### **Option B: Push to GitHub and Redeploy**

If you prefer to trigger the migration automatically:

1. **Commit and push the changes**
   ```bash
   git add .
   git commit -m "Fix: Add missing profile schema columns"
   git push origin main
   ```

2. **On Render, add a build command** (if not already there)
   - Go to your service settings
   - Under "Build Command", add:
   ```bash
   pip install -r requirements.txt && python migrate_profile_fields.py
   ```
   
   OR create a simple one-time manual deploy script

3. **Deploy**
   - Render will automatically deploy the new code
   - The migration will run during build

---

#### **Option C: Manual SQL (Advanced)**

If you're comfortable with SQL, you can run this directly in Render's PostgreSQL:

1. Go to Render Dashboard → PostgreSQL database
2. Click "Connect" and use the PSQL shell
3. Run these commands:

```sql
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS gender TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS age INTEGER;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS department TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS year TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS religion TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS relationship_status TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS other_info TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

4. Verify:
```sql
\d user_profiles
```

---

## 🎯 What's Fixed

### Files Modified:
1. **`db.py`**
   - Fixed both CREATE TABLE statements for `user_profiles`
   - Both now include all 7 extended fields
   - Added `created_at` and `updated_at` timestamps
   - Made `emoji` column optional (was NOT NULL)

2. **`migrate_profile_fields.py`** (NEW)
   - Standalone migration script
   - Adds missing columns safely
   - Works with both PostgreSQL and SQLite
   - Includes verification step

### Schema Changes:
```sql
user_profiles table now has:
✅ user_id (PRIMARY KEY)
✅ display_name
✅ emoji
✅ bio
✅ is_active
✅ gender             ← ADDED
✅ age                ← ADDED
✅ department         ← ADDED
✅ year               ← ADDED
✅ religion           ← ADDED
✅ relationship_status ← ADDED
✅ other_info         ← ADDED
✅ created_at         ← ADDED
✅ updated_at         ← ADDED
```

---

## 🚀 After Migration

1. **Test the profile feature**
   - Click "👤 My Profile" button
   - Should work without errors
   - All edit options should function

2. **Commit the fixed code**
   ```bash
   git add db.py migrate_profile_fields.py FIX_PROFILE_SCHEMA.md
   git commit -m "Fix: Profile schema missing extended fields"
   git push origin main
   ```

3. **Future deployments**
   - The fixed `db.py` ensures new databases have correct schema
   - The migration script is idempotent (safe to run multiple times)

---

## 📝 Notes

- The migration script uses `IF NOT EXISTS` so it's safe to run multiple times
- No data will be lost - only new columns are added
- Existing profiles will have NULL/empty values for new fields
- Users can fill in these fields by editing their profile

---

## ❓ If You Still See Errors

1. **Check the column exists**:
   ```bash
   # In Render Shell
   python -c "from db_connection import get_db_connection; conn = get_db_connection().get_connection(); cursor = conn.cursor(); cursor.execute('SELECT column_name FROM information_schema.columns WHERE table_name = \\'user_profiles\\''); print([row[0] for row in cursor.fetchall()])"
   ```

2. **Check Render logs**:
   - Go to Render Dashboard
   - Click on "Logs" tab
   - Look for migration output

3. **Restart the service**:
   - Sometimes Render caches the old schema
   - Manual restart can help

---

## ✅ Success Checklist

- [ ] Code changes committed to GitHub
- [ ] Migration script executed successfully
- [ ] "My Profile" button works without errors
- [ ] Can edit profile fields (gender, age, etc.)
- [ ] All extended fields save correctly
- [ ] No database errors in Render logs

---

**Need help? Check the Render logs or run the migration script again!**
