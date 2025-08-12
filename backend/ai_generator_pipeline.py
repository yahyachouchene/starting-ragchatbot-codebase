"""
Alternative AI Generator Implementation using State Machine Pipeline Architecture

This implementation treats sequential tool calling as a state machine where each round
is a distinct state with explicit context flow and event-driven transitions.
"""

import anthropic
from typing import List, Optional, Dict, Any, Tuple, Callable
from enum import Enum
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class RoundState(Enum):
    """Enumeration of possible round states in the pipeline"""
    INITIAL_QUERY = "initial_query"
    FIRST_TOOL_ROUND = "first_tool_round" 
    SECOND_TOOL_ROUND = "second_tool_round"
    SYNTHESIS_ROUND = "synthesis_round"
    COMPLETED = "completed"
    FAILED = "failed"


class RoundEvent(Enum):
    """Events that trigger state transitions"""
    TOOL_USAGE_REQUIRED = "tool_usage_required"
    TOOL_EXECUTED_CONTINUE = "tool_executed_continue"
    TOOL_EXECUTED_SYNTHESIZE = "tool_executed_synthesize"
    DIRECT_RESPONSE = "direct_response"
    MAX_ROUNDS_REACHED = "max_rounds_reached"
    ERROR_OCCURRED = "error_occurred"


@dataclass
class RoundContext:
    """Context object that flows between pipeline states"""
    # User input
    original_query: str
    conversation_history: Optional[str] = None
    
    # Pipeline state
    current_state: RoundState = RoundState.INITIAL_QUERY
    round_number: int = 0
    max_rounds: int = 2
    
    # Conversation accumulation
    messages: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    
    # Tool execution tracking
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    executed_tools: List[str] = field(default_factory=list)
    round_summaries: List[str] = field(default_factory=list)
    
    # Error handling
    errors: List[str] = field(default_factory=list)
    rollback_states: List[RoundState] = field(default_factory=list)
    
    # Final result
    final_response: Optional[str] = None
    sources: List[Dict[str, Any]] = field(default_factory=list)


class RoundProcessor(ABC):
    """Abstract base class for round processors in the pipeline"""
    
    @abstractmethod
    def can_handle(self, context: RoundContext) -> bool:
        """Check if this processor can handle the current context state"""
        pass
    
    @abstractmethod
    def process(self, context: RoundContext, api_client: anthropic.Anthropic, 
               tools: List[Dict], tool_manager) -> Tuple[RoundEvent, RoundContext]:
        """Process the round and return next event and updated context"""
        pass
    
    @abstractmethod
    def rollback(self, context: RoundContext) -> RoundContext:
        """Handle rollback for this processor"""
        pass


class InitialQueryProcessor(RoundProcessor):
    """Processes the initial user query to determine tool usage needs"""
    
    def __init__(self, base_params: Dict[str, Any]):
        self.base_params = base_params
        
    def can_handle(self, context: RoundContext) -> bool:
        return context.current_state == RoundState.INITIAL_QUERY
    
    def process(self, context: RoundContext, api_client: anthropic.Anthropic,
               tools: List[Dict], tool_manager) -> Tuple[RoundEvent, RoundContext]:
        """Process initial query with enhanced reasoning about tool usage"""
        
        # Enhanced system prompt for initial reasoning
        enhanced_system = context.system_prompt + """

ROUND 1 INSTRUCTIONS - Initial Analysis:
You are in the first round of a multi-round conversation. Your job is to:
1. Analyze if this query needs tool usage for accurate response
2. If tools needed, use them strategically - you may get another round
3. If no tools needed, provide direct response using existing knowledge
4. Consider if you might need multiple searches to fully answer the query

Examples of multi-round scenarios:
- "Compare course A with course B" → Search A in round 1, search B in round 2
- "Find differences between lessons 1 and 3 in course X" → Search lesson 1, then lesson 3
- "Show me content from both Introduction and Advanced courses" → Search each separately

Current round: 1/2 maximum
"""
        
        # Prepare API call
        api_params = {
            **self.base_params,
            "messages": [{"role": "user", "content": context.original_query}],
            "system": enhanced_system,
            "tools": tools,
            "tool_choice": {"type": "auto"}
        }
        
        try:
            response = api_client.messages.create(**api_params)
            
            # Update context with response
            context.messages.append({"role": "user", "content": context.original_query})
            context.messages.append({"role": "assistant", "content": response.content})
            context.round_number = 1
            
            if response.stop_reason == "tool_use":
                # Execute tools and prepare for potential next round
                tool_results = self._execute_tools(response, tool_manager)
                context.tool_results.extend(tool_results)
                context.messages.append({"role": "user", "content": tool_results})
                
                # Track what tools were used
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        context.executed_tools.append(content_block.name)
                
                context.current_state = RoundState.FIRST_TOOL_ROUND
                return RoundEvent.TOOL_EXECUTED_CONTINUE, context
            else:
                # Direct response without tools
                context.final_response = response.content[0].text
                context.current_state = RoundState.COMPLETED
                return RoundEvent.DIRECT_RESPONSE, context
                
        except Exception as e:
            context.errors.append(f"Initial query processing failed: {str(e)}")
            context.current_state = RoundState.FAILED
            return RoundEvent.ERROR_OCCURRED, context
    
    def _execute_tools(self, response, tool_manager) -> List[Dict[str, Any]]:
        """Execute tools from the response"""
        tool_results = []
        for content_block in response.content:
            if content_block.type == "tool_use":
                result = tool_manager.execute_tool(
                    content_block.name, 
                    **content_block.input
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": content_block.id,
                    "content": result
                })
        return tool_results
    
    def rollback(self, context: RoundContext) -> RoundContext:
        """Reset to initial state"""
        context.messages.clear()
        context.tool_results.clear()
        context.executed_tools.clear()
        context.round_number = 0
        context.current_state = RoundState.INITIAL_QUERY
        return context


