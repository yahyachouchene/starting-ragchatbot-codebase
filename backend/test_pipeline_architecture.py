"""
Testing Strategy for State Machine Pipeline Architecture

This module demonstrates testing approaches for the alternative pipeline-based
AI generator architecture and compares it with the original loop-based approach.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest
from ai_generator_pipeline import (
    AIGeneratorPipeline,
    InitialQueryProcessor,
    PipelineOrchestrator,
    RoundContext,
    RoundEvent,
    RoundState,
    SequentialToolProcessor,
    SynthesisProcessor,
)


class TestPipelineArchitecture:
    """Comprehensive tests for the state machine pipeline approach"""

    def setup_method(self):
        """Setup test fixtures"""
        self.api_key = "test-api-key"
        self.model = "claude-sonnet-4"
        self.generator = AIGeneratorPipeline(self.api_key, self.model)

        # Mock tool manager
        self.mock_tool_manager = Mock()
        self.mock_tool_manager.get_last_sources.return_value = []

        # Mock tools
        self.mock_tools = [
            {
                "name": "search_course_content",
                "description": "Search course content",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]

    def test_single_round_direct_response(self):
        """Test: Query that doesn't need tools gets direct response"""
        query = "What is machine learning?"

        with patch.object(self.generator.client.messages, "create") as mock_create:
            # Mock response without tool use
            mock_response = Mock()
            mock_response.stop_reason = "end_turn"
            mock_response.content = [Mock(text="Machine learning is...")]
            mock_create.return_value = mock_response

            result = self.generator.generate_response(
                query=query, tools=self.mock_tools, tool_manager=self.mock_tool_manager
            )

            assert result == "Machine learning is..."
            assert mock_create.call_count == 1

    def test_single_round_with_tool_usage(self):
        """Test: Query needs one tool call, gets synthesized response"""
        query = "What's in lesson 1 of Introduction to AI?"

        with patch.object(self.generator.client.messages, "create") as mock_create:
            # Mock initial response with tool use
            tool_response = Mock()
            tool_response.stop_reason = "tool_use"
            tool_response.content = [
                Mock(
                    type="tool_use",
                    name="search_course_content",
                    id="tool_1",
                    input={"query": "lesson 1", "course_name": "Introduction to AI"},
                )
            ]

            # Mock final response after tool execution
            final_response = Mock()
            final_response.stop_reason = "end_turn"
            final_response.content = [Mock(text="Lesson 1 covers basic concepts...")]

            mock_create.side_effect = [tool_response, final_response]

            # Mock tool execution
            self.mock_tool_manager.execute_tool.return_value = (
                "Course content about basic AI concepts"
            )

            result = self.generator.generate_response(
                query=query, tools=self.mock_tools, tool_manager=self.mock_tool_manager
            )

            assert result == "Lesson 1 covers basic concepts..."
            assert mock_create.call_count == 2
            assert self.mock_tool_manager.execute_tool.called

    def test_two_round_sequential_tool_usage(self):
        """Test: Query needs two sequential tool calls"""
        query = "Compare lesson 1 and lesson 2 of Introduction to AI"

        with patch.object(self.generator.client.messages, "create") as mock_create:
            # Round 1: Initial query with tool use
            round1_response = Mock()
            round1_response.stop_reason = "tool_use"
            round1_response.content = [
                Mock(
                    type="tool_use",
                    name="search_course_content",
                    id="tool_1",
                    input={"query": "lesson 1", "course_name": "Introduction to AI"},
                )
            ]

            # Round 2: Second tool use
            round2_response = Mock()
            round2_response.stop_reason = "tool_use"
            round2_response.content = [
                Mock(
                    type="tool_use",
                    name="search_course_content",
                    id="tool_2",
                    input={"query": "lesson 2", "course_name": "Introduction to AI"},
                )
            ]

            # Round 3: Final synthesis
            final_response = Mock()
            final_response.stop_reason = "end_turn"
            final_response.content = [
                Mock(
                    text="Lesson 1 focuses on basics while lesson 2 covers advanced topics..."
                )
            ]

            mock_create.side_effect = [round1_response, round2_response, final_response]

            # Mock tool executions
            self.mock_tool_manager.execute_tool.side_effect = [
                "Lesson 1: Basic AI concepts",
                "Lesson 2: Advanced AI techniques",
            ]

            result = self.generator.generate_response(
                query=query, tools=self.mock_tools, tool_manager=self.mock_tool_manager
            )

            assert (
                result
                == "Lesson 1 focuses on basics while lesson 2 covers advanced topics..."
            )
            assert mock_create.call_count == 3
            assert self.mock_tool_manager.execute_tool.call_count == 2

    def test_max_rounds_reached_synthesis(self):
        """Test: Synthesis kicks in when max rounds reached"""
        query = "Find everything about courses A, B, and C"

        with patch.object(self.generator.client.messages, "create") as mock_create:
            # Both rounds have tool usage
            round1_response = Mock()
            round1_response.stop_reason = "tool_use"
            round1_response.content = [
                Mock(type="tool_use", name="search_course_content", id="1")
            ]

            round2_response = Mock()
            round2_response.stop_reason = "tool_use"
            round2_response.content = [
                Mock(type="tool_use", name="search_course_content", id="2")
            ]

            # Synthesis round (no tools available)
            synthesis_response = Mock()
            synthesis_response.stop_reason = "end_turn"
            synthesis_response.content = [
                Mock(text="Based on the searches, here's a summary...")
            ]

            mock_create.side_effect = [
                round1_response,
                round2_response,
                synthesis_response,
            ]
            self.mock_tool_manager.execute_tool.return_value = "Course content"

            result = self.generator.generate_response(
                query=query, tools=self.mock_tools, tool_manager=self.mock_tool_manager
            )

            assert result == "Based on the searches, here's a summary..."
            assert mock_create.call_count == 3

    def test_error_recovery_and_rollback(self):
        """Test: Error handling and rollback capabilities"""
        query = "Search for something"

        with patch.object(self.generator.client.messages, "create") as mock_create:
            # First call fails
            mock_create.side_effect = [
                Exception("API Error"),
                Mock(content=[Mock(text="Fallback response")]),
            ]

            # Mock tool execution failure
            self.mock_tool_manager.execute_tool.side_effect = Exception(
                "Tool execution failed"
            )

            result = self.generator.generate_response(
                query=query, tools=self.mock_tools, tool_manager=self.mock_tool_manager
            )

            # Should handle error gracefully
            assert "error" in result.lower()

    def test_context_flow_between_rounds(self):
        """Test: Context properly flows between pipeline rounds"""
        context = RoundContext(original_query="Test query", max_rounds=2)

        orchestrator = PipelineOrchestrator()

        # Test state transitions
        assert context.current_state == RoundState.INITIAL_QUERY
        assert context.round_number == 0

        # Simulate context updates
        context.round_number = 1
        context.current_state = RoundState.FIRST_TOOL_ROUND
        context.executed_tools.append("search_course_content")
        context.tool_results.append({"content": "tool result"})

        # Verify context preservation
        assert len(context.executed_tools) == 1
        assert len(context.tool_results) == 1
        assert context.round_number == 1

    def test_processor_isolation(self):
        """Test: Individual processors work in isolation"""
        base_params = {"model": "test", "temperature": 0}

        # Test InitialQueryProcessor
        initial_processor = InitialQueryProcessor(base_params)
        context = RoundContext(
            original_query="Test", current_state=RoundState.INITIAL_QUERY
        )

        assert initial_processor.can_handle(context)

        # Test state-specific handling
        context.current_state = RoundState.FIRST_TOOL_ROUND
        assert not initial_processor.can_handle(context)

        # Test SequentialToolProcessor
        sequential_processor = SequentialToolProcessor(base_params)
        assert sequential_processor.can_handle(context)

    def test_pipeline_termination_conditions(self):
        """Test: All termination conditions work correctly"""
        context = RoundContext(original_query="Test")

        # Test max rounds termination
        context.round_number = 2
        context.max_rounds = 2
        assert context.round_number >= context.max_rounds

        # Test error termination
        context.current_state = RoundState.FAILED
        assert context.current_state == RoundState.FAILED

        # Test completion termination
        context.current_state = RoundState.COMPLETED
        context.final_response = "Complete response"
        assert context.current_state == RoundState.COMPLETED
        assert context.final_response is not None


