# Daily New Client Reports System

This system automatically sends daily email reports containing details of newly created/added clients from the last 24 hours (or specified time period).

## Features

- **Email Recipients Management**: Store and manage email addresses that will receive daily reports
- **Automated Reports**: Generate and send reports with newly created client data from the last 24 hours
- **HTML Email Format**: Beautiful, responsive HTML email with client details
- **CSV Attachment**: Complete client data in CSV format for further analysis
- **Admin Interface**: Easy management through Django admin
- **Flexible Time Periods**: Configure how many days back to look for newly created clients

## Setup

### 1. Email Configuration

Configure your email settings in the `.env` file:

```env
# Email Configuration
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=your-smtp-server.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@domain.com
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

For development/testing, you can use the console backend:
```env
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

### 2. Add Email Recipients

1. Go to Django Admin → Core → Email Recipients
2. Click "Add Email Recipient"
3. Fill in:
   - **Name**: Display name for the recipient
   - **Email**: Email address to receive reports
   - **Is Active**: Check to enable receiving reports
   - **Department**: Optional - restrict to specific department
   - **Notes**: Optional notes about this recipient

### 3. Run the Report Command

#### Manual Execution
```bash
# Send report for newly created clients in last 24 hours to all active recipients
python manage.py send_daily_client_report

# Send report for newly created clients in last 7 days
python manage.py send_daily_client_report --days 7

# Test mode - send to first recipient only
python manage.py send_daily_client_report --test
```

#### Automated Execution (Cron Job)
Add to your crontab to run daily at 8 AM:
```bash
0 8 * * * cd /path/to/your/project && source venv/bin/activate && python manage.py send_daily_client_report
```

## Report Contents

### HTML Email
- **Header**: Report title and date range
- **Summary Cards**: Total new clients added, report date
- **Client Table**: Detailed client information including:
  - Name (with preferred name)
  - Date of Birth and Age
  - Gender
  - Contact Information (Phone, Email)
  - Program and Status
  - Creation timestamp

### CSV Attachment
Complete client data including:
- Client ID, Names, DOB, Age
- Contact Information
- Address Details
- Program Information
- Health Card Information
- Referral Source
- Creation Timestamps

## Email Template

The HTML email template is located at:
`templates/emails/daily_client_report.html`

You can customize the styling and layout by editing this file.

## Management Command Options

- `--test`: Send email to first recipient only (for testing)
- `--days N`: Look back N days for newly created clients (default: 1)

## Database Model

### EmailRecipient
- `email`: Unique email address
- `name`: Display name
- `is_active`: Enable/disable recipient
- `department`: Optional department filter
- `notes`: Additional notes
- `created_at`, `updated_at`: Timestamps

## Troubleshooting

### No Emails Sent
1. Check if there are active email recipients
2. Verify email configuration in settings
3. Check if there are newly created clients in the specified time period

### Email Delivery Issues
1. Verify SMTP settings
2. Check firewall/network restrictions
3. Test with console backend first

### Template Issues
1. Ensure template file exists at correct path
2. Check Django template syntax
3. Verify template context variables

## Security Considerations

- Email credentials should be stored securely in environment variables
- Consider using email service providers (SendGrid, AWS SES) for production
- Implement rate limiting for email sending
- Consider email content filtering for sensitive client data

## Future Enhancements

- Department-specific reports
- Customizable report templates
- Report scheduling options
- Email delivery tracking
- Report analytics and metrics