class SequentialToolProcessor(RoundProcessor):
    """Processes sequential tool rounds with reasoning about continuation"""
    
    def __init__(self, base_params: Dict[str, Any]):
        self.base_params = base_params
    
    def can_handle(self, context: RoundContext) -> bool:
        return context.current_state in [RoundState.FIRST_TOOL_ROUND, RoundState.SECOND_TOOL_ROUND]
    
    def process(self, context: RoundContext, api_client: anthropic.Anthropic,
               tools: List[Dict], tool_manager) -> Tuple[RoundEvent, RoundContext]:
        """Process sequential tool round with continuation logic"""
        
        is_final_round = context.round_number >= context.max_rounds
        
        # Build system prompt with round context
        round_system = self._build_round_system_prompt(context, is_final_round)
        
        # Prepare API call with accumulated context
        api_params = {
            **self.base_params,
            "messages": context.messages,
            "system": round_system
        }
        
        # Add tools only if not final round
        if not is_final_round:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}
        
        try:
            response = api_client.messages.create(**api_params)
            
            # Update context
            context.messages.append({"role": "assistant", "content": response.content})
            
            if response.stop_reason == "tool_use" and not is_final_round:
                # Execute tools for next round
                tool_results = self._execute_tools(response, tool_manager)
                context.tool_results.extend(tool_results)
                context.messages.append({"role": "user", "content": tool_results})
                
                # Track executed tools
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        context.executed_tools.append(content_block.name)
                
                context.round_number += 1
                if context.round_number >= context.max_rounds:
                    context.current_state = RoundState.SYNTHESIS_ROUND
                    return RoundEvent.TOOL_EXECUTED_SYNTHESIZE, context
                else:
                    context.current_state = RoundState.SECOND_TOOL_ROUND
                    return RoundEvent.TOOL_EXECUTED_CONTINUE, context
            else:
                # Final response ready
                context.final_response = response.content[0].text
                context.current_state = RoundState.COMPLETED
                return RoundEvent.DIRECT_RESPONSE, context
                
        except Exception as e:
            context.errors.append(f"Sequential tool processing failed: {str(e)}")
            context.current_state = RoundState.FAILED
            return RoundEvent.ERROR_OCCURRED, context
    
    def _build_round_system_prompt(self, context: RoundContext, is_final_round: bool) -> str:
        """Build system prompt with round context"""
        executed_tools_summary = ", ".join(context.executed_tools) if context.executed_tools else "none"
        
        round_context = f"""

ROUND {context.round_number} CONTEXT:
- Tools executed so far: {executed_tools_summary}
- This is {"the FINAL round" if is_final_round else f"round {context.round_number}/{context.max_rounds}"}

"""
        
        if is_final_round:
            round_context += """
FINAL ROUND INSTRUCTIONS:
- You CANNOT use tools in this round
- Synthesize all previous tool results into a comprehensive answer
- Focus on directly answering the original user query
- Be concise but thorough in your final response
"""
        else:
            round_context += f"""
ROUND {context.round_number} INSTRUCTIONS:
- You may use tools if needed for additional information
- Consider what information you still need to fully answer the query
- You have {context.max_rounds - context.round_number} more round(s) after this
- If you have enough information, provide the final answer without using tools
"""
        
        return context.system_prompt + round_context
    
    def _execute_tools(self, response, tool_manager) -> List[Dict[str, Any]]:
        """Execute tools from the response"""
        tool_results = []
        for content_block in response.content:
            if content_block.type == "tool_use":
                result = tool_manager.execute_tool(
                    content_block.name, 
                    **content_block.input
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": content_block.id,
                    "content": result
                })
        return tool_results
    
    def rollback(self, context: RoundContext) -> RoundContext:
        """Rollback to previous round state"""
        if context.rollback_states:
            context.current_state = context.rollback_states.pop()
            context.round_number = max(0, context.round_number - 1)
        return context


