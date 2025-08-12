import os
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Any, Dict, List

from ai_generator import AIGenerator


class MockAnthropicResponse:
    """Mock Anthropic API response for testing"""

    def __init__(
        self,
        content_text: str = None,
        tool_use_blocks: List[Dict] = None,
        stop_reason: str = "end_turn",
    ):
        self.stop_reason = stop_reason

        # Create content blocks
        self.content = []

        if content_text:
            mock_text_block = Mock()
            mock_text_block.type = "text"
            mock_text_block.text = content_text
            self.content.append(mock_text_block)

        if tool_use_blocks:
            for tool_block in tool_use_blocks:
                mock_tool_block = Mock()
                mock_tool_block.type = "tool_use"
                mock_tool_block.name = tool_block.get("name", "search_course_content")
                mock_tool_block.input = tool_block.get("input", {})
                mock_tool_block.id = tool_block.get("id", f"tool_{len(self.content)}")
                self.content.append(mock_tool_block)


class MockToolManager:
    """Mock tool manager for testing"""

    def __init__(self):
        self.execute_calls = []
        self.last_sources = [
            {"text": "Test Course - Lesson 1", "link": "http://example.com"}
        ]

    def execute_tool(self, tool_name: str, **kwargs) -> str:
        self.execute_calls.append({"name": tool_name, "kwargs": kwargs})

        # Simulate different tool responses
        if tool_name == "search_course_content":
            query = kwargs.get("query", "")
            if "error" in query.lower():
                raise Exception("Simulated tool error")
            return f"Search result for: {query}"
        elif tool_name == "get_course_outline":
            course_name = kwargs.get("course_name", "")
            return f"Course outline for: {course_name}"

        return f"Tool {tool_name} executed with {kwargs}"


