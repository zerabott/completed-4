# Render Deployment Guide for Telegram Confession Bot

This guide will help you deploy your Telegram Confession Bot on Render with PostgreSQL database support.

## Prerequisites

1. **Render Account**: Sign up at [render.com](https://render.com)
2. **GitHub Repository**: Your bot code should be in a GitHub repository
3. **Telegram Bot Token**: From @BotFather
4. **Channel ID**: Your Telegram channel ID
5. **Admin IDs**: Your admin user IDs

## Step-by-Step Deployment

### 1. Prepare Your Repository

Make sure your GitHub repository contains all the updated files:
- `requirements.txt` (with PostgreSQL support)
- `render.yaml` (with database configuration)
- `bot_web.py` (with database migration setup)
- All your bot files including the new database modules

### 2. Create Database Service First

1. **Log into Render Dashboard**
2. **Click "New +" → "PostgreSQL"**
3. **Configure Database:**
   - **Name**: `confession-bot-db`
   - **Database**: `confession_bot` (or any name you prefer)
   - **User**: `confession_user` (or any username)
   - **Region**: Choose closest to your users
   - **Plan**: Free (or paid for better performance)
   
4. **Click "Create Database"**
5. **Wait for database to be ready** (takes 2-3 minutes)
6. **Note down the connection details** (you'll see them in the dashboard)

### 3. Deploy the Web Service

1. **Click "New +" → "Web Service"**
2. **Connect your GitHub repository**
3. **Configure Web Service:**
   
   **Basic Settings:**
   - **Name**: `telegram-confession-bot`
   - **Region**: Same as your database
   - **Branch**: `main` (or your default branch)
   - **Root Directory**: Leave empty if bot is in repo root
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot_web.py`

   **Environment Variables:**
   Add all these environment variables in the Render dashboard:

   ```
   BOT_TOKEN=your_bot_token_from_botfather
   CHANNEL_ID=your_channel_id (with minus sign, e.g., -1001234567890)
   BOT_USERNAME=@yourbotusername
   ADMIN_ID_1=your_first_admin_user_id
   ADMIN_ID_2=your_second_admin_user_id (optional)
   USE_POSTGRESQL=true
   PORT=10000
   ```

   **Database Connection Variables:**
   Render will automatically provide these from your database:
   - `DATABASE_URL` → Set to your database's "External Connection String"
   - `PGHOST` → Your database host
   - `PGPORT` → Your database port (usually 5432)
   - `PGDATABASE` → Your database name
   - `PGUSER` → Your database username
   - `PGPASSWORD` → Your database password

4. **Advanced Settings:**
   - **Auto-Deploy**: Yes
   - **Plan**: Free (or paid for better performance)

5. **Click "Create Web Service"**

### 4. Alternative: Deploy Using render.yaml (Recommended)

If you want to deploy both database and web service together:

1. **Push the included `render.yaml` to your repository**
2. **In Render dashboard, click "New +" → "Blueprint"**
3. **Connect your GitHub repository**
4. **Render will automatically:**
   - Create the PostgreSQL database
   - Create the web service
   - Set up all connections automatically

### 5. Configure Environment Variables

In the Render dashboard, go to your web service and add these environment variables:

```env
BOT_TOKEN=8462429667:AAFbUVgvhnrdM7Wyj96j44uTSEVlWWQIncs
CHANNEL_ID=-1002715898008
BOT_USERNAME=@confessiontesterbot
ADMIN_ID_1=1298849354
ADMIN_ID_2=7085119805
USE_POSTGRESQL=true
```

**Important**: Replace these with your actual bot credentials!

### 6. Monitor Deployment

1. **Check the logs** in your Render dashboard
2. **Look for these success messages:**
   ```
   🗄️ Setting up database...
   ✅ Database setup completed
   🚀 Starting Telegram bot subprocess...
   🌐 Starting web server on 0.0.0.0:10000
   ```

3. **Test your bot** by sending `/start` to it

## Database Migration

The bot will automatically run database migrations on startup:

1. **Create all necessary tables** (users, posts, comments, etc.)
2. **Add media support columns**
3. **Add analytics columns**
4. **Create PostgreSQL indexes** for better performance

## Troubleshooting

### Common Issues:

1. **"ModuleNotFoundError: No module named 'psycopg2'"**
   - Make sure `psycopg2-binary>=2.9.0` is in `requirements.txt`

2. **Database connection errors**
   - Verify all PostgreSQL environment variables are set correctly
   - Check that the database is running and accessible

3. **Bot not responding**
   - Check the logs for errors
   - Verify bot token and channel ID are correct
   - Make sure the bot is added as admin to your channel

4. **"Port already in use" errors**
   - This is normal during restarts, Render will handle it

### Checking Logs:

1. **In Render dashboard** → Your web service → Logs tab
2. **Look for error messages** and check the troubleshooting section
3. **Database logs** can be found in your PostgreSQL service

### Health Checks:

Your bot exposes health check endpoints:
- `https://your-app-url.onrender.com/` - Basic health check
- `https://your-app-url.onrender.com/health` - Detailed status
- `https://your-app-url.onrender.com/ping` - Simple ping

## Data Persistence

With PostgreSQL on Render:
- **Data is persistent** across restarts
- **Automatic backups** are available (paid plans)
- **Connection pooling** for better performance
- **ACID compliance** for data integrity

## Cost Considerations

**Free Tier Limitations:**
- Database: 1GB storage, shared CPU
- Web Service: 750 hours/month, sleeps after 15 minutes of inactivity
- No custom domains on free tier

**Paid Plans Benefits:**
- Always-on services (no sleeping)
- Better performance
- More storage
- Custom domains
- Automatic backups

## Security Notes

1. **Never commit** `.env` files with real credentials
2. **Use Render environment variables** for all sensitive data
3. **Regularly rotate** your bot token if compromised
4. **Monitor access logs** in Render dashboard

## Next Steps

After successful deployment:
1. **Test all bot features** thoroughly
2. **Set up monitoring** and alerts
3. **Configure backups** if on paid plan
4. **Update your Telegram channel** with the new bot
5. **Monitor database performance** and optimize as needed

## Support

- **Render Documentation**: https://render.com/docs
- **PostgreSQL Docs**: https://www.postgresql.org/docs/
- **Telegram Bot API**: https://core.telegram.org/bots/api

Your bot should now be running 24/7 on Render with persistent PostgreSQL database storage!