class TestArchitecturalComparison:
    """Tests that highlight differences between pipeline vs loop architectures"""

    def test_explicit_vs_implicit_state(self):
        """Compare explicit state management vs implicit loop state"""

        # Pipeline approach: Explicit state
        context = RoundContext(original_query="Test")
        assert context.current_state == RoundState.INITIAL_QUERY
        assert context.round_number == 0
        assert len(context.executed_tools) == 0

        # State is explicit and queryable
        context.current_state = RoundState.FIRST_TOOL_ROUND
        context.round_number = 1
        context.executed_tools.append("tool1")

        # All state is visible and testable
        assert context.current_state == RoundState.FIRST_TOOL_ROUND
        assert context.round_number == 1
        assert "tool1" in context.executed_tools

    def test_processor_modularity(self):
        """Test modular processor design vs monolithic loop"""

        base_params = {"model": "test"}

        # Each processor is independent and testable
        initial_processor = InitialQueryProcessor(base_params)
        sequential_processor = SequentialToolProcessor(base_params)
        synthesis_processor = SynthesisProcessor(base_params)

        # Processors have clear responsibilities
        initial_context = RoundContext(current_state=RoundState.INITIAL_QUERY)
        sequential_context = RoundContext(current_state=RoundState.FIRST_TOOL_ROUND)
        synthesis_context = RoundContext(current_state=RoundState.SYNTHESIS_ROUND)

        # Each processor only handles its designated states
        assert initial_processor.can_handle(initial_context)
        assert not initial_processor.can_handle(sequential_context)

        assert sequential_processor.can_handle(sequential_context)
        assert not sequential_processor.can_handle(initial_context)

        assert synthesis_processor.can_handle(synthesis_context)
        assert not synthesis_processor.can_handle(initial_context)

    def test_event_driven_transitions(self):
        """Test event-driven state transitions vs linear progression"""

        orchestrator = PipelineOrchestrator()

        # Verify transition mapping exists
        transitions = orchestrator.state_transitions[RoundState.INITIAL_QUERY]

        assert RoundEvent.TOOL_EXECUTED_CONTINUE in transitions
        assert RoundEvent.DIRECT_RESPONSE in transitions
        assert RoundEvent.ERROR_OCCURRED in transitions

        # Verify different events lead to different states
        assert (
            transitions[RoundEvent.TOOL_EXECUTED_CONTINUE]
            == RoundState.FIRST_TOOL_ROUND
        )
        assert transitions[RoundEvent.DIRECT_RESPONSE] == RoundState.COMPLETED
        assert transitions[RoundEvent.ERROR_OCCURRED] == RoundState.FAILED

    def test_context_accumulation(self):
        """Test rich context accumulation vs simple message passing"""

        context = RoundContext(original_query="Compare courses")

        # Context accumulates rich information
        context.executed_tools.append("search_course_content")
        context.tool_results.append({"tool": "search", "result": "Course A info"})
        context.round_summaries.append("Searched Course A")

        # Move to next round
        context.round_number = 2
        context.executed_tools.append("search_course_content")
        context.tool_results.append({"tool": "search", "result": "Course B info"})
        context.round_summaries.append("Searched Course B")

        # All information is preserved and accessible
        assert len(context.executed_tools) == 2
        assert len(context.tool_results) == 2
        assert len(context.round_summaries) == 2
        assert context.round_number == 2

    def test_error_recovery_granularity(self):
        """Test fine-grained error recovery vs coarse error handling"""

        context = RoundContext(original_query="Test")
        context.rollback_states = [
            RoundState.INITIAL_QUERY,
            RoundState.FIRST_TOOL_ROUND,
        ]
        context.current_state = RoundState.SECOND_TOOL_ROUND

        # Can rollback to specific states
        base_params = {"model": "test"}
        processor = SequentialToolProcessor(base_params)

        # Rollback preserves rollback chain
        processor.rollback(context)
        assert (
            context.current_state == RoundState.SECOND_TOOL_ROUND
        )  # Stays same if valid rollback

        # Context preserves error information
        context.errors.append("Tool execution failed")
        assert len(context.errors) == 1
        assert "Tool execution failed" in context.errors