class SynthesisProcessor(RoundProcessor):
    """Processes final synthesis round without tool access"""
    
    def __init__(self, base_params: Dict[str, Any]):
        self.base_params = base_params
    
    def can_handle(self, context: RoundContext) -> bool:
        return context.current_state == RoundState.SYNTHESIS_ROUND
    
    def process(self, context: RoundContext, api_client: anthropic.Anthropic,
               tools: List[Dict], tool_manager) -> Tuple[RoundEvent, RoundContext]:
        """Process final synthesis without tool access"""
        
        synthesis_system = context.system_prompt + """

SYNTHESIS ROUND - FINAL RESPONSE:
- You have reached the maximum number of tool-enabled rounds
- NO TOOLS AVAILABLE in this round - synthesize existing information
- Provide a comprehensive final answer based on all previous tool results
- Focus on directly addressing the original user query
- Be thorough but concise in your response
"""
        
        api_params = {
            **self.base_params,
            "messages": context.messages,
            "system": synthesis_system
            # Note: No tools parameter - tools disabled in synthesis round
        }
        
        try:
            response = api_client.messages.create(**api_params)
            
            context.final_response = response.content[0].text
            context.current_state = RoundState.COMPLETED
            
            return RoundEvent.DIRECT_RESPONSE, context
            
        except Exception as e:
            context.errors.append(f"Synthesis processing failed: {str(e)}")
            context.current_state = RoundState.FAILED
            return RoundEvent.ERROR_OCCURRED, context
    
    def rollback(self, context: RoundContext) -> RoundContext:
        """Rollback to previous tool round"""
        context.current_state = RoundState.SECOND_TOOL_ROUND
        return context


class PipelineOrchestrator:
    """Central orchestrator that manages the state machine pipeline"""
    
    def __init__(self):
        self.processors: Dict[RoundState, RoundProcessor] = {}
        self.state_transitions: Dict[RoundState, Dict[RoundEvent, RoundState]] = {
            RoundState.INITIAL_QUERY: {
                RoundEvent.TOOL_EXECUTED_CONTINUE: RoundState.FIRST_TOOL_ROUND,
                RoundEvent.DIRECT_RESPONSE: RoundState.COMPLETED,
                RoundEvent.ERROR_OCCURRED: RoundState.FAILED
            },
            RoundState.FIRST_TOOL_ROUND: {
                RoundEvent.TOOL_EXECUTED_CONTINUE: RoundState.SECOND_TOOL_ROUND,
                RoundEvent.TOOL_EXECUTED_SYNTHESIZE: RoundState.SYNTHESIS_ROUND,
                RoundEvent.DIRECT_RESPONSE: RoundState.COMPLETED,
                RoundEvent.ERROR_OCCURRED: RoundState.FAILED
            },
            RoundState.SECOND_TOOL_ROUND: {
                RoundEvent.TOOL_EXECUTED_SYNTHESIZE: RoundState.SYNTHESIS_ROUND,
                RoundEvent.DIRECT_RESPONSE: RoundState.COMPLETED,
                RoundEvent.ERROR_OCCURRED: RoundState.FAILED
            },
            RoundState.SYNTHESIS_ROUND: {
                RoundEvent.DIRECT_RESPONSE: RoundState.COMPLETED,
                RoundEvent.ERROR_OCCURRED: RoundState.FAILED
            }
        }
    
    def register_processor(self, state: RoundState, processor: RoundProcessor):
        """Register a processor for a specific state"""
        self.processors[state] = processor
    
    def execute_pipeline(self, context: RoundContext, api_client: anthropic.Anthropic,
                        tools: List[Dict], tool_manager) -> RoundContext:
        """Execute the complete pipeline until completion or failure"""
        
        max_iterations = 10  # Safety valve to prevent infinite loops
        iterations = 0
        
        while (context.current_state not in [RoundState.COMPLETED, RoundState.FAILED] 
               and iterations < max_iterations):
            
            iterations += 1
            logger.info(f"Pipeline iteration {iterations}, state: {context.current_state}")
            
            # Find processor for current state
            processor = self.processors.get(context.current_state)
            if not processor or not processor.can_handle(context):
                context.errors.append(f"No processor found for state: {context.current_state}")
                context.current_state = RoundState.FAILED
                break
            
            # Save state for potential rollback
            context.rollback_states.append(context.current_state)
            
            try:
                # Process current round
                event, context = processor.process(context, api_client, tools, tool_manager)
                
                # Handle state transition
                next_state = self.state_transitions.get(context.current_state, {}).get(event)
                if next_state:
                    context.current_state = next_state
                else:
                    context.errors.append(f"Invalid transition from {context.current_state} on {event}")
                    context.current_state = RoundState.FAILED
                    
            except Exception as e:
                logger.error(f"Pipeline error: {str(e)}")
                context.errors.append(f"Pipeline execution error: {str(e)}")
                
                # Attempt rollback
                if context.rollback_states and len(context.rollback_states) > 1:
                    processor.rollback(context)
                else:
                    context.current_state = RoundState.FAILED
        
        if iterations >= max_iterations:
            context.errors.append("Pipeline exceeded maximum iterations")
            context.current_state = RoundState.FAILED
        
        return context