class TestAIGenerator(unittest.TestCase):
    """Test cases for AIGenerator sequential tool calling"""

    def setUp(self):
        """Set up test fixtures"""
        self.ai_generator = AIGenerator(
            api_key="test_key", model="claude-3-haiku-20240307"
        )
        self.mock_tool_manager = MockToolManager()
        self.mock_tools = [
            {
                "name": "search_course_content",
                "description": "Search course materials",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]

    @patch("anthropic.Anthropic")
    def test_single_round_backward_compatibility(self, mock_anthropic_class):
        """Test that single-round queries work unchanged (backward compatibility)"""

        # Mock the API client
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        self.ai_generator.client = mock_client

        # Set up a single response without tool use
        mock_response = MockAnthropicResponse(content_text="This is a direct answer")
        mock_client.messages.create.return_value = mock_response

        # Test the query
        result = self.ai_generator.generate_response(
            query="What is machine learning?",
            tools=self.mock_tools,
            tool_manager=self.mock_tool_manager,
        )

        # Verify single API call was made
        self.assertEqual(mock_client.messages.create.call_count, 1)

        # Verify response
        self.assertEqual(result, "This is a direct answer")

        # Verify statistics
        stats = self.ai_generator.get_call_stats()
        self.assertEqual(stats["total_queries"], 1)
        self.assertEqual(stats["multi_round_queries"], 0)

    @patch("anthropic.Anthropic")
    def test_two_round_sequential_tool_calling(self, mock_anthropic_class):
        """Test two-round sequential tool calling scenario"""

        # Mock the API client
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        self.ai_generator.client = mock_client

        # Set up responses for two rounds
        # Round 1: Tool use
        round1_response = MockAnthropicResponse(
            tool_use_blocks=[
                {
                    "name": "get_course_outline",
                    "input": {"course_name": "Course A"},
                    "id": "tool_1",
                }
            ],
            stop_reason="tool_use",
        )

        # Round 2: Another tool use
        round2_response = MockAnthropicResponse(
            tool_use_blocks=[
                {
                    "name": "search_course_content",
                    "input": {"query": "specific topic"},
                    "id": "tool_2",
                }
            ],
            stop_reason="tool_use",
        )

        # Final response: Text only
        final_response = MockAnthropicResponse(
            content_text="Based on my search, here's the comparison..."
        )

        # Configure mock to return responses in sequence
        mock_client.messages.create.side_effect = [
            round1_response,
            round2_response,
            final_response,
        ]

        # Test the query
        result = self.ai_generator.generate_response(
            query="Compare Course A with courses that cover similar topics",
            tools=self.mock_tools,
            tool_manager=self.mock_tool_manager,
        )

        # Verify three API calls were made (2 rounds + 1 final)
        self.assertEqual(mock_client.messages.create.call_count, 3)

        # Verify tools were executed
        self.assertEqual(len(self.mock_tool_manager.execute_calls), 2)
        self.assertEqual(
            self.mock_tool_manager.execute_calls[0]["name"], "get_course_outline"
        )
        self.assertEqual(
            self.mock_tool_manager.execute_calls[1]["name"], "search_course_content"
        )

        # Verify final response
        self.assertEqual(result, "Based on my search, here's the comparison...")

        # Verify statistics
        stats = self.ai_generator.get_call_stats()
        self.assertEqual(stats["total_queries"], 1)
        self.assertEqual(stats["multi_round_queries"], 1)
        self.assertEqual(stats["max_rounds_reached"], 1)

    @patch("anthropic.Anthropic")
    def test_early_termination_no_tool_use(self, mock_anthropic_class):
        """Test early termination when first round has no tool use"""

        # Mock the API client
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        self.ai_generator.client = mock_client

        # Set up response without tool use
        mock_response = MockAnthropicResponse(
            content_text="Direct answer without tools"
        )
        mock_client.messages.create.return_value = mock_response

        # Test the query
        result = self.ai_generator.generate_response(
            query="General knowledge question",
            tools=self.mock_tools,
            tool_manager=self.mock_tool_manager,
        )

        # Verify only one API call was made
        self.assertEqual(mock_client.messages.create.call_count, 1)

        # Verify no tools were executed
        self.assertEqual(len(self.mock_tool_manager.execute_calls), 0)

        # Verify response
        self.assertEqual(result, "Direct answer without tools")

        # Verify statistics
        stats = self.ai_generator.get_call_stats()
        self.assertEqual(stats["total_queries"], 1)
        self.assertEqual(stats["multi_round_queries"], 0)

    @patch("anthropic.Anthropic")
    def test_tool_execution_error_handling(self, mock_anthropic_class):
        """Test graceful handling of tool execution errors"""

        # Mock the API client
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        self.ai_generator.client = mock_client

        # Set up response with tool use that will cause an error
        tool_response = MockAnthropicResponse(
            tool_use_blocks=[
                {
                    "name": "search_course_content",
                    "input": {
                        "query": "error query"
                    },  # This will trigger an error in mock
                    "id": "tool_error",
                }
            ],
            stop_reason="tool_use",
        )

        # Final response after error
        final_response = MockAnthropicResponse(content_text="Error handled gracefully")

        mock_client.messages.create.side_effect = [tool_response, final_response]

        # Test the query
        result = self.ai_generator.generate_response(
            query="Query that will cause tool error",
            tools=self.mock_tools,
            tool_manager=self.mock_tool_manager,
        )

        # Verify two API calls were made (tool use + final after error)
        self.assertEqual(mock_client.messages.create.call_count, 2)

        # Verify response contains error handling
        self.assertEqual(result, "Error handled gracefully")

        # Verify statistics show error
        stats = self.ai_generator.get_call_stats()
        self.assertEqual(stats["tool_failures"], 1)

    @patch("anthropic.Anthropic")
    def test_context_preservation_between_rounds(self, mock_anthropic_class):
        """Test that conversation context is preserved between rounds"""

        # Mock the API client
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        self.ai_generator.client = mock_client

        # Set up conversation history
        conversation_history = (
            "Previous: User asked about Course X. Assistant: Course X covers ML basics."
        )

        # Set up responses
        round1_response = MockAnthropicResponse(
            tool_use_blocks=[
                {
                    "name": "search_course_content",
                    "input": {"query": "advanced topics"},
                    "id": "tool_1",
                }
            ],
            stop_reason="tool_use",
        )

        final_response = MockAnthropicResponse(
            content_text="Here are the advanced topics..."
        )
        mock_client.messages.create.side_effect = [round1_response, final_response]

        # Test query with conversation history
        result = self.ai_generator.generate_response(
            query="What about advanced topics in the same course?",
            conversation_history=conversation_history,
            tools=self.mock_tools,
            tool_manager=self.mock_tool_manager,
        )

        # Verify API calls include conversation history
        call_args = mock_client.messages.create.call_args_list
        for call in call_args:
            system_content = call[1]["system"]
            self.assertIn(conversation_history, system_content)

    @patch("anthropic.Anthropic")
    def test_max_rounds_enforcement(self, mock_anthropic_class):
        """Test that maximum rounds are enforced"""

        # Mock the API client
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        self.ai_generator.client = mock_client

        # Set up responses that would continue beyond max rounds
        tool_response = MockAnthropicResponse(
            tool_use_blocks=[
                {
                    "name": "search_course_content",
                    "input": {"query": "test query"},
                    "id": "tool_continuous",
                }
            ],
            stop_reason="tool_use",
        )

        # Configure mock to always return tool use
        mock_client.messages.create.return_value = tool_response

        # Test with max_rounds=1
        result = self.ai_generator.generate_response(
            query="Test query",
            tools=self.mock_tools,
            tool_manager=self.mock_tool_manager,
            max_rounds=1,
        )

        # Should stop after 1 round + final response call = 2 total calls
        self.assertEqual(mock_client.messages.create.call_count, 2)

        # Reset for testing default max_rounds=2
        mock_client.reset_mock()
        self.mock_tool_manager.execute_calls = []

        # Test with default max_rounds=2
        final_response = MockAnthropicResponse(
            content_text="Final response after 2 rounds"
        )
        mock_client.messages.create.side_effect = [
            tool_response,
            tool_response,
            final_response,
        ]

        result = self.ai_generator.generate_response(
            query="Test query",
            tools=self.mock_tools,
            tool_manager=self.mock_tool_manager,
        )

        # Should make 3 calls: 2 tool rounds + 1 final
        self.assertEqual(mock_client.messages.create.call_count, 3)
        self.assertEqual(result, "Final response after 2 rounds")

    def test_statistics_tracking(self):
        """Test that call statistics are tracked correctly"""

        # Initialize fresh generator
        generator = AIGenerator("test_key", "test_model")

        # Test initial stats
        stats = generator.get_call_stats()
        expected_initial = {
            "total_queries": 0,
            "multi_round_queries": 0,
            "tool_failures": 0,
            "max_rounds_reached": 0,
        }
        self.assertEqual(stats, expected_initial)

        # Test stats update
        generator._update_call_stats(rounds_used=2, had_errors=True, reached_max=True)
        generator.call_stats["total_queries"] += 1

        updated_stats = generator.get_call_stats()
        self.assertEqual(updated_stats["total_queries"], 1)
        self.assertEqual(updated_stats["multi_round_queries"], 1)
        self.assertEqual(updated_stats["tool_failures"], 1)
        self.assertEqual(updated_stats["max_rounds_reached"], 1)

    @patch("anthropic.Anthropic")
    def test_api_error_handling(self, mock_anthropic_class):
        """Test handling of API errors with round context"""

        # Mock the API client
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        self.ai_generator.client = mock_client

        # Configure mock to raise an exception
        mock_client.messages.create.side_effect = Exception("API connection failed")

        # Test that error is raised with round context
        with self.assertRaises(Exception) as context:
            self.ai_generator.generate_response(
                query="Test query",
                tools=self.mock_tools,
                tool_manager=self.mock_tool_manager,
            )

        # Verify error includes round information
        self.assertIn("round 1", str(context.exception))


if __name__ == "__main__":
    unittest.main()