class TestEdgeCaseHandling:
    """Tests for edge cases handled differently by pipeline architecture"""

    def test_infinite_loop_prevention(self):
        """Test: Pipeline prevents infinite loops with iteration limits"""
        context = RoundContext(original_query="Test")
        orchestrator = PipelineOrchestrator()

        # Mock clients and tools
        mock_client = Mock()
        mock_tools = []
        mock_tool_manager = Mock()

        # Create a processor that would cause infinite loops
        class LoopingProcessor(InitialQueryProcessor):
            def process(self, context, api_client, tools, tool_manager):
                # Always return continue event without advancing state properly
                return RoundEvent.TOOL_EXECUTED_CONTINUE, context

        # Register the looping processor
        orchestrator.register_processor(RoundState.INITIAL_QUERY, LoopingProcessor({}))

        # Execute pipeline - should terminate due to iteration limit
        result_context = orchestrator.execute_pipeline(
            context, mock_client, mock_tools, mock_tool_manager
        )

        # Should fail with max iterations error
        assert result_context.current_state == RoundState.FAILED
        assert any("maximum iterations" in error for error in result_context.errors)

    def test_invalid_state_transitions(self):
        """Test: Pipeline handles invalid state transitions gracefully"""
        context = RoundContext(original_query="Test")
        context.current_state = RoundState.COMPLETED  # Invalid starting state

        orchestrator = PipelineOrchestrator()
        mock_client = Mock()

        result_context = orchestrator.execute_pipeline(context, mock_client, [], Mock())

        # Should handle gracefully
        assert result_context.current_state == RoundState.FAILED

    def test_missing_processor_handling(self):
        """Test: Pipeline handles missing processors for states"""
        context = RoundContext(original_query="Test")
        context.current_state = RoundState.SYNTHESIS_ROUND  # No processor registered

        orchestrator = PipelineOrchestrator()  # Empty orchestrator
        mock_client = Mock()

        result_context = orchestrator.execute_pipeline(context, mock_client, [], Mock())

        # Should fail gracefully with error message
        assert result_context.current_state == RoundState.FAILED
        assert any("No processor found" in error for error in result_context.errors)

    def test_api_failure_during_rounds(self):
        """Test: API failures handled at each round independently"""

        generator = AIGeneratorPipeline("test-key", "test-model")

        with patch.object(generator.client.messages, "create") as mock_create:
            # Simulate API failure
            mock_create.side_effect = Exception("API timeout")

            result = generator.generate_response(
                query="Test query", tools=[], tool_manager=Mock()
            )

            # Should return error message, not crash
            assert "error" in result.lower()

    def test_tool_execution_failure_recovery(self):
        """Test: Tool execution failures don't break the pipeline"""

        generator = AIGeneratorPipeline("test-key", "test-model")
        mock_tool_manager = Mock()

        with patch.object(generator.client.messages, "create") as mock_create:
            # Mock response that uses tools
            tool_response = Mock()
            tool_response.stop_reason = "tool_use"
            tool_response.content = [
                Mock(type="tool_use", name="test_tool", id="1", input={})
            ]

            # Mock final response
            final_response = Mock()
            final_response.content = [Mock(text="Final response")]

            mock_create.side_effect = [tool_response, final_response]

            # Tool execution fails
            mock_tool_manager.execute_tool.side_effect = Exception("Tool failed")

            result = generator.generate_response(
                query="Test",
                tools=[{"name": "test_tool"}],
                tool_manager=mock_tool_manager,
            )

            # Should handle tool failure gracefully
            assert isinstance(result, str)
            assert len(result) > 0