class AIGeneratorPipeline:
    """Main AI Generator using State Machine Pipeline Architecture"""
    
    # Enhanced system prompt for multi-round reasoning
    SYSTEM_PROMPT = """You are an AI assistant specialized in course materials and educational content with access to comprehensive tools for course information.

MULTI-ROUND TOOL CALLING CAPABILITY:
- You can make tool calls across multiple rounds to gather comprehensive information
- Each round is a separate API call where you can reason about previous results
- Maximum 2 rounds of tool usage, then synthesis of results

Tool Usage Guidelines:
- **Content search tool**: Use for questions about specific course content or detailed educational materials
- **Course outline tool**: Use for questions about course structure, lesson lists, or course overview
- **Strategic tool usage**: Consider if you need multiple searches to fully answer complex queries
- Synthesize tool results into accurate, fact-based responses
- If tools yield no results, state this clearly without offering alternatives

Multi-Round Examples:
- "Compare course A with course B" → Round 1: Search course A, Round 2: Search course B
- "What's the difference between lesson 1 and lesson 3?" → Search each lesson separately
- "Show me content from both Introduction and Advanced courses" → Search each course

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching  
- **Course content questions**: Use content search tool first, then answer
- **Course outline/structure questions**: Use outline tool to get course title, course link, and complete lesson information
- **No meta-commentary**: Provide direct answers only — no reasoning process, search explanations, or question-type analysis

Tool Selection:
- For "what lessons are in...", "course outline", "what's covered in...", "lesson list" → use outline tool
- For specific content, explanations, detailed information → use content search tool

All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value  
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""
    
    def __init__(self, api_key: str, model: str, max_rounds: int = 2):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_rounds = max_rounds
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }
        
        # Initialize pipeline
        self.orchestrator = PipelineOrchestrator()
        self._setup_processors()
    
    def _setup_processors(self):
        """Setup all pipeline processors"""
        self.orchestrator.register_processor(
            RoundState.INITIAL_QUERY, 
            InitialQueryProcessor(self.base_params)
        )
        self.orchestrator.register_processor(
            RoundState.FIRST_TOOL_ROUND, 
            SequentialToolProcessor(self.base_params)
        )
        self.orchestrator.register_processor(
            RoundState.SECOND_TOOL_ROUND, 
            SequentialToolProcessor(self.base_params)
        )
        self.orchestrator.register_processor(
            RoundState.SYNTHESIS_ROUND, 
            SynthesisProcessor(self.base_params)
        )
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response using pipeline architecture.
        
        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools
            
        Returns:
            Generated response as string
        """
        
        # Build system content
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history 
            else self.SYSTEM_PROMPT
        )
        
        # Initialize pipeline context
        context = RoundContext(
            original_query=query,
            conversation_history=conversation_history,
            system_prompt=system_content,
            max_rounds=self.max_rounds
        )
        
        # Execute pipeline
        if tools and tool_manager:
            context = self.orchestrator.execute_pipeline(context, self.client, tools, tool_manager)
            
            # Extract sources from tool manager
            if hasattr(tool_manager, 'get_last_sources'):
                context.sources = tool_manager.get_last_sources()
        else:
            # No tools available - direct response
            api_params = {
                **self.base_params,
                "messages": [{"role": "user", "content": query}],
                "system": system_content
            }
            response = self.client.messages.create(**api_params)
            context.final_response = response.content[0].text
            context.current_state = RoundState.COMPLETED
        
        # Handle final result
        if context.current_state == RoundState.COMPLETED and context.final_response:
            return context.final_response
        elif context.errors:
            error_summary = "; ".join(context.errors)
            logger.error(f"Pipeline failed: {error_summary}")
            return f"I encountered an error processing your request: {error_summary}"
        else:
            return "I was unable to process your request. Please try again."
    
    def get_pipeline_context(self) -> Dict[str, Any]:
        """Get pipeline configuration for debugging/monitoring"""
        return {
            "max_rounds": self.max_rounds,
            "registered_processors": list(self.orchestrator.processors.keys()),
            "state_transitions": self.orchestrator.state_transitions
        }