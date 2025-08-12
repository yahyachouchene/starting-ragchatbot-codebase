import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""
    
    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to comprehensive tools for course information.

Tool Usage Guidelines:
- **Content search tool**: Use for questions about specific course content or detailed educational materials
- **Course outline tool**: Use for questions about course structure, lesson lists, or course overview
- **Sequential tool use**: You can make up to 2 tool calls in separate rounds to gather comprehensive information
- **Tool strategy**: Use your first tool call to gather initial information, then use a second tool call if you need additional or more specific information
- Synthesize tool results into accurate, fact-based responses
- If tools yield no results, state this clearly without offering alternatives

Sequential Tool Examples:
- First call: Search broad topic, Second call: Search specific aspect if needed
- First call: Get course outline, Second call: Search specific lesson content if needed
- First call: Search one course, Second call: Search different course for comparison

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course content questions**: Use content search tool first, then additional search if needed
- **Course outline/structure questions**: Use outline tool to get course title, course link, and complete lesson information (lesson numbers and titles)
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results" or "based on the tool results"

Tool Selection:
- For "what lessons are in...", "course outline", "what's covered in...", "lesson list" → use outline tool
- For specific content, explanations, detailed information → use content search tool
- For complex queries, consider using both tools across multiple rounds

All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""
    
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }
        
        # Track sequential calling stats for debugging
        self.call_stats = {
            "total_queries": 0,
            "multi_round_queries": 0,
            "tool_failures": 0,
            "max_rounds_reached": 0
        }
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None,
                         max_rounds: int = 2) -> str:
        """
        Generate AI response with support for up to 2 sequential tool calling rounds.
        
        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools
            max_rounds: Maximum number of tool calling rounds (default 2)
            
        Returns:
            Generated response as string
        """
        
        # Track statistics
        self.call_stats["total_queries"] += 1
        rounds_used = 0
        had_errors = False
        reached_max = False
        
        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history 
            else self.SYSTEM_PROMPT
        )
        
        # Initialize conversation messages
        messages = [{"role": "user", "content": query}]
        
        # Track rounds and execute sequential tool calling
        current_round = 0
        while current_round < max_rounds:
            current_round += 1
            rounds_used = current_round
            
            # Prepare API call parameters
            api_params = {
                **self.base_params,
                "messages": messages.copy(),
                "system": system_content
            }
            
            # Add tools if available and we haven't exceeded rounds
            if tools and current_round <= max_rounds:
                api_params["tools"] = tools
                api_params["tool_choice"] = {"type": "auto"}
            
            # Make API call
            response = self._make_api_call(api_params, current_round)
            
            # Check if we got a tool use response
            if response.stop_reason == "tool_use" and tool_manager:
                # Execute tools and prepare for next round
                messages, has_errors = self._execute_tools_and_update_messages(
                    response, messages, tool_manager, current_round
                )
                
                # Track errors
                if has_errors:
                    had_errors = True
                    break
                
                # If we've reached max rounds, exit after tool execution
                if current_round >= max_rounds:
                    reached_max = True
                    break
                    
            else:
                # No tool use - return final response
                self._update_call_stats(rounds_used, had_errors, reached_max)
                return response.content[0].text
        
        # If we exit the loop, make one final call without tools to get response
        final_response = self._make_final_response(messages, system_content)
        reached_max = True
        self._update_call_stats(rounds_used, had_errors, reached_max)
        return final_response
    
    def _execute_tools_and_update_messages(self, response, messages: List, tool_manager, round_num: int):
        """
        Execute tools from current response and update message history for next round.
        
        Args:
            response: API response containing tool use blocks
            messages: Current message history
            tool_manager: Tool execution manager
            round_num: Current round number for error tracking
            
        Returns:
            Tuple of (updated_messages, has_errors)
        """
        
        # Add AI's tool use response to messages
        messages.append({"role": "assistant", "content": response.content})
        
        # Execute all tool calls and collect results
        tool_results = []
        has_errors = False
        
        for content_block in response.content:
            if content_block.type == "tool_use":
                try:
                    tool_result = tool_manager.execute_tool(
                        content_block.name, 
                        **content_block.input
                    )
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": content_block.id,
                        "content": tool_result
                    })
                    
                except Exception as e:
                    # Handle tool execution errors gracefully
                    error_msg = f"Tool execution error in round {round_num}: {str(e)}"
                    tool_results.append({
                        "type": "tool_result", 
                        "tool_use_id": content_block.id,
                        "content": error_msg,
                        "is_error": True
                    })
                    has_errors = True
        
        # Add tool results to messages for next round
        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        
        return messages, has_errors
    
    def _make_api_call(self, api_params: Dict[str, Any], round_num: int):
        """
        Make API call with error handling and round tracking.
        
        Args:
            api_params: Parameters for the API call
            round_num: Current round number for error context
            
        Returns:
            API response object
            
        Raises:
            Exception: If API call fails after retries
        """
        try:
            return self.client.messages.create(**api_params)
        except Exception as e:
            # Add round context to error and re-raise
            raise Exception(f"API call failed in round {round_num}: {str(e)}")
    
    def _make_final_response(self, messages: List, system_content: str) -> str:
        """
        Make final API call without tools to get concluding response.
        
        Args:
            messages: Complete message history including tool results
            system_content: System prompt content
            
        Returns:
            Final response text
        """
        final_params = {
            **self.base_params,
            "messages": messages,
            "system": system_content
            # Explicitly no tools for final response
        }
        
        try:
            final_response = self.client.messages.create(**final_params)
            return final_response.content[0].text
        except Exception as e:
            return f"Error generating final response: {str(e)}"
    
    def _update_call_stats(self, rounds_used: int, had_errors: bool, reached_max: bool):
        """Update internal statistics for monitoring sequential calling behavior."""
        if rounds_used > 1:
            self.call_stats["multi_round_queries"] += 1
        if had_errors:
            self.call_stats["tool_failures"] += 1
        if reached_max:
            self.call_stats["max_rounds_reached"] += 1

    def get_call_stats(self) -> Dict[str, int]:
        """Return current call statistics for debugging."""
        return self.call_stats.copy()