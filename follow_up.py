import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import json
import logging
from sqlalchemy.orm import Session
from data.db_config import get_db, ActionItem, Meeting, User
from services.email_service import email_service
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for structured output
class ActionItemUpdate(BaseModel):
    status: str = Field(description="Updated status: pending, in_progress, completed, overdue")
    progress_notes: Optional[str] = Field(description="Notes about progress made")
    estimated_completion_date: Optional[str] = Field(description="New estimated completion date")
    blocking_issues: List[str] = Field(description="Issues blocking completion")

class FollowUpStrategy(BaseModel):
    priority_level: str = Field(description="Follow-up priority: low, medium, high, urgent")
    next_action: str = Field(description="Recommended next action")
    escalation_required: bool = Field(description="Whether escalation is needed")
    suggested_reminder_frequency: int = Field(description="Days between reminders")
    stakeholders_to_notify: List[str] = Field(description="Who should be notified")

class ActionItemAnalysis(BaseModel):
    risk_level: str = Field(description="Risk level: low, medium, high, critical")
    completion_probability: float = Field(description="Probability of completion on time (0-1)")
    dependency_issues: List[str] = Field(description="Identified dependency problems")
    resource_needs: List[str] = Field(description="Additional resources needed")
    recommendations: List[str] = Field(description="Specific recommendations")

