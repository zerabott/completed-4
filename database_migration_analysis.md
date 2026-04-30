# Database Migration Analysis - SQLite to PostgreSQL

## Current Status
- **Local Environment**: Using SQLite (no PostgreSQL environment variables set)
- **Production Environment**: Should use PostgreSQL on Render with Aiven
- **Database Abstraction**: Available via `db_connection.py` but not used by all files

## Files Already Fixed ✅
- `comments.py` - Updated to use proper database abstraction

## Critical Files Needing Update (HIGH PRIORITY) 🔴

### Core Functionality
1. **`bot.py`** - Main bot file with 9+ database connections
2. **`db.py`** - Database utility functions (6 connections)
3. **`submission.py`** - Post submission handling (13 connections)
4. **`approval.py`** - Post approval system (8 connections)

### User Management
5. **`user_experience.py`** - User interaction handling (19 connections)
6. **`stats.py`** - User statistics (2 connections)

### Admin Functions
7. **`admin_tools.py`** - Administrative functions (22 connections)
8. **`admin_messaging.py`** - Admin messaging system (7 connections)
9. **`moderation.py`** - Content moderation (7 connections)

### Notifications
10. **`notifications.py`** - Notification system (15 connections)
11. **`notification_ui.py`** - Notification UI (2 connections)

## Medium Priority Files 🟡

### Analytics & Reporting
- `analytics.py` - Analytics system (8 connections)
- `trending.py` - Trending content (6 connections)
- `performance.py` - Performance monitoring (4 connections)

### Enhanced Features
- `enhanced_ranking_system.py` - Ranking system (2 connections)
- `enhanced_ranking_ui.py` - Ranking UI (1 connection)
- `enhanced_leaderboard.py` - Leaderboard (6 connections)
- `enhanced_moderation.py` - Enhanced moderation (2 connections)
- `ranking_integration.py` - Ranking integration (6 connections)
- `rank_ladder.py` - Rank ladder (1 connection)

### Content Management
- `content_moderation.py` - Content moderation (1 connection)

## Low Priority / Utility Files 🟢

### Migration & Setup
- `migrations.py` - Database migrations (4 connections)
- `backup_system.py` - Backup system (4 connections)
- `deploy_setup.py` - Deployment setup (1 connection)

### Development/Testing Files
- `check_*.py` files - Database schema checking
- `fix_migration.py` - Migration fixes

## Database Configuration Issues

### Missing Environment Variables
The following environment variables need to be set for PostgreSQL on Render:
```
USE_POSTGRESQL=true
DATABASE_URL=postgresql://user:password@host:port/database
# OR individual variables:
PGHOST=your-aiven-host
PGPORT=5432
PGDATABASE=your-database-name
PGUSER=your-username
PGPASSWORD=your-password
```

## Recommended Migration Strategy

### Phase 1: Critical Core Files
1. Update `db.py` first (utilities used by other files)
2. Update `bot.py` (main application)
3. Update `submission.py` and `approval.py` (core post functionality)
4. Update `user_experience.py` (user interactions)

### Phase 2: Admin & Management
1. Update admin files (`admin_tools.py`, `admin_messaging.py`, `moderation.py`)
2. Update notification system
3. Update stats and analytics

### Phase 3: Enhanced Features
1. Update ranking and leaderboard systems
2. Update enhanced moderation features
3. Update performance monitoring

### Phase 4: Utilities & Maintenance
1. Update migration and backup systems
2. Clean up development/testing files

## Pattern for Updates

Each file needs to be updated to:
1. Replace `import sqlite3` with database abstraction imports
2. Replace `sqlite3.connect(DB_PATH)` with `get_db_connection()`
3. Use proper placeholder syntax (`db_conn.get_placeholder()`)
4. Handle PostgreSQL-specific syntax (RETURNING clauses, etc.)
5. Use proper connection context management

## Deployment Checklist

- [ ] Set PostgreSQL environment variables on Render
- [ ] Update all critical files (Phase 1)
- [ ] Test database connectivity
- [ ] Deploy to staging environment
- [ ] Run database migrations if needed
- [ ] Deploy to production
- [ ] Monitor for errors
