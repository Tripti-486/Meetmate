
import os
import json
import asyncio
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
import uvicorn

# Import models and services
from models.schemas import *
from data.db_config import get_db, create_tables
from services.transcription_service import transcription_service
from services.calendar_service import calendar_service
from services.email_service import email_service
from agents.mom_generator import mom_generator
from agents.scheduler import smart_scheduler
from agents.follow_up import follow_up_agent
from config import settings

# Create FastAPI app
app = FastAPI(
    title="MeetMate: Autonomous Meeting Scheduler & Summarizer",
    description="AI-powered meeting management system with smart scheduling and automatic minutes generation",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize database and services on startup."""
    create_tables()
    print("✅ MeetMate API started successfully!")
    print(f"📊 Running in {'DEBUG' if settings.debug else 'PRODUCTION'} mode")

@app.get("/", response_model=APIResponse)
async def read_root():
    """Root endpoint with API information."""
    return APIResponse(
        success=True,
        message="Welcome to MeetMate API! 🎯 Autonomous Meeting Scheduler & Summarizer",
        data={
            "version": "1.0.0",
            "features": [
                "Smart Meeting Scheduling",
                "AI-powered Minutes of Meeting Generation",
                "Action Item Tracking",
                "Automated Follow-ups",
                "Calendar Integration (Google & Outlook)",
                "Email Notifications"
            ],
            "endpoints": {
                "meetings": "/meetings/",
                "transcription": "/transcription/",
                "mom": "/mom/",
                "scheduling": "/scheduling/",
                "action-items": "/action-items/",
                "calendar": "/calendar/",
                "email": "/email/"
            }
        }
    )

@app.get("/health", response_model=APIResponse)
async def health_check():
    """Health check endpoint."""
    # Check service configurations
    email_config = email_service.validate_email_configuration()
    
    return APIResponse(
        success=True,
        message="MeetMate API is healthy",
        data={
            "timestamp": datetime.now().isoformat(),
            "services": {
                "database": "connected",
                "transcription": "available",
                "mom_generator": "available",
                "scheduler": "available",
                "follow_up_agent": "available",
                "email_service": "configured" if email_config['is_configured'] else "not_configured",
                "calendar_service": "available"
            }
        }
    )

# Meeting Endpoints
@app.post("/meetings/", response_model=APIResponse)
async def create_meeting(meeting: MeetingCreate, db: Session = Depends(get_db)):
    """Create a new meeting."""
    try:
        # Import here to avoid circular imports
        from data.db_config import Meeting, User
        
        # Get or create organizer
        organizer = db.query(User).filter(User.email == meeting.organizer_email).first()
        if not organizer:
            organizer = User(email=meeting.organizer_email, name=meeting.organizer_email.split('@')[0])
            db.add(organizer)
            db.commit()
            db.refresh(organizer)
        
        # Create meeting
        db_meeting = Meeting(
            title=meeting.title,
            description=meeting.description,
            start_time=meeting.start_time,
            end_time=meeting.end_time,
            location=meeting.location,
            meeting_link=meeting.meeting_link,
            priority=meeting.priority,
            organizer_id=organizer.id
        )
        
        db.add(db_meeting)
        db.commit()
        db.refresh(db_meeting)
        
        # Add attendees
        for email in meeting.attendee_emails:
            attendee = db.query(User).filter(User.email == email).first()
            if not attendee:
                attendee = User(email=email, name=email.split('@')[0])
                db.add(attendee)
                db.commit()
                db.refresh(attendee)
            
            db_meeting.attendees.append(attendee)
        
        db.commit()
        
        return APIResponse(
            success=True,
            message="Meeting created successfully",
            data={"meeting_id": db_meeting.id, "title": db_meeting.title}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating meeting: {str(e)}")

@app.get("/meetings/", response_model=APIResponse)
async def get_meetings(
    skip: int = 0, 
    limit: int = 100, 
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get list of meetings."""
    try:
        from data.db_config import Meeting
        
        query = db.query(Meeting)
        if status:
            query = query.filter(Meeting.status == status)
        
        meetings = query.offset(skip).limit(limit).all()
        
        meetings_data = []
        for meeting in meetings:
            meetings_data.append({
                "id": meeting.id,
                "title": meeting.title,
                "start_time": meeting.start_time.isoformat(),
                "end_time": meeting.end_time.isoformat(),
                "status": meeting.status,
                "organizer": meeting.organizer.email if meeting.organizer else None,
                "attendee_count": len(meeting.attendees)
            })
        
        return APIResponse(
            success=True,
            message="Meetings retrieved successfully",
            data={"meetings": meetings_data, "count": len(meetings_data)}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving meetings: {str(e)}")

@app.get("/meetings/{meeting_id}", response_model=APIResponse)
async def get_meeting(meeting_id: int, db: Session = Depends(get_db)):
    """Get detailed meeting information."""
    try:
        from data.db_config import Meeting
        
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        meeting_data = {
            "id": meeting.id,
            "title": meeting.title,
            "description": meeting.description,
            "start_time": meeting.start_time.isoformat(),
            "end_time": meeting.end_time.isoformat(),
            "location": meeting.location,
            "meeting_link": meeting.meeting_link,
            "priority": meeting.priority,
            "status": meeting.status,
            "organizer": {
                "email": meeting.organizer.email,
                "name": meeting.organizer.name
            } if meeting.organizer else None,
            "attendees": [
                {"email": attendee.email, "name": attendee.name} 
                for attendee in meeting.attendees
            ],
            "has_transcript": meeting.transcript_path is not None,
            "has_minutes": meeting.minutes is not None,
            "action_items_count": len(meeting.action_items),
            "created_at": meeting.created_at.isoformat()
        }
        
        return APIResponse(
            success=True,
            message="Meeting details retrieved successfully",
            data=meeting_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving meeting: {str(e)}")

# Transcription Endpoints
@app.post("/transcription/upload/{meeting_id}", response_model=APIResponse)
async def upload_audio_for_transcription(
    meeting_id: int,
    file: UploadFile = File(...),
    service: str = "whisper",
    language: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Upload audio file for transcription."""
    try:
        from data.db_config import Meeting
        
        # Verify meeting exists
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Save uploaded file
        file_path = f"{settings.upload_directory}/meeting_{meeting_id}_{file.filename}"
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Start transcription in background
        transcript_result = await transcription_service.transcribe_audio(
            audio_path=file_path,
            service=service,
            language=language
        )
        
        # Save transcript
        transcript_path = f"{settings.temp_directory}/meeting_{meeting_id}_transcript.txt"
        transcription_service.save_transcript_to_file(
            transcript_result, 
            transcript_path,
            include_timestamps=True
        )
        
        # Update meeting record
        meeting.recording_path = file_path
        meeting.transcript_path = transcript_path
        db.commit()
        
        # Save transcription to database
        from data.db_config import Transcription
        db_transcription = Transcription(
            meeting_id=meeting_id,
            content=transcript_result['text'],
            language=transcript_result.get('language', 'unknown'),
            confidence_score=transcript_result.get('confidence_score'),
            audio_file_path=file_path,
            processing_time=transcript_result.get('processing_time', 0)
        )
        db.add(db_transcription)
        db.commit()
        
        return APIResponse(
            success=True,
            message="Audio transcribed successfully",
            data={
                "meeting_id": meeting_id,
                "transcript_preview": transcript_result['text'][:200] + "...",
                "language": transcript_result.get('language'),
                "processing_time": transcript_result.get('processing_time'),
                "service_used": service,
                "transcript_path": transcript_path
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing audio: {str(e)}")

@app.get("/transcription/{meeting_id}", response_model=APIResponse)
async def get_transcription(meeting_id: int, db: Session = Depends(get_db)):
    """Get transcription for a meeting."""
    try:
        from data.db_config import Transcription
        
        transcription = db.query(Transcription).filter(Transcription.meeting_id == meeting_id).first()
        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        return APIResponse(
            success=True,
            message="Transcription retrieved successfully",
            data={
                "meeting_id": meeting_id,
                "content": transcription.content,
                "language": transcription.language,
                "confidence_score": transcription.confidence_score,
                "processing_time": transcription.processing_time,
                "created_at": transcription.created_at.isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving transcription: {str(e)}")

# MoM Generation Endpoints
@app.post("/mom/generate/{meeting_id}", response_model=APIResponse)
async def generate_mom(
    meeting_id: int,
    extract_detailed_action_items: bool = True,
    db: Session = Depends(get_db)
):
    """Generate Minutes of Meeting from transcription."""
    try:
        from data.db_config import Meeting, Transcription, MinutesOfMeeting, ActionItem, User
        
        # Get meeting and transcription
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        transcription = db.query(Transcription).filter(Transcription.meeting_id == meeting_id).first()
        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found for this meeting")
        
        # Generate MoM using AI
        mom_data = await mom_generator.generate_mom(
            transcript=transcription.content,
            meeting_title=meeting.title,
            meeting_date=meeting.start_time.date().isoformat(),
            duration=int((meeting.end_time - meeting.start_time).total_seconds() / 60),
            extract_detailed_action_items=extract_detailed_action_items
        )
        
        # Save MoM to database
        db_mom = MinutesOfMeeting(
            meeting_id=meeting_id,
            summary=mom_data['summary'],
            key_decisions=json.dumps(mom_data['key_decisions']),
            discussion_points=json.dumps(mom_data['discussion_points']),
            next_meeting_date=datetime.fromisoformat(mom_data['next_meeting_info']) if mom_data.get('next_meeting_info') else None
        )
        db.add(db_mom)
        db.commit()
        db.refresh(db_mom)
        
        # Save action items
        for item_data in mom_data['action_items']:
            # Find or create assignee
            assignee_email = item_data['assignee']
            if '@' in assignee_email:
                assignee = db.query(User).filter(User.email == assignee_email).first()
                if not assignee:
                    assignee = User(email=assignee_email, name=assignee_email.split('@')[0])
                    db.add(assignee)
                    db.commit()
                    db.refresh(assignee)
                
                action_item = ActionItem(
                    meeting_id=meeting_id,
                    title=item_data['title'],
                    description=item_data['description'],
                    assignee_id=assignee.id,
                    due_date=datetime.strptime(item_data['due_date'], '%Y-%m-%d').date() if item_data.get('due_date') else None,
                    priority=item_data['priority']
                )
                db.add(action_item)
        
        db.commit()
        
        return APIResponse(
            success=True,
            message="Minutes of Meeting generated successfully",
            data={
                "mom_id": db_mom.id,
                "meeting_id": meeting_id,
                "summary": mom_data['summary'],
                "key_decisions_count": len(mom_data['key_decisions']),
                "action_items_count": len(mom_data['action_items']),
                "participants_identified": len(mom_data['participants'])
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating MoM: {str(e)}")

@app.get("/mom/{meeting_id}", response_model=APIResponse)
async def get_mom(meeting_id: int, db: Session = Depends(get_db)):
    """Get Minutes of Meeting for a specific meeting."""
    try:
        from data.db_config import MinutesOfMeeting
        
        mom = db.query(MinutesOfMeeting).filter(MinutesOfMeeting.meeting_id == meeting_id).first()
        if not mom:
            raise HTTPException(status_code=404, detail="Minutes of Meeting not found")
        
        return APIResponse(
            success=True,
            message="Minutes of Meeting retrieved successfully",
            data={
                "id": mom.id,
                "meeting_id": meeting_id,
                "summary": mom.summary,
                "key_decisions": mom.key_decisions_list,
                "discussion_points": mom.discussion_points_list,
                "next_meeting_date": mom.next_meeting_date.isoformat() if mom.next_meeting_date else None,
                "created_at": mom.created_at.isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving MoM: {str(e)}")

# Smart Scheduling Endpoints
@app.post("/scheduling/analyze", response_model=APIResponse)
async def analyze_meeting_request(request: ScheduleRequest):
    """Analyze meeting request and provide AI-powered scheduling recommendations."""
    try:
        recommendations = await smart_scheduler.get_intelligent_recommendations(
            title=request.title,
            attendees=request.attendee_emails,
            duration_minutes=request.duration,
            description=request.description or "",
            organizer_notes="",
            calendar_providers=None  # Could be passed as parameter
        )
        
        return APIResponse(
            success=recommendations['success'],
            message="Meeting analysis completed",
            data=recommendations
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing meeting request: {str(e)}")

@app.post("/scheduling/smart-schedule", response_model=APIResponse)
async def smart_schedule_meeting(
    request: ScheduleRequest,
    auto_confirm: bool = False,
    db: Session = Depends(get_db)
):
    """Schedule meeting using AI-powered intelligent recommendations."""
    try:
        # Use smart scheduler
        result = await smart_scheduler.schedule_intelligent_meeting(
            title=request.title,
            attendees=request.attendee_emails,
            duration_minutes=request.duration,
            description=request.description or "",
            location="",
            organizer_notes="",
            calendar_providers=None,
            auto_confirm=auto_confirm
        )
        
        if result['success'] and auto_confirm:
            # Create meeting record in database
            from data.db_config import Meeting, User
            
            # Get or create organizer (assuming first attendee is organizer)
            organizer_email = request.attendee_emails[0] if request.attendee_emails else "unknown@example.com"
            organizer = db.query(User).filter(User.email == organizer_email).first()
            if not organizer:
                organizer = User(email=organizer_email, name=organizer_email.split('@')[0])
                db.add(organizer)
                db.commit()
                db.refresh(organizer)
            
            # Create meeting
            scheduled_slot = result['scheduled_slot']
            db_meeting = Meeting(
                title=request.title,
                description=request.description or "",
                start_time=scheduled_slot['start_time'],
                end_time=scheduled_slot['end_time'],
                priority=request.priority,
                organizer_id=organizer.id,
                calendar_event_id=str(result.get('calendar_events', {}))
            )
            
            db.add(db_meeting)
            db.commit()
            db.refresh(db_meeting)
            
            result['database_meeting_id'] = db_meeting.id
        
        return APIResponse(
            success=result['success'],
            message=result['message'],
            data=result
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scheduling meeting: {str(e)}")

@app.get("/scheduling/availability", response_model=APIResponse)
async def check_availability(
    attendees: List[str],
    start_date: str,
    end_date: str,
    duration: int = 60
):
    """Check availability for multiple attendees."""
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        
        availability = await calendar_service.get_availability(
            attendee_emails=attendees,
            start_date=start_dt,
            end_date=end_dt
        )
        
        available_slots = calendar_service.find_available_slots(
            availability=availability,
            start_date=start_dt,
            end_date=end_dt,
            duration_minutes=duration
        )
        
        return APIResponse(
            success=True,
            message="Availability checked successfully",
            data={
                "attendees": attendees,
                "availability_conflicts": availability,
                "available_slots": [
                    {
                        "start_time": slot['start_time'].isoformat(),
                        "end_time": slot['end_time'].isoformat(),
                        "duration_minutes": slot['duration_minutes']
                    } for slot in available_slots[:10]  # Return top 10
                ],
                "total_slots_found": len(available_slots)
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking availability: {str(e)}")

# Action Items Endpoints
@app.get("/action-items/", response_model=APIResponse)
async def get_action_items(
    status: Optional[str] = None,
    assignee_email: Optional[str] = None,
    priority: Optional[str] = None,
    overdue_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get action items with filtering options."""
    try:
        from data.db_config import ActionItem, User
        
        query = db.query(ActionItem)
        
        if status:
            query = query.filter(ActionItem.status == status)
        
        if priority:
            query = query.filter(ActionItem.priority == priority)
        
        if assignee_email:
            user = db.query(User).filter(User.email == assignee_email).first()
            if user:
                query = query.filter(ActionItem.assignee_id == user.id)
        
        if overdue_only:
            query = query.filter(ActionItem.due_date < date.today())
        
        action_items = query.all()
        
        items_data = []
        for item in action_items:
            items_data.append({
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "assignee": {
                    "email": item.assignee.email,
                    "name": item.assignee.name
                } if item.assignee else None,
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "priority": item.priority,
                "status": item.status,
                "meeting_title": item.meeting.title if item.meeting else None,
                "is_overdue": item.due_date < date.today() if item.due_date else False,
                "created_at": item.created_at.isoformat()
            })
        
        return APIResponse(
            success=True,
            message="Action items retrieved successfully",
            data={"action_items": items_data, "count": len(items_data)}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving action items: {str(e)}")

@app.put("/action-items/{item_id}", response_model=APIResponse)
async def update_action_item(
    item_id: int,
    update_data: ActionItemUpdate,
    db: Session = Depends(get_db)
):
    """Update action item status and details."""
    try:
        from data.db_config import ActionItem
        
        action_item = db.query(ActionItem).filter(ActionItem.id == item_id).first()
        if not action_item:
            raise HTTPException(status_code=404, detail="Action item not found")
        
        # Update fields
        action_item.status = update_data.status
        if update_data.status == "completed":
            action_item.completed_at = datetime.now()
        
        db.commit()
        
        return APIResponse(
            success=True,
            message="Action item updated successfully",
            data={"item_id": item_id, "new_status": update_data.status}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating action item: {str(e)}")

# Follow-up and Reminder Endpoints
@app.post("/follow-up/process-daily", response_model=APIResponse)
async def process_daily_follow_ups(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Process daily follow-ups for all action items."""
    try:
        # Run in background to avoid timeout
        background_tasks.add_task(follow_up_agent.process_daily_follow_ups, db)
        
        return APIResponse(
            success=True,
            message="Daily follow-up processing started in background",
            data={"status": "processing", "timestamp": datetime.now().isoformat()}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting follow-up processing: {str(e)}")

@app.get("/follow-up/report", response_model=APIResponse)
async def get_follow_up_report(db: Session = Depends(get_db)):
    """Generate comprehensive follow-up report."""
    try:
        report = await follow_up_agent.generate_follow_up_report(db)
        
        return APIResponse(
            success=True,
            message="Follow-up report generated successfully",
            data=report
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating follow-up report: {str(e)}")

@app.post("/follow-up/send-reminder/{item_id}", response_model=APIResponse)
async def send_manual_reminder(
    item_id: int,
    custom_message: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Send manual reminder for specific action item."""
    try:
        from data.db_config import ActionItem
        
        action_item = db.query(ActionItem).filter(ActionItem.id == item_id).first()
        if not action_item:
            raise HTTPException(status_code=404, detail="Action item not found")
        
        # Convert to dict format expected by follow-up agent
        item_dict = {
            "id": action_item.id,
            "title": action_item.title,
            "description": action_item.description,
            "assignee": action_item.assignee.email if action_item.assignee else "unknown",
            "due_date": action_item.due_date.isoformat() if action_item.due_date else None,
            "priority": action_item.priority
        }
        
        meeting_dict = {
            "meeting_metadata": {
                "title": action_item.meeting.title if action_item.meeting else "Unknown Meeting",
                "date": action_item.created_at.date().isoformat()
            }
        }
        
        success = await email_service.send_action_item_reminder(
            action_item=item_dict,
            meeting_data=meeting_dict,
            custom_message=custom_message
        )
        
        return APIResponse(
            success=success,
            message="Reminder sent successfully" if success else "Failed to send reminder",
            data={"item_id": item_id, "reminder_sent": success}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending reminder: {str(e)}")

# Email Endpoints
@app.post("/email/send-mom/{meeting_id}", response_model=APIResponse)
async def send_mom_email(
    meeting_id: int,
    request: MoMEmailRequest,
    db: Session = Depends(get_db)
):
    """Send Minutes of Meeting via email."""
    try:
        from data.db_config import Meeting, MinutesOfMeeting, ActionItem
        
        # Get meeting and MoM data
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        mom = db.query(MinutesOfMeeting).filter(MinutesOfMeeting.meeting_id == meeting_id).first()
        if not mom:
            raise HTTPException(status_code=404, detail="Minutes of Meeting not found")
        
        # Prepare email data
        meeting_data = {
            "meeting_metadata": {
                "title": meeting.title,
                "date": meeting.start_time.date().isoformat(),
                "duration": int((meeting.end_time - meeting.start_time).total_seconds() / 60)
            },
            "summary": mom.summary,
            "key_decisions": mom.key_decisions_list,
            "discussion_points": mom.discussion_points_list,
            "participants": [attendee.email for attendee in meeting.attendees],
            "next_meeting_info": mom.next_meeting_date.isoformat() if mom.next_meeting_date else None
        }
        
        # Add action items if requested
        if request.include_action_items:
            action_items = db.query(ActionItem).filter(ActionItem.meeting_id == meeting_id).all()
            meeting_data["action_items"] = [
                {
                    "title": item.title,
                    "description": item.description,
                    "assignee": item.assignee.email if item.assignee else "Unknown",
                    "due_date": item.due_date.isoformat() if item.due_date else None,
                    "priority": item.priority
                } for item in action_items
            ]
        
        # Determine recipients
        recipients = request.recipients or [attendee.email for attendee in meeting.attendees]
        
        # Send email
        success = await email_service.send_mom_email(
            meeting_data=meeting_data,
            recipients=recipients,
            include_attachments=True
        )
        
        return APIResponse(
            success=success,
            message="MoM email sent successfully" if success else "Failed to send MoM email",
            data={
                "meeting_id": meeting_id,
                "recipients": recipients,
                "email_sent": success
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending MoM email: {str(e)}")

# Statistics and Analytics Endpoints
@app.get("/analytics/dashboard", response_model=APIResponse)
async def get_dashboard_analytics(db: Session = Depends(get_db)):
    """Get dashboard analytics and statistics."""
    try:
        from data.db_config import Meeting, ActionItem
        from sqlalchemy import func
        
        # Meeting statistics
        total_meetings = db.query(Meeting).count()
        completed_meetings = db.query(Meeting).filter(Meeting.status == "completed").count()
        
        # Action item statistics
        total_action_items = db.query(ActionItem).count()
        completed_action_items = db.query(ActionItem).filter(ActionItem.status == "completed").count()
        overdue_action_items = db.query(ActionItem).filter(
            ActionItem.due_date < date.today(),
            ActionItem.status != "completed"
        ).count()
        
        # Recent activity
        recent_meetings = db.query(Meeting).order_by(Meeting.created_at.desc()).limit(5).all()
        recent_action_items = db.query(ActionItem).order_by(ActionItem.created_at.desc()).limit(5).all()
        
        return APIResponse(
            success=True,
            message="Dashboard analytics retrieved successfully",
            data={
                "meetings": {
                    "total": total_meetings,
                    "completed": completed_meetings,
                    "completion_rate": (completed_meetings / total_meetings * 100) if total_meetings > 0 else 0
                },
                "action_items": {
                    "total": total_action_items,
                    "completed": completed_action_items,
                    "overdue": overdue_action_items,
                    "completion_rate": (completed_action_items / total_action_items * 100) if total_action_items > 0 else 0
                },
                "recent_activity": {
                    "meetings": [
                        {
                            "id": m.id,
                            "title": m.title,
                            "date": m.start_time.date().isoformat(),
                            "status": m.status
                        } for m in recent_meetings
                    ],
                    "action_items": [
                        {
                            "id": a.id,
                            "title": a.title,
                            "assignee": a.assignee.email if a.assignee else "Unknown",
                            "status": a.status,
                            "priority": a.priority
                        } for a in recent_action_items
                    ]
                },
                "generated_at": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving analytics: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
