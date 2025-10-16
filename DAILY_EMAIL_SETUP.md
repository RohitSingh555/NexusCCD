# Daily Email Report Setup Guide

## 📧 Email Format

The daily email now follows your requested format:

**Subject:** `Daily Client Report - [Date]`

**Content:**
```
Here are the list of clients which are added [Date] for today.

Total new clients added: [Number]

📎 Attachment: A CSV file containing detailed information for all [Number] clients created today is attached to this email.

Client Names Added Today:
- [Client Name 1]
- [Client Name 2]
- [etc...]
```

## ⏰ Daily Scheduling at 11 PM

### 1. Cron Job Setup

To set up the daily email at 11 PM, run these commands:

```bash
# Add the cron job
crontab -e

# Add this line to run daily at 11 PM:
0 23 * * * /home/agilemorph/Desktop/fredvictor/NexusCCD/scripts/send_daily_report.sh
```

### 2. Manual Setup Commands

```bash
# Make the script executable (already done)
chmod +x /home/agilemorph/Desktop/fredvictor/NexusCCD/scripts/send_daily_report.sh

# Add to crontab
echo "0 23 * * * /home/agilemorph/Desktop/fredvictor/NexusCCD/scripts/send_daily_report.sh" | crontab -

# Verify the cron job was added
crontab -l
```

### 3. Cron Job Details

- **Time:** `0 23 * * *` = Every day at 11:00 PM
- **Script:** `/home/agilemorph/Desktop/fredvictor/NexusCCD/scripts/send_daily_report.sh`
- **Logs:** Stored in `/home/agilemorph/Desktop/fredvictor/NexusCCD/logs/daily_report.log`

## 📁 Files Created/Modified

### 1. Email Template
- **File:** `templates/emails/daily_client_report.html`
- **Status:** ✅ Updated to simple format
- **Features:** Clean, simple design with date and client list

### 2. Management Command
- **File:** `core/management/commands/send_daily_client_report.py`
- **Status:** ✅ Updated subject line
- **Usage:** `python manage.py send_daily_client_report --frequency daily`

### 3. Shell Script
- **File:** `scripts/send_daily_report.sh`
- **Status:** ✅ Created and executable
- **Purpose:** Automated daily execution

### 4. Cron Configuration
- **File:** `cron_daily_report.txt`
- **Status:** ✅ Ready to add to crontab
- **Schedule:** Daily at 11 PM

## 🧪 Testing

### Manual Test
```bash
# Test the email format
python manage.py send_daily_client_report --frequency daily --test

# Test the shell script
./scripts/send_daily_report.sh
```

### Email Preview
The email template has been tested and shows:
- ✅ Simple format with date
- ✅ Client count and names
- ✅ CSV attachment notification
- ✅ Clean, professional styling

## 📋 Setup Checklist

- [x] Email template updated to simple format
- [x] Email subject updated
- [x] Shell script created and executable
- [x] Cron job configuration ready
- [x] Logs directory created
- [x] Email format tested and verified

## 🚀 Next Steps

1. **Add the cron job:**
   ```bash
   crontab -e
   # Add: 0 23 * * * /home/agilemorph/Desktop/fredvictor/NexusCCD/scripts/send_daily_report.sh
   ```

2. **Test the setup:**
   ```bash
   # Test manually first
   ./scripts/send_daily_report.sh
   
   # Check logs
   tail -f logs/daily_report.log
   ```

3. **Monitor the system:**
   - Check logs daily
   - Verify emails are being sent
   - Monitor CSV attachments

## 📧 Email Configuration

The system uses Gmail SMTP with these settings:
- **Host:** smtp.gmail.com
- **Port:** 587 (TLS)
- **From:** agilemorphsolutions@gmail.com
- **Credentials:** Stored in `.env` file

## 🔧 Troubleshooting

### If emails don't send:
1. Check database connection
2. Verify Gmail SMTP credentials
3. Check cron job logs: `tail -f logs/daily_report.log`
4. Test manually: `./scripts/send_daily_report.sh`

### If cron job doesn't run:
1. Verify cron service is running: `systemctl status cron`
2. Check crontab: `crontab -l`
3. Check system logs: `journalctl -u cron`

## 📊 Email Features

- **Simple Format:** Clean, easy-to-read email
- **Date Display:** Shows the exact date clients were added
- **Client List:** Names of all new clients
- **CSV Attachment:** Detailed client data in spreadsheet format
- **Professional Styling:** Clean HTML design
- **Mobile Responsive:** Works on all devices
