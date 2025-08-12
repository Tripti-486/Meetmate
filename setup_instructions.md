# 🎯 MeetMate: Autonomous Meeting Scheduler & Summarizer

## Overview

MeetMate is an AI-powered meeting management system that combines smart scheduling with automatic minutes generation. It provides:

- **Smart Meeting Scheduling**: AI-powered conflict detection and optimal time slot recommendations
- **AI-powered Minutes of Meeting Generation**: Automatic transcription and intelligent summarization
- **Action Item Tracking**: Automated follow-ups and reminder system
- **Calendar Integration**: Works with Google Calendar and Outlook
- **Email Notifications**: Professional HTML email templates for all communications

## 🏗️ Architecture

```
MeetMate/
├── main.py                 # FastAPI application with all endpoints
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
│
├── agents/                 # AI Agents
│   ├── mom_generator.py   # Minutes of Meeting generator
│   ├── scheduler.py       # Smart scheduling agent
│   └── follow_up.py       # Action item follow-up agent
│
├── services/              # Core Services
│   ├── transcription_service.py  # Audio transcription (Whisper/AssemblyAI)
│   ├── calendar_service.py       # Calendar integration
│   ├── email_service.py          # Email notifications
│   └── pdf_service.py           # PDF generation
│
├── models/                # Data Models
│   └── schemas.py         # Pydantic models
│
├── data/                  # Database
│   └── db_config.py       # SQLAlchemy models and database config
│
└── credentials/           # API credentials (create this directory)
    ├── google_calendar.json
    └── google_token.json
```

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Clone or create the project directory
cd MeetMate-ai

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the project root:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Google Calendar API (optional)
GOOGLE_CALENDAR_CREDENTIALS_PATH=credentials/google_calendar.json
GOOGLE_CALENDAR_TOKEN_PATH=credentials/google_token.json

# Microsoft Graph API (optional)
MICROSOFT_CLIENT_ID=your_microsoft_client_id
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret
MICROSOFT_TENANT_ID=your_microsoft_tenant_id

# AssemblyAI (optional - alternative to Whisper)
ASSEMBLYAI_API_KEY=your_assemblyai_api_key

# Database Configuration
DATABASE_URL=sqlite:///./meetmate.db

# Email Configuration (for notifications)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_FROM=your_email@gmail.com

# Application Settings
DEBUG=True
SECRET_KEY=your_secret_key_here
```

### 3. API Key Setup

#### Required: OpenAI API Key
1. Visit [OpenAI API](https://platform.openai.com/api-keys)
2. Create an API key
3. Add it to your `.env` file as `OPENAI_API_KEY`

#### Optional: Google Calendar Integration
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project or select existing one
3. Enable Google Calendar API
4. Create credentials (OAuth 2.0 Client ID)
5. Download the JSON file and save as `credentials/google_calendar.json`

#### Optional: AssemblyAI (Enhanced Transcription)
1. Visit [AssemblyAI](https://www.assemblyai.com/)
2. Sign up and get API key
3. Add to `.env` as `ASSEMBLYAI_API_KEY`

### 4. Run the Application

```bash
# Start the FastAPI server
python main.py

# Or use uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **Main API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## 📋 Core Features Usage

### 1. Meeting Transcription & MoM Generation

```bash
# 1. Create a meeting
curl -X POST "http://localhost:8000/meetings/" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Team Standup",
    "description": "Daily team synchronization",
    "start_time": "2024-01-15T09:00:00",
    "end_time": "2024-01-15T10:00:00",
    "organizer_email": "organizer@company.com",
    "attendee_emails": ["alice@company.com", "bob@company.com"]
  }'

# 2. Upload audio for transcription
curl -X POST "http://localhost:8000/transcription/upload/1" \
  -F "file=@meeting_audio.mp3" \
  -F "service=whisper"

# 3. Generate Minutes of Meeting
curl -X POST "http://localhost:8000/mom/generate/1"

# 4. Send MoM via email
curl -X POST "http://localhost:8000/email/send-mom/1" \
  -H "Content-Type: application/json" \
  -d '{
    "meeting_id": 1,
    "recipients": ["team@company.com"],
    "include_action_items": true
  }'
```

### 2. Smart Meeting Scheduling

```bash
# Get AI-powered scheduling recommendations
curl -X POST "http://localhost:8000/scheduling/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Project Review Meeting",
    "description": "Quarterly project review with stakeholders",
    "attendee_emails": ["alice@company.com", "bob@company.com", "carol@company.com"],
    "duration": 90,
    "priority": "high"
  }'

# Auto-schedule meeting with AI recommendations
curl -X POST "http://localhost:8000/scheduling/smart-schedule" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Project Review Meeting",
    "attendee_emails": ["alice@company.com", "bob@company.com"],
    "duration": 60,
    "auto_schedule": true
  }'
```

