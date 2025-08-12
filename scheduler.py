import asyncio
from datetime import datetime, timedelta, time
from typing import List, Dict, Any, Optional, Tuple
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import json
import logging
from services.calendar_service import calendar_service
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for structured output
class MeetingPriority(BaseModel):
    level: str = Field(description="Priority level: low, medium, high, urgent")
    reasoning: str = Field(description="Explanation for the priority level")
    urgency_score: int = Field(description="Urgency score from 1-10")

class TimePreference(BaseModel):
    preferred_date: Optional[str] = Field(description="Preferred date in YYYY-MM-DD format")
    preferred_time: Optional[str] = Field(description="Preferred time in HH:MM format")
    flexible_hours: List[int] = Field(description="List of acceptable hours (0-23)")
    avoid_times: List[str] = Field(description="Times to avoid in HH:MM format")

class SchedulingRecommendation(BaseModel):
    recommended_slot: Dict[str, Any] = Field(description="Best recommended time slot")
    confidence_score: float = Field(description="Confidence in recommendation (0-1)")
    reasoning: str = Field(description="Explanation for the recommendation")
    alternative_reasons: List[str] = Field(description="Reasons why other slots were not chosen")

class SmartSchedulerAgent:
    """AI-powered intelligent meeting scheduler with conflict detection and optimization."""
    
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key not configured")
        
        self.llm = ChatOpenAI(
            model="gpt-4-turbo-preview",
            temperature=0.2,
            openai_api_key=settings.openai_api_key
        )
        
        self.calendar_service = calendar_service
    
    def _create_priority_analysis_prompt(self) -> ChatPromptTemplate:
        """Create prompt for analyzing meeting priority and urgency."""
        
        system_message = """You are an expert meeting scheduler who analyzes meeting requests to determine priority and urgency.

Analyze the meeting details and classify the priority level based on:
1. Keywords indicating urgency (urgent, emergency, ASAP, critical, immediate)
2. Meeting type (client meeting, interview, deadline review, casual sync)
3. Number of attendees and their roles
4. Business impact potential
5. Time sensitivity from description

Priority Levels:
- urgent: Immediate action required, high business impact, contains urgent keywords
- high: Important business meeting, client-facing, interview, deadline-related
- medium: Regular team meetings, project updates, planning sessions
- low: Social meetings, optional sync-ups, informal discussions

{format_instructions}"""

        human_message = """Analyze this meeting request and determine its priority:

MEETING TITLE: {title}
DESCRIPTION: {description}
ATTENDEES: {attendees}
REQUESTED BY: {organizer}
PREFERRED DATE: {preferred_date}

Classify the priority level and provide reasoning."""

        return ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_message),
            HumanMessagePromptTemplate.from_template(human_message)
        ])
    
    def _create_time_preference_prompt(self) -> ChatPromptTemplate:
        """Create prompt for extracting time preferences from meeting requests."""
        
        system_message = """You are an expert at extracting time preferences from meeting requests.

Extract and interpret:
1. Explicit date/time mentions
2. Relative time references (next week, tomorrow, end of month)
3. Time constraints (morning only, after 2pm, before lunch)
4. Timezone preferences
5. Days of week preferences
6. Times to avoid

Convert relative dates to absolute dates based on today's date: {today_date}

{format_instructions}"""

        human_message = """Extract time preferences from this meeting request:

TITLE: {title}
DESCRIPTION: {description}
ORGANIZER MESSAGE: {organizer_notes}

Today is {today_date}. Extract any time preferences mentioned."""

        return ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_message),
            HumanMessagePromptTemplate.from_template(human_message)
        ])
    
    def _create_scheduling_recommendation_prompt(self) -> ChatPromptTemplate:
        """Create prompt for AI-driven scheduling recommendations."""
        
        system_message = """You are an expert meeting scheduler who provides optimal scheduling recommendations.

Consider these factors when recommending meeting times:
1. Attendee availability and conflicts
2. Meeting priority level
3. Time zone considerations
4. Business hours and cultural norms
5. Meeting duration and buffer time needs
6. Attendee productivity patterns
7. Previous meeting history

Provide reasoning for your recommendation and explain why other options were not selected.

{format_instructions}"""

        human_message = """Recommend the best meeting time from available slots:

MEETING DETAILS:
Title: {title}
Priority: {priority}
Duration: {duration} minutes
Attendees: {attendees}

AVAILABLE SLOTS:
{available_slots}

ATTENDEE AVAILABILITY ANALYSIS:
{availability_analysis}

TIME PREFERENCES:
{time_preferences}

Recommend the optimal slot with detailed reasoning."""

        return ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_message),
            HumanMessagePromptTemplate.from_template(human_message)
        ])
    
    async def analyze_meeting_priority(
        self,
        title: str,
        description: str = "",
        attendees: List[str] = None,
        organizer: str = "",
        preferred_date: str = ""
    ) -> Dict[str, Any]:
        """Analyze meeting priority using AI."""
        try:
            if not attendees:
                attendees = []
            
            parser = PydanticOutputParser(pydantic_object=MeetingPriority)
            prompt = self._create_priority_analysis_prompt()
            
            formatted_prompt = prompt.format_messages(
                title=title,
                description=description,
                attendees=", ".join(attendees),
                organizer=organizer,
                preferred_date=preferred_date,
                format_instructions=parser.get_format_instructions()
            )
            
            response = await self.llm.agenerate([formatted_prompt])
            priority_text = response.generations[0][0].text
            
            priority_data = parser.parse(priority_text)
            
            return {
                'level': priority_data.level,
                'reasoning': priority_data.reasoning,
                'urgency_score': priority_data.urgency_score
            }
            
        except Exception as e:
            logger.error(f"Error analyzing meeting priority: {str(e)}")
            # Fallback to simple heuristics
            return self._fallback_priority_analysis(title, description)
    
    def _fallback_priority_analysis(self, title: str, description: str) -> Dict[str, Any]:
        """Fallback priority analysis using simple heuristics."""
        urgent_keywords = ['urgent', 'emergency', 'asap', 'critical', 'immediate', 'crisis']
        high_keywords = ['client', 'interview', 'deadline', 'review', 'demo', 'presentation']
        
        text = f"{title} {description}".lower()
        
        if any(keyword in text for keyword in urgent_keywords):
            return {'level': 'urgent', 'reasoning': 'Contains urgent keywords', 'urgency_score': 9}
        elif any(keyword in text for keyword in high_keywords):
            return {'level': 'high', 'reasoning': 'Important business meeting', 'urgency_score': 7}
        else:
            return {'level': 'medium', 'reasoning': 'Standard meeting', 'urgency_score': 5}
    
    async def extract_time_preferences(
        self,
        title: str,
        description: str = "",
        organizer_notes: str = ""
    ) -> Dict[str, Any]:
        """Extract time preferences from meeting request using AI."""
        try:
            parser = PydanticOutputParser(pydantic_object=TimePreference)
            prompt = self._create_time_preference_prompt()
            
            today = datetime.now().strftime("%Y-%m-%d")
            
            formatted_prompt = prompt.format_messages(
                title=title,
                description=description,
                organizer_notes=organizer_notes,
                today_date=today,
                format_instructions=parser.get_format_instructions()
            )
            
            response = await self.llm.agenerate([formatted_prompt])
            preferences_text = response.generations[0][0].text
            
            preferences_data = parser.parse(preferences_text)
            
            return {
                'preferred_date': preferences_data.preferred_date,
                'preferred_time': preferences_data.preferred_time,
                'flexible_hours': preferences_data.flexible_hours,
                'avoid_times': preferences_data.avoid_times
            }
            
        except Exception as e:
            logger.error(f"Error extracting time preferences: {str(e)}")
            return {
                'preferred_date': None,
                'preferred_time': None,
                'flexible_hours': list(range(9, 17)),  # Default business hours
                'avoid_times': []
            }
    
    async def get_intelligent_recommendations(
        self,
        title: str,
        attendees: List[str],
        duration_minutes: int = 60,
        description: str = "",
        organizer_notes: str = "",
        calendar_providers: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """Get AI-powered scheduling recommendations."""
        try:
            # Step 1: Analyze meeting priority
            priority_data = await self.analyze_meeting_priority(
                title=title,
                description=description,
                attendees=attendees
            )
            
            # Step 2: Extract time preferences
            time_preferences = await self.extract_time_preferences(
                title=title,
                description=description,
                organizer_notes=organizer_notes
            )
            
            # Step 3: Get availability data
            search_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            search_end = search_start + timedelta(days=14)
            
            if time_preferences['preferred_date']:
                try:
                    preferred_date = datetime.strptime(time_preferences['preferred_date'], "%Y-%m-%d")
                    search_start = preferred_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    search_end = search_start + timedelta(days=7)
                except:
                    pass
            
            availability = await self.calendar_service.get_availability(
                attendees,
                search_start,
                search_end,
                calendar_providers
            )
            
            # Step 4: Find available slots with smart filtering
            available_slots = self.calendar_service.find_available_slots(
                availability,
                search_start,
                search_end,
                duration_minutes,
                settings.buffer_time
            )
            
            # Step 5: Apply AI-based filtering and ranking
            filtered_slots = self._apply_intelligent_filtering(
                available_slots,
                time_preferences,
                priority_data,
                duration_minutes
            )
            
            if not filtered_slots:
                return {
                    'success': False,
                    'message': 'No suitable slots found matching preferences',
                    'priority_analysis': priority_data,
                    'time_preferences': time_preferences,
                    'availability_conflicts': availability
                }
            
            # Step 6: Get AI recommendation for best slot
            recommendation = await self._get_ai_recommendation(
                title=title,
                attendees=attendees,
                duration_minutes=duration_minutes,
                available_slots=filtered_slots[:5],  # Top 5 slots
                priority_data=priority_data,
                time_preferences=time_preferences,
                availability=availability
            )
            
            return {
                'success': True,
                'recommended_slot': recommendation['recommended_slot'],
                'confidence_score': recommendation['confidence_score'],
                'reasoning': recommendation['reasoning'],
                'alternative_slots': filtered_slots[1:5],
                'priority_analysis': priority_data,
                'time_preferences': time_preferences,
                'total_slots_analyzed': len(available_slots),
                'filtered_slots_count': len(filtered_slots)
            }
            
        except Exception as e:
            logger.error(f"Error getting intelligent recommendations: {str(e)}")
            raise
    
    def _apply_intelligent_filtering(
        self,
        available_slots: List[Dict[str, Any]],
        time_preferences: Dict[str, Any],
        priority_data: Dict[str, Any],
        duration_minutes: int
    ) -> List[Dict[str, Any]]:
        """Apply intelligent filtering to available slots."""
        filtered_slots = []
        
        for slot in available_slots:
            start_time = slot['start_time']
            score = 100  # Start with perfect score
            
            # Filter by flexible hours
            if time_preferences['flexible_hours']:
                if start_time.hour not in time_preferences['flexible_hours']:
                    continue  # Skip this slot entirely
            
            # Avoid specified times
            if time_preferences['avoid_times']:
                slot_time = start_time.strftime("%H:%M")
                if slot_time in time_preferences['avoid_times']:
                    continue  # Skip this slot entirely
            
            # Score based on time preferences
            if time_preferences['preferred_time']:
                try:
                    preferred_hour = int(time_preferences['preferred_time'].split(':')[0])
                    hour_diff = abs(start_time.hour - preferred_hour)
                    score -= hour_diff * 5  # Penalty for time difference
                except:
                    pass
            
            # Score based on day of week (prefer Tuesday-Thursday for important meetings)
            weekday = start_time.weekday()
            if priority_data['urgency_score'] >= 7:  # High priority meetings
                if weekday in [1, 2, 3]:  # Tuesday-Thursday
                    score += 10
                elif weekday in [0, 4]:  # Monday, Friday
                    score -= 5
                else:  # Weekend
                    score -= 20
            
            # Score based on time of day for productivity
            hour = start_time.hour
            if 9 <= hour <= 11:  # Morning peak
                score += 15
            elif 14 <= hour <= 16:  # Afternoon productive hours
                score += 10
            elif hour < 9 or hour > 17:  # Outside business hours
                score -= 20
            elif 12 <= hour <= 13:  # Lunch time
                score -= 10
            
            # Bonus for longer meetings in morning
            if duration_minutes >= 90 and 9 <= hour <= 11:
                score += 20
            
            # Score based on priority urgency
            if priority_data['urgency_score'] >= 8:  # Very urgent
                # Prefer earlier slots for urgent meetings
                days_from_now = (start_time.date() - datetime.now().date()).days
                score -= days_from_now * 10
            
            slot['ai_score'] = max(0, score)
            filtered_slots.append(slot)
        
        # Sort by AI score (highest first)
        filtered_slots.sort(key=lambda x: x['ai_score'], reverse=True)
        
        return filtered_slots
    
    async def _get_ai_recommendation(
        self,
        title: str,
        attendees: List[str],
        duration_minutes: int,
        available_slots: List[Dict[str, Any]],
        priority_data: Dict[str, Any],
        time_preferences: Dict[str, Any],
        availability: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """Get AI-powered recommendation for the best slot."""
        try:
            parser = PydanticOutputParser(pydantic_object=SchedulingRecommendation)
            prompt = self._create_scheduling_recommendation_prompt()
            
            # Format available slots for AI analysis
            slots_text = ""
            for i, slot in enumerate(available_slots):
                slots_text += f"Slot {i+1}: {slot['start_time'].strftime('%Y-%m-%d %H:%M')} - {slot['end_time'].strftime('%H:%M')} (Score: {slot.get('ai_score', 0)})\n"
            
            # Analyze availability conflicts
            conflicts_summary = ""
            for email, events in availability.items():
                conflicts_summary += f"{email}: {len(events)} existing meetings\n"
            
            formatted_prompt = prompt.format_messages(
                title=title,
                priority=f"{priority_data['level']} (score: {priority_data['urgency_score']})",
                duration=duration_minutes,
                attendees=", ".join(attendees),
                available_slots=slots_text,
                availability_analysis=conflicts_summary,
                time_preferences=json.dumps(time_preferences, indent=2),
                format_instructions=parser.get_format_instructions()
            )
            
            response = await self.llm.agenerate([formatted_prompt])
            recommendation_text = response.generations[0][0].text
            
            recommendation_data = parser.parse(recommendation_text)
            
            # Find the actual slot object
            recommended_slot = available_slots[0]  # Default to first slot
            for slot in available_slots:
                slot_time_str = slot['start_time'].strftime('%Y-%m-%d %H:%M')
                if slot_time_str in str(recommendation_data.recommended_slot):
                    recommended_slot = slot
                    break
            
            return {
                'recommended_slot': recommended_slot,
                'confidence_score': recommendation_data.confidence_score,
                'reasoning': recommendation_data.reasoning,
                'alternative_reasons': recommendation_data.alternative_reasons
            }
            
        except Exception as e:
            logger.error(f"Error getting AI recommendation: {str(e)}")
            # Fallback to highest scored slot
            return {
                'recommended_slot': available_slots[0],
                'confidence_score': 0.7,
                'reasoning': 'Highest scoring slot based on heuristics',
                'alternative_reasons': ['AI analysis failed, using fallback scoring']
            }
    
    async def schedule_intelligent_meeting(
        self,
        title: str,
        attendees: List[str],
        duration_minutes: int = 60,
        description: str = "",
        location: str = "",
        organizer_notes: str = "",
        calendar_providers: Dict[str, str] = None,
        auto_confirm: bool = False
    ) -> Dict[str, Any]:
        """Schedule a meeting using intelligent AI-powered recommendations."""
        try:
            # Get intelligent recommendations
            recommendations = await self.get_intelligent_recommendations(
                title=title,
                attendees=attendees,
                duration_minutes=duration_minutes,
                description=description,
                organizer_notes=organizer_notes,
                calendar_providers=calendar_providers
            )
            
            if not recommendations['success']:
                return recommendations
            
            recommended_slot = recommendations['recommended_slot']
            
            if auto_confirm:
                # Schedule the meeting automatically
                scheduling_result = await self.calendar_service.schedule_meeting(
                    title=title,
                    attendee_emails=attendees,
                    duration_minutes=duration_minutes,
                    description=f"{description}\n\nScheduled by AI Assistant\nReasoning: {recommendations['reasoning']}",
                    location=location,
                    preferred_date=recommended_slot['start_time'],
                    calendar_providers=calendar_providers,
                    auto_schedule=True
                )
                
                if scheduling_result['success']:
                    return {
                        'success': True,
                        'message': 'Meeting scheduled successfully using AI recommendations',
                        'scheduled_slot': recommended_slot,
                        'ai_analysis': {
                            'confidence_score': recommendations['confidence_score'],
                            'reasoning': recommendations['reasoning'],
                            'priority_analysis': recommendations['priority_analysis']
                        },
                        'calendar_events': scheduling_result['created_events'],
                        'alternative_slots': recommendations['alternative_slots']
                    }
                else:
                    return scheduling_result
            else:
                # Return recommendations for manual confirmation
                return {
                    'success': True,
                    'message': 'AI scheduling recommendations ready',
                    'recommended_slot': recommended_slot,
                    'confidence_score': recommendations['confidence_score'],
                    'reasoning': recommendations['reasoning'],
                    'alternative_slots': recommendations['alternative_slots'],
                    'priority_analysis': recommendations['priority_analysis'],
                    'time_preferences': recommendations['time_preferences'],
                    'requires_confirmation': True
                }
                
        except Exception as e:
            logger.error(f"Error in intelligent meeting scheduling: {str(e)}")
            return {
                'success': False,
                'message': f'Intelligent scheduling failed: {str(e)}',
                'error': str(e)
            }
    
    def generate_scheduling_summary(self, scheduling_result: Dict[str, Any]) -> str:
        """Generate a human-readable summary of the scheduling decision."""
        if not scheduling_result['success']:
            return f"❌ Scheduling failed: {scheduling_result['message']}"
        
        slot = scheduling_result['recommended_slot']
        confidence = scheduling_result.get('confidence_score', 0)
        reasoning = scheduling_result.get('reasoning', 'No reasoning provided')
        
        summary = f"""
🎯 **Meeting Scheduled Successfully**

📅 **Selected Time**: {slot['start_time'].strftime('%A, %B %d, %Y at %I:%M %p')}
⏱️ **Duration**: {slot['duration_minutes']} minutes
🎯 **Confidence**: {confidence:.0%}

💡 **AI Reasoning**: {reasoning}

📊 **Analysis Summary**:
"""
        
        if 'priority_analysis' in scheduling_result:
            priority = scheduling_result['priority_analysis']
            summary += f"- Priority Level: {priority['level'].upper()} (Score: {priority['urgency_score']}/10)\n"
            summary += f"- Priority Reasoning: {priority['reasoning']}\n"
        
        if 'alternative_slots' in scheduling_result and scheduling_result['alternative_slots']:
            summary += f"- Alternative slots available: {len(scheduling_result['alternative_slots'])}\n"
        
        return summary

# Create global instance
smart_scheduler = SmartSchedulerAgent()