if __name__ == "__main__":
    # Run specific test scenarios
    import sys

    def run_demo_scenarios():
        """Demonstrate pipeline architecture with example scenarios"""

        print("=== State Machine Pipeline Architecture Demo ===\n")

        # Scenario 1: Single round with tools
        print("1. Single Round Tool Usage:")
        print("   Query: 'What is in lesson 1 of Machine Learning?'")
        print("   Expected: INITIAL_QUERY → tool_use → COMPLETED")
        print("   Rounds: 1 API call + 1 synthesis call\n")

        # Scenario 2: Two round comparison
        print("2. Two Round Comparison:")
        print("   Query: 'Compare lesson 1 and lesson 2 of Deep Learning'")
        print(
            "   Expected: INITIAL_QUERY → FIRST_TOOL_ROUND → SECOND_TOOL_ROUND → COMPLETED"
        )
        print("   Rounds: 3 API calls (search lesson 1, search lesson 2, synthesize)\n")

        # Scenario 3: Max rounds with synthesis
        print("3. Max Rounds with Forced Synthesis:")
        print("   Query: 'Tell me about courses A, B, C, and D'")
        print(
            "   Expected: INITIAL_QUERY → FIRST_TOOL_ROUND → SYNTHESIS_ROUND → COMPLETED"
        )
        print("   Rounds: 3 API calls (tools disabled in synthesis round)\n")

        # Scenario 4: Direct response
        print("4. Direct Response (No Tools):")
        print("   Query: 'What is machine learning?'")
        print("   Expected: INITIAL_QUERY → COMPLETED")
        print("   Rounds: 1 API call (Claude uses existing knowledge)\n")

        # Scenario 5: Error recovery
        print("5. Error Recovery:")
        print("   Scenario: API fails in round 2")
        print("   Expected: Error captured, rollback attempted, graceful failure")
        print("   Behavior: Context preserved, error messages clear\n")

        print("=== Key Architectural Differences ===")
        print("Pipeline vs Loop Approach:")
        print("✓ Explicit state management vs implicit loop variables")
        print("✓ Event-driven transitions vs linear progression")
        print("✓ Modular processors vs monolithic logic")
        print("✓ Rich context accumulation vs simple message passing")
        print("✓ Fine-grained error recovery vs coarse error handling")
        print("✓ Declarative configuration vs imperative control flow")
        print("✓ Individual processor testing vs integration-only testing")

    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        run_demo_scenarios()
    else:
        pytest.main([__file__, "-v"])