### 3. Action Item Management

```bash
# Get all action items
curl "http://localhost:8000/action-items/"

# Get overdue action items only
curl "http://localhost:8000/action-items/?overdue_only=true"

# Update action item status
curl -X PUT "http://localhost:8000/action-items/1" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "completed"
  }'

# Send manual reminder
curl -X POST "http://localhost:8000/follow-up/send-reminder/1" \
  -H "Content-Type: application/json" \
  -d '{
    "custom_message": "This is urgent - please complete ASAP"
  }'
```

### 4. Follow-up Reports and Analytics

```bash
# Generate follow-up report
curl "http://localhost:8000/follow-up/report"

# Get dashboard analytics
curl "http://localhost:8000/analytics/dashboard"

# Process daily follow-ups (background task)
curl -X POST "http://localhost:8000/follow-up/process-daily"
```

## 🎨 API Endpoints Reference

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API information and available endpoints |
| `/health` | GET | Health check and service status |
| `/docs` | GET | Interactive API documentation |

### Meeting Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/meetings/` | POST | Create new meeting |
| `/meetings/` | GET | List meetings with filtering |
| `/meetings/{id}` | GET | Get detailed meeting information |

### Transcription & MoM

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/transcription/upload/{meeting_id}` | POST | Upload audio for transcription |
| `/transcription/{meeting_id}` | GET | Get transcription text |
| `/mom/generate/{meeting_id}` | POST | Generate Minutes of Meeting |
| `/mom/{meeting_id}` | GET | Get generated MoM |

### Smart Scheduling

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/scheduling/analyze` | POST | AI analysis of meeting request |
| `/scheduling/smart-schedule` | POST | Auto-schedule with AI recommendations |
| `/scheduling/availability` | GET | Check attendee availability |

### Action Items & Follow-up

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/action-items/` | GET | List action items with filtering |
| `/action-items/{id}` | PUT | Update action item |
| `/follow-up/process-daily` | POST | Process daily follow-ups |
| `/follow-up/report` | GET | Generate follow-up report |
| `/follow-up/send-reminder/{id}` | POST | Send manual reminder |

### Email & Communication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/email/send-mom/{meeting_id}` | POST | Send MoM via email |

### Analytics

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/analytics/dashboard` | GET | Dashboard statistics |

## 🔧 Configuration Options

### Transcription Services

- **Whisper (Default)**: Local processing, supports multiple languages
- **AssemblyAI**: Cloud-based, better accuracy for English, speaker diarization

### Calendar Integration

- **Google Calendar**: OAuth 2.0 authentication required
- **Microsoft Outlook**: Microsoft Graph API credentials required

### Email Configuration

Supports any SMTP server. For Gmail:
1. Enable 2-factor authentication
2. Generate an app-specific password
3. Use the app password in EMAIL_PASSWORD

## 🚨 Troubleshooting

### Common Issues

1. **OpenAI API Errors**
   - Check API key validity
   - Verify sufficient credits
   - Check rate limits

2. **Transcription Failures**
   - Ensure audio file format is supported
   - Check file size limits
   - Verify audio quality

3. **Calendar Integration Issues**
   - Verify credentials file exists
   - Check OAuth permissions
   - Ensure calendar API is enabled

4. **Email Not Sending**
   - Verify SMTP settings
   - Check firewall/antivirus blocking
   - Test email credentials

### Performance Optimization

1. **For Large Audio Files**
   - Use AssemblyAI for better performance
   - Consider audio compression
   - Process in background

2. **For Many Users**
   - Use PostgreSQL instead of SQLite
   - Implement Redis for caching
   - Scale with multiple workers

## 🔒 Security Considerations

1. **API Keys**: Store securely in environment variables
2. **Database**: Use strong passwords and encryption
3. **CORS**: Configure allowed origins for production
4. **Rate Limiting**: Implement for production use
5. **Authentication**: Add user authentication for multi-tenant use

## 🐳 Docker Deployment (Optional)

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'
services:
  meetmate:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./uploads:/app/uploads
      - ./exports:/app/exports
```

Run with:
```bash
docker-compose up --build
```

## 📈 Scaling for Production

1. **Database**: Switch to PostgreSQL
2. **Message Queue**: Add Celery for background tasks
3. **Load Balancer**: Use nginx for multiple instances
4. **Monitoring**: Add logging and monitoring
5. **Caching**: Implement Redis for session management

## 📞 Support

For issues and questions:
1. Check the troubleshooting section
2. Review API documentation at `/docs`
3. Check logs for detailed error messages

---

🎉 **Congratulations!** You now have a fully functional AI-powered meeting management system. MeetMate will help streamline your meeting workflows with intelligent scheduling and automatic documentation. 