class FollowUpAgent:
    """AI-powered agent for tracking action items and managing follow-ups."""
    
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key not configured")
        
        self.llm = ChatOpenAI(
            model="gpt-4-turbo-preview",
            temperature=0.2,
            openai_api_key=settings.openai_api_key
        )
        
        self.email_service = email_service
    
    def _create_analysis_prompt(self) -> ChatPromptTemplate:
        """Create prompt for analyzing action item status and risks."""
        
        system_message = """You are an expert project management assistant who analyzes action items to assess risks and provide follow-up recommendations.

Analyze action items based on:
1. Due date proximity and overdue status
2. Priority level and business impact
3. Historical completion patterns
4. Complexity and resource requirements
5. Dependencies and blocking factors
6. Assignee workload and capacity

Risk Levels:
- critical: Overdue high-priority items affecting critical business functions
- high: Near-due important items or items with blocking dependencies
- medium: Standard items with moderate risk of delay
- low: Low-priority items with adequate time for completion

{format_instructions}"""

        human_message = """Analyze this action item and provide risk assessment:

ACTION ITEM:
Title: {title}
Description: {description}
Assignee: {assignee}
Due Date: {due_date}
Priority: {priority}
Status: {status}
Created: {created_date}

CONTEXT:
Days until due: {days_until_due}
Is overdue: {is_overdue}
Meeting context: {meeting_title}
Other assignee tasks: {assignee_workload}

Provide comprehensive analysis including risk level, completion probability, and recommendations."""

        return ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_message),
            HumanMessagePromptTemplate.from_template(human_message)
        ])
    
    def _create_follow_up_strategy_prompt(self) -> ChatPromptTemplate:
        """Create prompt for determining follow-up strategy."""
        
        system_message = """You are an expert at creating follow-up strategies for action items based on their risk level and current status.

Consider these factors when creating follow-up strategy:
1. Risk level and urgency
2. Time since last update
3. Assignee responsiveness history
4. Item complexity and dependencies
5. Business impact and stakeholder expectations
6. Team dynamics and communication preferences

Follow-up Actions:
- gentle_reminder: Standard reminder email
- urgent_follow_up: Direct contact with urgency indicators
- escalate_to_manager: Involve supervisor or manager
- redistribute_task: Consider reassigning to another team member
- deadline_extension: Negotiate new timeline
- resource_allocation: Provide additional support

{format_instructions}"""

        human_message = """Create follow-up strategy for this action item:

ITEM ANALYSIS:
Risk Level: {risk_level}
Completion Probability: {completion_probability}
Days Overdue: {days_overdue}
Priority: {priority}
Assignee: {assignee}

HISTORY:
Last reminder sent: {last_reminder_date}
Previous follow-ups: {follow_up_count}
Assignee response rate: {response_rate}

CONTEXT:
Team size: {team_size}
Project deadline pressure: {deadline_pressure}
Available resources: {resource_availability}

Create an effective follow-up strategy with specific next actions."""

        return ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_message),
            HumanMessagePromptTemplate.from_template(human_message)
        ])
    
    async def analyze_action_item(
        self,
        action_item: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze an action item for risks and completion probability."""
        try:
            if not context:
                context = {}
            
            # Calculate time metrics
            due_date = None
            days_until_due = None
            is_overdue = False
            
            if action_item.get('due_date'):
                try:
                    due_date = datetime.strptime(action_item['due_date'], '%Y-%m-%d').date()
                    days_until_due = (due_date - date.today()).days
                    is_overdue = days_until_due < 0
                except:
                    pass
            
            parser = PydanticOutputParser(pydantic_object=ActionItemAnalysis)
            prompt = self._create_analysis_prompt()
            
            formatted_prompt = prompt.format_messages(
                title=action_item.get('title', ''),
                description=action_item.get('description', ''),
                assignee=action_item.get('assignee', ''),
                due_date=action_item.get('due_date', 'Not set'),
                priority=action_item.get('priority', 'medium'),
                status=action_item.get('status', 'pending'),
                created_date=action_item.get('created_at', ''),
                days_until_due=days_until_due if days_until_due is not None else 'Unknown',
                is_overdue=is_overdue,
                meeting_title=context.get('meeting_title', ''),
                assignee_workload=context.get('assignee_workload', 'Unknown'),
                format_instructions=parser.get_format_instructions()
            )
            
            response = await self.llm.agenerate([formatted_prompt])
            analysis_text = response.generations[0][0].text
            
            analysis_data = parser.parse(analysis_text)
            
            return {
                'risk_level': analysis_data.risk_level,
                'completion_probability': analysis_data.completion_probability,
                'dependency_issues': analysis_data.dependency_issues,
                'resource_needs': analysis_data.resource_needs,
                'recommendations': analysis_data.recommendations,
                'days_until_due': days_until_due,
                'is_overdue': is_overdue,
                'analysis_date': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing action item: {str(e)}")
            # Fallback analysis
            return self._fallback_analysis(action_item)
    
    def _fallback_analysis(self, action_item: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback analysis using simple heuristics."""
        due_date = action_item.get('due_date')
        priority = action_item.get('priority', 'medium')
        
        # Simple risk assessment
        risk_level = 'low'
        completion_probability = 0.8
        
        if due_date:
            try:
                due = datetime.strptime(due_date, '%Y-%m-%d').date()
                days_until = (due - date.today()).days
                
                if days_until < 0:  # Overdue
                    risk_level = 'critical' if priority in ['high', 'urgent'] else 'high'
                    completion_probability = 0.3
                elif days_until <= 1:  # Due soon
                    risk_level = 'high' if priority in ['high', 'urgent'] else 'medium'
                    completion_probability = 0.6
                elif days_until <= 3:
                    risk_level = 'medium'
                    completion_probability = 0.7
            except:
                pass
        
        return {
            'risk_level': risk_level,
            'completion_probability': completion_probability,
            'dependency_issues': [],
            'resource_needs': [],
            'recommendations': ['Regular follow-up recommended'],
            'days_until_due': None,
            'is_overdue': False,
            'analysis_date': datetime.now().isoformat()
        }
    
    async def create_follow_up_strategy(
        self,
        action_item: Dict[str, Any],
        analysis: Dict[str, Any],
        follow_up_history: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a follow-up strategy based on analysis."""
        try:
            if not follow_up_history:
                follow_up_history = {}
            
            parser = PydanticOutputParser(pydantic_object=FollowUpStrategy)
            prompt = self._create_follow_up_strategy_prompt()
            
            formatted_prompt = prompt.format_messages(
                risk_level=analysis.get('risk_level', 'medium'),
                completion_probability=analysis.get('completion_probability', 0.5),
                days_overdue=max(0, -(analysis.get('days_until_due', 0))),
                priority=action_item.get('priority', 'medium'),
                assignee=action_item.get('assignee', ''),
                last_reminder_date=follow_up_history.get('last_reminder_date', 'Never'),
                follow_up_count=follow_up_history.get('follow_up_count', 0),
                response_rate=follow_up_history.get('response_rate', 'Unknown'),
                team_size=follow_up_history.get('team_size', 'Unknown'),
                deadline_pressure=follow_up_history.get('deadline_pressure', 'Medium'),
                resource_availability=follow_up_history.get('resource_availability', 'Limited'),
                format_instructions=parser.get_format_instructions()
            )
            
            response = await self.llm.agenerate([formatted_prompt])
            strategy_text = response.generations[0][0].text
            
            strategy_data = parser.parse(strategy_text)
            
            return {
                'priority_level': strategy_data.priority_level,
                'next_action': strategy_data.next_action,
                'escalation_required': strategy_data.escalation_required,
                'suggested_reminder_frequency': strategy_data.suggested_reminder_frequency,
                'stakeholders_to_notify': strategy_data.stakeholders_to_notify,
                'strategy_created': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating follow-up strategy: {str(e)}")
            # Fallback strategy
            return self._fallback_strategy(action_item, analysis)
    
    def _fallback_strategy(self, action_item: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback strategy using simple rules."""
        risk_level = analysis.get('risk_level', 'medium')
        
        if risk_level == 'critical':
            return {
                'priority_level': 'urgent',
                'next_action': 'urgent_follow_up',
                'escalation_required': True,
                'suggested_reminder_frequency': 1,
                'stakeholders_to_notify': ['manager', 'assignee'],
                'strategy_created': datetime.now().isoformat()
            }
        elif risk_level == 'high':
            return {
                'priority_level': 'high',
                'next_action': 'direct_follow_up',
                'escalation_required': False,
                'suggested_reminder_frequency': 2,
                'stakeholders_to_notify': ['assignee'],
                'strategy_created': datetime.now().isoformat()
            }
        else:
            return {
                'priority_level': 'medium',
                'next_action': 'gentle_reminder',
                'escalation_required': False,
                'suggested_reminder_frequency': 7,
                'stakeholders_to_notify': ['assignee'],
                'strategy_created': datetime.now().isoformat()
            }
    
    async def get_overdue_action_items(self, db: Session) -> List[Dict[str, Any]]:
        """Get all overdue action items from database."""
        try:
            today = date.today()
            overdue_items = db.query(ActionItem).filter(
                ActionItem.due_date < today,
                ActionItem.status.in_(['pending', 'in_progress'])
            ).all()
            
            result = []
            for item in overdue_items:
                days_overdue = (today - item.due_date).days
                result.append({
                    'id': item.id,
                    'title': item.title,
                    'description': item.description,
                    'assignee': item.assignee.email if item.assignee else 'Unknown',
                    'assignee_name': item.assignee.name if item.assignee else 'Unknown',
                    'due_date': item.due_date.strftime('%Y-%m-%d'),
                    'priority': item.priority,
                    'status': item.status,
                    'meeting_id': item.meeting_id,
                    'meeting_title': item.meeting.title if item.meeting else 'Unknown',
                    'created_at': item.created_at.isoformat(),
                    'days_overdue': days_overdue
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting overdue action items: {str(e)}")
            return []
    
    async def get_upcoming_due_items(self, db: Session, days_ahead: int = 3) -> List[Dict[str, Any]]:
        """Get action items due within specified days."""
        try:
            today = date.today()
            upcoming_date = today + timedelta(days=days_ahead)
            
            upcoming_items = db.query(ActionItem).filter(
                ActionItem.due_date >= today,
                ActionItem.due_date <= upcoming_date,
                ActionItem.status.in_(['pending', 'in_progress'])
            ).all()
            
            result = []
            for item in upcoming_items:
                days_until_due = (item.due_date - today).days
                result.append({
                    'id': item.id,
                    'title': item.title,
                    'description': item.description,
                    'assignee': item.assignee.email if item.assignee else 'Unknown',
                    'assignee_name': item.assignee.name if item.assignee else 'Unknown',
                    'due_date': item.due_date.strftime('%Y-%m-%d'),
                    'priority': item.priority,
                    'status': item.status,
                    'meeting_id': item.meeting_id,
                    'meeting_title': item.meeting.title if item.meeting else 'Unknown',
                    'created_at': item.created_at.isoformat(),
                    'days_until_due': days_until_due
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting upcoming due items: {str(e)}")
            return []
    
    async def process_daily_follow_ups(self, db: Session) -> Dict[str, Any]:
        """Process daily follow-ups for all action items."""
        try:
            logger.info("Starting daily follow-up processing")
            
            # Get overdue and upcoming items
            overdue_items = await self.get_overdue_action_items(db)
            upcoming_items = await self.get_upcoming_due_items(db, days_ahead=3)
            
            results = {
                'processed_date': datetime.now().isoformat(),
                'overdue_items_count': len(overdue_items),
                'upcoming_items_count': len(upcoming_items),
                'actions_taken': [],
                'emails_sent': 0,
                'escalations_created': 0,
                'errors': []
            }
            
            # Process overdue items with high priority
            for item in overdue_items:
                try:
                    analysis = await self.analyze_action_item(item)
                    strategy = await self.create_follow_up_strategy(item, analysis)
                    
                    action_taken = await self._execute_follow_up_action(item, strategy, analysis)
                    results['actions_taken'].append(action_taken)
                    
                    if action_taken.get('email_sent'):
                        results['emails_sent'] += 1
                    if action_taken.get('escalation_created'):
                        results['escalations_created'] += 1
                        
                except Exception as e:
                    error_msg = f"Error processing overdue item {item['id']}: {str(e)}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            # Process upcoming items with lower priority
            for item in upcoming_items:
                try:
                    analysis = await self.analyze_action_item(item)
                    
                    # Only send reminders for high-priority upcoming items
                    if analysis['risk_level'] in ['high', 'critical'] or item['priority'] in ['high', 'urgent']:
                        strategy = await self.create_follow_up_strategy(item, analysis)
                        action_taken = await self._execute_follow_up_action(item, strategy, analysis)
                        results['actions_taken'].append(action_taken)
                        
                        if action_taken.get('email_sent'):
                            results['emails_sent'] += 1
                        
                except Exception as e:
                    error_msg = f"Error processing upcoming item {item['id']}: {str(e)}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            logger.info(f"Daily follow-up processing completed. Sent {results['emails_sent']} emails.")
            return results
            
        except Exception as e:
            logger.error(f"Error in daily follow-up processing: {str(e)}")
            return {
                'processed_date': datetime.now().isoformat(),
                'error': str(e),
                'success': False
            }
    
    async def _execute_follow_up_action(
        self,
        action_item: Dict[str, Any],
        strategy: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the determined follow-up action."""
        action_result = {
            'action_item_id': action_item['id'],
            'action_type': strategy['next_action'],
            'timestamp': datetime.now().isoformat(),
            'email_sent': False,
            'escalation_created': False,
            'success': False
        }
        
        try:
            next_action = strategy['next_action']
            
            if next_action in ['gentle_reminder', 'urgent_follow_up', 'direct_follow_up']:
                # Send reminder email
                meeting_data = {
                    'meeting_metadata': {
                        'title': action_item.get('meeting_title', 'Unknown Meeting'),
                        'date': action_item.get('created_at', '')[:10]
                    }
                }
                
                # Customize message based on urgency
                custom_message = None
                if next_action == 'urgent_follow_up':
                    custom_message = f"⚠️ This action item is {action_item.get('days_overdue', 0)} days overdue and requires immediate attention."
                elif analysis['risk_level'] == 'high':
                    custom_message = "This item has been identified as high-risk and may impact project delivery."
                
                email_sent = await self.email_service.send_action_item_reminder(
                    action_item=action_item,
                    meeting_data=meeting_data,
                    custom_message=custom_message
                )
                
                action_result['email_sent'] = email_sent
                action_result['success'] = email_sent
                
            elif next_action == 'escalate_to_manager':
                # Create escalation (in a real system, this might create a ticket or notification)
                action_result['escalation_created'] = True
                action_result['success'] = True
                logger.info(f"Escalation created for action item {action_item['id']}")
                
            elif next_action == 'redistribute_task':
                # Log recommendation for task redistribution
                action_result['recommendation'] = 'Task redistribution recommended'
                action_result['success'] = True
                logger.info(f"Task redistribution recommended for action item {action_item['id']}")
                
            elif next_action == 'deadline_extension':
                # Log recommendation for deadline extension
                action_result['recommendation'] = 'Deadline extension recommended'
                action_result['success'] = True
                logger.info(f"Deadline extension recommended for action item {action_item['id']}")
            
            return action_result
            
        except Exception as e:
            logger.error(f"Error executing follow-up action: {str(e)}")
            action_result['error'] = str(e)
            return action_result
    
    async def generate_follow_up_report(self, db: Session) -> Dict[str, Any]:
        """Generate a comprehensive follow-up report."""
        try:
            overdue_items = await self.get_overdue_action_items(db)
            upcoming_items = await self.get_upcoming_due_items(db, days_ahead=7)
            
            # Analyze all items
            high_risk_items = []
            medium_risk_items = []
            low_risk_items = []
            
            all_items = overdue_items + upcoming_items
            
            for item in all_items:
                analysis = await self.analyze_action_item(item)
                item['analysis'] = analysis
                
                if analysis['risk_level'] in ['critical', 'high']:
                    high_risk_items.append(item)
                elif analysis['risk_level'] == 'medium':
                    medium_risk_items.append(item)
                else:
                    low_risk_items.append(item)
            
            # Calculate statistics
            total_items = len(all_items)
            overdue_count = len(overdue_items)
            completion_rates = [item['analysis']['completion_probability'] for item in all_items]
            avg_completion_probability = sum(completion_rates) / len(completion_rates) if completion_rates else 0
            
            return {
                'report_date': datetime.now().isoformat(),
                'summary': {
                    'total_active_items': total_items,
                    'overdue_items': overdue_count,
                    'upcoming_items': len(upcoming_items),
                    'high_risk_items': len(high_risk_items),
                    'average_completion_probability': avg_completion_probability
                },
                'risk_breakdown': {
                    'high_risk': high_risk_items,
                    'medium_risk': medium_risk_items,
                    'low_risk': low_risk_items
                },
                'recommendations': self._generate_management_recommendations(all_items),
                'alerts': self._generate_alerts(overdue_items, high_risk_items)
            }
            
        except Exception as e:
            logger.error(f"Error generating follow-up report: {str(e)}")
            return {
                'report_date': datetime.now().isoformat(),
                'error': str(e),
                'success': False
            }
    
    def _generate_management_recommendations(self, items: List[Dict[str, Any]]) -> List[str]:
        """Generate management recommendations based on action item analysis."""
        recommendations = []
        
        overdue_high_priority = [item for item in items if item.get('days_overdue', 0) > 0 and item.get('priority') in ['high', 'urgent']]
        if overdue_high_priority:
            recommendations.append(f"Immediate attention needed: {len(overdue_high_priority)} high-priority items are overdue")
        
        low_completion_prob = [item for item in items if item.get('analysis', {}).get('completion_probability', 1) < 0.5]
        if low_completion_prob:
            recommendations.append(f"Resource allocation review needed: {len(low_completion_prob)} items have low completion probability")
        
        resource_constrained = [item for item in items if item.get('analysis', {}).get('resource_needs')]
        if resource_constrained:
            recommendations.append(f"Additional resources may be needed for {len(resource_constrained)} items")
        
        if not recommendations:
            recommendations.append("Action item tracking is on track with no major concerns")
        
        return recommendations
    
    def _generate_alerts(self, overdue_items: List[Dict[str, Any]], high_risk_items: List[Dict[str, Any]]) -> List[str]:
        """Generate alerts for critical situations."""
        alerts = []
        
        critical_overdue = [item for item in overdue_items if item.get('priority') == 'urgent']
        if critical_overdue:
            alerts.append(f"🚨 CRITICAL: {len(critical_overdue)} urgent items are overdue")
        
        long_overdue = [item for item in overdue_items if item.get('days_overdue', 0) > 7]
        if long_overdue:
            alerts.append(f"⚠️ WARNING: {len(long_overdue)} items are more than 7 days overdue")
        
        high_risk_near_due = [item for item in high_risk_items if item.get('days_until_due', 999) <= 1]
        if high_risk_near_due:
            alerts.append(f"⏰ URGENT: {len(high_risk_near_due)} high-risk items are due within 1 day")
        
        return alerts

# Create global instance
follow_up_agent = FollowUpAgent()
