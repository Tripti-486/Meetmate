import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import logging
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for structured output
class ActionItemExtracted(BaseModel):
    title: str = Field(description="Brief title of the action item")
    description: str = Field(description="Detailed description of what needs to be done")
    assignee: str = Field(description="Person responsible for the action item")
    due_date: Optional[str] = Field(description="Due date if mentioned (YYYY-MM-DD format)")
    priority: str = Field(description="Priority level: low, medium, high, urgent")

class KeyDecision(BaseModel):
    decision: str = Field(description="The key decision made during the meeting")
    context: str = Field(description="Context or reasoning behind the decision")

class MeetingMinutes(BaseModel):
    summary: str = Field(description="Concise summary of the meeting")
    key_decisions: List[KeyDecision] = Field(description="Important decisions made")
    discussion_points: List[str] = Field(description="Main topics discussed")
    action_items: List[ActionItemExtracted] = Field(description="Action items identified")
    next_meeting_info: Optional[str] = Field(description="Information about next meeting if mentioned")
    participants: List[str] = Field(description="List of meeting participants identified")

class MoMGeneratorAgent:
    """AI Agent for generating comprehensive Minutes of Meeting from transcripts."""
    
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key not configured")
        
        self.llm = ChatOpenAI(
            model="gpt-4-turbo-preview",
            temperature=0.1,
            openai_api_key=settings.openai_api_key
        )
        
        self.parser = PydanticOutputParser(pydantic_object=MeetingMinutes)
        
    def _create_mom_prompt(self) -> ChatPromptTemplate:
        """Create the prompt template for MoM generation."""
        
        system_message = """You are an expert meeting minutes generator. Your task is to analyze meeting transcripts and create comprehensive, professional minutes of meeting (MoM).

INSTRUCTIONS:
1. Extract key information from the transcript accurately
2. Identify all participants mentioned by name
3. Summarize the main discussion points concisely
4. Clearly identify all decisions made during the meeting
5. Extract actionable items with assignees and deadlines when mentioned
6. Maintain professional tone and structure
7. Focus on outcomes and deliverables
8. If speaker labels are available, use them to identify participants

IMPORTANT GUIDELINES:
- Be objective and factual
- Don't add information not present in the transcript
- Group related discussion points together
- Prioritize action items based on urgency and impact
- If no specific assignee is mentioned for an action item, note it as "To be assigned"
- Extract due dates in YYYY-MM-DD format when mentioned
- Classify priority as: low, medium, high, or urgent based on language used

{format_instructions}"""

        human_message = """Please analyze the following meeting transcript and generate comprehensive minutes of meeting:

MEETING DETAILS:
Title: {meeting_title}
Date: {meeting_date}
Duration: {duration} minutes

TRANSCRIPT:
{transcript}

Generate detailed minutes of meeting following the specified format."""

        return ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_message),
            HumanMessagePromptTemplate.from_template(human_message)
        ])
    
    def _create_action_items_prompt(self) -> ChatPromptTemplate:
        """Create a specialized prompt for extracting action items."""
        
        system_message = """You are specialized in extracting action items from meeting transcripts. Focus specifically on:

1. Tasks assigned to specific people
2. Deadlines and due dates mentioned
3. Follow-up actions required
4. Deliverables to be created
5. Next steps identified

Be very thorough and extract even implicit action items. Look for phrases like:
- "John will handle..."
- "We need to follow up on..."
- "Sarah should check..."
- "By next week, we should..."
- "The team needs to..."

{format_instructions}"""

        human_message = """Extract all action items from this meeting transcript:

{transcript}

Focus on identifying:
- WHO is responsible
- WHAT needs to be done
- WHEN it should be completed (if mentioned)
- WHY it's important (context)"""

        parser = PydanticOutputParser(pydantic_object=List[ActionItemExtracted])
        
        return ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_message.format(format_instructions=parser.get_format_instructions())),
            HumanMessagePromptTemplate.from_template(human_message)
        ])
    
    async def generate_mom(
        self,
        transcript: str,
        meeting_title: str = "Team Meeting",
        meeting_date: str = None,
        duration: int = 60,
        extract_detailed_action_items: bool = True
    ) -> Dict[str, Any]:
        """
        Generate comprehensive minutes of meeting from transcript.
        
        Args:
            transcript: Meeting transcript text
            meeting_title: Title of the meeting
            meeting_date: Date of the meeting (YYYY-MM-DD)
            duration: Meeting duration in minutes
            extract_detailed_action_items: Whether to run additional action item extraction
        
        Returns:
            Dictionary containing structured MoM data
        """
        try:
            if not meeting_date:
                meeting_date = datetime.now().strftime("%Y-%m-%d")
            
            logger.info(f"Generating MoM for meeting: {meeting_title}")
            
            # Create and format the main prompt
            prompt = self._create_mom_prompt()
            formatted_prompt = prompt.format_messages(
                meeting_title=meeting_title,
                meeting_date=meeting_date,
                duration=duration,
                transcript=transcript,
                format_instructions=self.parser.get_format_instructions()
            )
            
            # Generate MoM
            response = await self.llm.agenerate([formatted_prompt])
            mom_text = response.generations[0][0].text
            
            # Parse the structured output
            mom_data = self.parser.parse(mom_text)
            
            # Optionally extract additional detailed action items
            detailed_action_items = []
            if extract_detailed_action_items:
                detailed_action_items = await self._extract_detailed_action_items(transcript)
            
            # Combine and deduplicate action items
            all_action_items = self._merge_action_items(
                mom_data.action_items, 
                detailed_action_items
            )
            
            return {
                'summary': mom_data.summary,
                'key_decisions': [
                    {
                        'decision': kd.decision,
                        'context': kd.context
                    } for kd in mom_data.key_decisions
                ],
                'discussion_points': mom_data.discussion_points,
                'action_items': [
                    {
                        'title': ai.title,
                        'description': ai.description,
                        'assignee': ai.assignee,
                        'due_date': ai.due_date,
                        'priority': ai.priority
                    } for ai in all_action_items
                ],
                'next_meeting_info': mom_data.next_meeting_info,
                'participants': mom_data.participants,
                'meeting_metadata': {
                    'title': meeting_title,
                    'date': meeting_date,
                    'duration': duration,
                    'generated_at': datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating MoM: {str(e)}")
            raise
    
    async def _extract_detailed_action_items(self, transcript: str) -> List[ActionItemExtracted]:
        """Extract detailed action items using specialized prompt."""
        try:
            prompt = self._create_action_items_prompt()
            formatted_prompt = prompt.format_messages(transcript=transcript)
            
            response = await self.llm.agenerate([formatted_prompt])
            action_items_text = response.generations[0][0].text
            
            parser = PydanticOutputParser(pydantic_object=List[ActionItemExtracted])
            return parser.parse(action_items_text)
            
        except Exception as e:
            logger.warning(f"Failed to extract detailed action items: {str(e)}")
            return []
    
    def _merge_action_items(
        self, 
        main_action_items: List[ActionItemExtracted], 
        detailed_action_items: List[ActionItemExtracted]
    ) -> List[ActionItemExtracted]:
        """Merge and deduplicate action items from different extractions."""
        all_items = list(main_action_items)
        
        for detailed_item in detailed_action_items:
            # Check if this action item is already captured
            is_duplicate = False
            for existing_item in all_items:
                if (self._calculate_similarity(detailed_item.title, existing_item.title) > 0.7 or
                    self._calculate_similarity(detailed_item.description, existing_item.description) > 0.8):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                all_items.append(detailed_item)
        
        return all_items
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple similarity between two texts."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    async def generate_summary_only(self, transcript: str) -> str:
        """Generate a quick summary of the meeting."""
        try:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content="You are a meeting summarizer. Provide a concise 2-3 sentence summary of the key points discussed in this meeting."),
                HumanMessage(content=f"Summarize this meeting transcript:\n\n{transcript}")
            ])
            
            response = await self.llm.agenerate([prompt.format_messages()])
            return response.generations[0][0].text.strip()
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise
    
    async def extract_participants(self, transcript: str) -> List[str]:
        """Extract participant names from transcript."""
        try:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content="Extract all participant names mentioned in this meeting transcript. Return only the names as a JSON list."),
                HumanMessage(content=transcript)
            ])
            
            response = await self.llm.agenerate([prompt.format_messages()])
            participants_text = response.generations[0][0].text.strip()
            
            # Try to parse as JSON, fallback to simple extraction
            try:
                participants = json.loads(participants_text)
                return participants if isinstance(participants, list) else []
            except:
                # Fallback: extract names from text
                return [name.strip() for name in participants_text.split(',') if name.strip()]
                
        except Exception as e:
            logger.warning(f"Error extracting participants: {str(e)}")
            return []
    
    def validate_mom_quality(self, mom_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the quality and completeness of generated MoM."""
        quality_score = 100
        issues = []
        suggestions = []
        
        # Check summary quality
        if len(mom_data.get('summary', '')) < 50:
            quality_score -= 20
            issues.append("Summary is too brief")
            suggestions.append("Provide more detailed summary of key discussions")
        
        # Check action items
        action_items = mom_data.get('action_items', [])
        if not action_items:
            quality_score -= 30
            issues.append("No action items identified")
            suggestions.append("Review transcript for follow-up tasks and assignments")
        else:
            unassigned_items = [ai for ai in action_items if not ai.get('assignee') or ai['assignee'] == 'To be assigned']
            if len(unassigned_items) > len(action_items) * 0.5:
                quality_score -= 15
                issues.append("Many action items lack clear assignees")
                suggestions.append("Clarify who is responsible for each action item")
        
        # Check key decisions
        if not mom_data.get('key_decisions'):
            quality_score -= 20
            issues.append("No key decisions recorded")
            suggestions.append("Identify important decisions made during the meeting")
        
        # Check participants
        if len(mom_data.get('participants', [])) < 2:
            quality_score -= 10
            issues.append("Few participants identified")
            suggestions.append("Ensure all meeting participants are captured")
        
        return {
            'quality_score': max(0, quality_score),
            'issues': issues,
            'suggestions': suggestions,
            'is_high_quality': quality_score >= 80
        }

# Create global instance
mom_generator = MoMGeneratorAgent()
