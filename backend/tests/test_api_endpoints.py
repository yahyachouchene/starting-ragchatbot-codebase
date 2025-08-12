import pytest
import json
from unittest.mock import Mock, patch
from fastapi import HTTPException


class TestQueryEndpoint:
    """Test cases for /api/query endpoint"""

    def test_query_with_session_id(self, test_client, sample_query_data):
        """Test query endpoint with provided session ID"""
        query_data = sample_query_data["valid_query"]
        
        response = test_client.post("/api/query", json=query_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "answer" in data
        assert "sources" in data
        assert "session_id" in data
        assert data["session_id"] == query_data["session_id"]
        assert isinstance(data["sources"], list)

    def test_query_without_session_id(self, test_client, sample_query_data):
        """Test query endpoint without session ID (should create one)"""
        query_data = sample_query_data["query_without_session"]
        
        response = test_client.post("/api/query", json=query_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "answer" in data
        assert "sources" in data
        assert "session_id" in data
        assert data["session_id"] is not None
        assert len(data["session_id"]) > 0

    def test_query_empty_query(self, test_client, sample_query_data):
        """Test query endpoint with empty query"""
        query_data = sample_query_data["empty_query"]
        
        response = test_client.post("/api/query", json=query_data)
        
        # Should still work, as the RAG system should handle empty queries
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data

    def test_query_invalid_json(self, test_client):
        """Test query endpoint with invalid JSON"""
        response = test_client.post("/api/query", data="invalid json")
        
        assert response.status_code == 422  # Validation error

    def test_query_missing_required_field(self, test_client):
        """Test query endpoint with missing required query field"""
        response = test_client.post("/api/query", json={"session_id": "test"})
        
        assert response.status_code == 422  # Validation error

    def test_query_rag_system_error(self, test_client, mock_rag_system):
        """Test query endpoint when RAG system raises an exception"""
        # Configure mock to raise an exception
        mock_rag_system.query.side_effect = Exception("RAG system error")
        
        response = test_client.post("/api/query", json={
            "query": "test query",
            "session_id": "test_session"
        })
        
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "RAG system error" in data["detail"]

    def test_query_response_structure(self, test_client, sample_query_data):
        """Test that query response has the correct structure"""
        query_data = sample_query_data["valid_query"]
        
        response = test_client.post("/api/query", json=query_data)
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure matches QueryResponse model
        assert isinstance(data["answer"], str)
        assert isinstance(data["sources"], list)
        assert isinstance(data["session_id"], str)
        
        # Check sources structure
        for source in data["sources"]:
            if isinstance(source, dict):
                assert "text" in source
                # link is optional

    def test_query_with_special_characters(self, test_client):
        """Test query with special characters and unicode"""
        special_query = {
            "query": "What is 机器学习? Explain émotions & symbols!@#$%",
            "session_id": "special_test"
        }
        
        response = test_client.post("/api/query", json=special_query)
        
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data

    def test_query_long_input(self, test_client):
        """Test query with very long input"""
        long_query = {
            "query": "What is machine learning? " * 1000,  # Very long query
            "session_id": "long_test"
        }
        
        response = test_client.post("/api/query", json=long_query)
        
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data


class TestCoursesEndpoint:
    """Test cases for /api/courses endpoint"""

    def test_get_courses_success(self, test_client):
        """Test successful retrieval of course statistics"""
        response = test_client.get("/api/courses")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "total_courses" in data
        assert "course_titles" in data
        assert isinstance(data["total_courses"], int)
        assert isinstance(data["course_titles"], list)

    def test_get_courses_structure(self, test_client):
        """Test that courses response matches CourseStats model"""
        response = test_client.get("/api/courses")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure matches CourseStats model
        assert data["total_courses"] >= 0
        assert all(isinstance(title, str) for title in data["course_titles"])

    def test_get_courses_rag_system_error(self, test_client, mock_rag_system):
        """Test courses endpoint when RAG system raises an exception"""
        # Configure mock to raise an exception
        mock_rag_system.get_course_analytics.side_effect = Exception("Analytics error")
        
        response = test_client.get("/api/courses")
        
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "Analytics error" in data["detail"]


class TestSessionClearEndpoint:
    """Test cases for /api/sessions/{session_id}/clear endpoint"""

    def test_clear_session_success(self, test_client):
        """Test successful session clearing"""
        session_id = "test_session_123"
        
        response = test_client.delete(f"/api/sessions/{session_id}/clear")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "session_id" in data
        assert data["session_id"] == session_id
        assert "cleared successfully" in data["message"].lower()

    def test_clear_session_with_special_characters(self, test_client):
        """Test session clearing with special characters in session ID"""
        session_id = "test-session_123!@#"
        
        response = test_client.delete(f"/api/sessions/{session_id}/clear")
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

    def test_clear_session_error(self, test_client, mock_rag_system):
        """Test session clearing when session manager raises an exception"""
        # Configure mock to raise an exception
        mock_rag_system.session_manager.clear_session.side_effect = Exception("Clear error")
        
        session_id = "error_session"
        response = test_client.delete(f"/api/sessions/{session_id}/clear")
        
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "Clear error" in data["detail"]


class TestRootEndpoint:
    """Test cases for / (root) endpoint"""

    def test_root_endpoint_success(self, test_client):
        """Test root endpoint returns correct response"""
        response = test_client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "RAG System" in data["message"]

    def test_root_endpoint_method_not_allowed(self, test_client):
        """Test that POST to root endpoint is not allowed"""
        response = test_client.post("/")
        
        assert response.status_code == 405  # Method not allowed


class TestEndpointIntegration:
    """Integration tests for API endpoints"""

    def test_query_then_clear_session_flow(self, test_client, sample_query_data):
        """Test the flow of making a query then clearing the session"""
        # First, make a query
        query_data = sample_query_data["valid_query"]
        session_id = query_data["session_id"]
        
        query_response = test_client.post("/api/query", json=query_data)
        assert query_response.status_code == 200
        
        query_data = query_response.json()
        assert query_data["session_id"] == session_id
        
        # Then clear the session
        clear_response = test_client.delete(f"/api/sessions/{session_id}/clear")
        assert clear_response.status_code == 200
        
        clear_data = clear_response.json()
        assert clear_data["session_id"] == session_id

    def test_multiple_queries_same_session(self, test_client):
        """Test multiple queries with the same session ID"""
        session_id = "persistent_session"
        
        # First query
        response1 = test_client.post("/api/query", json={
            "query": "What is machine learning?",
            "session_id": session_id
        })
        assert response1.status_code == 200
        
        # Second query with same session
        response2 = test_client.post("/api/query", json={
            "query": "Tell me more about supervised learning",
            "session_id": session_id
        })
        assert response2.status_code == 200
        
        # Both should have the same session ID
        data1 = response1.json()
        data2 = response2.json()
        assert data1["session_id"] == session_id
        assert data2["session_id"] == session_id

    def test_query_courses_endpoints_consistency(self, test_client):
        """Test consistency between query and courses endpoints"""
        # Get course statistics
        courses_response = test_client.get("/api/courses")
        assert courses_response.status_code == 200
        courses_data = courses_response.json()
        
        # Make a query about courses
        query_response = test_client.post("/api/query", json={
            "query": "What courses are available?",
            "session_id": "consistency_test"
        })
        assert query_response.status_code == 200
        
        # Both should work without errors
        assert courses_data["total_courses"] >= 0
        assert len(courses_data["course_titles"]) >= 0


class TestEndpointValidation:
    """Test request validation for all endpoints"""

    def test_query_endpoint_validation(self, test_client):
        """Test validation for query endpoint"""
        # Test with None query
        response = test_client.post("/api/query", json={"query": None})
        assert response.status_code == 422
        
        # Test with non-string query
        response = test_client.post("/api/query", json={"query": 123})
        assert response.status_code == 422
        
        # Test with extra fields (should be ignored or accepted)
        response = test_client.post("/api/query", json={
            "query": "test",
            "extra_field": "should be ignored"
        })
        # Should either work (extra fields ignored) or fail validation
        assert response.status_code in [200, 422]

    def test_session_id_validation(self, test_client):
        """Test session ID validation in various endpoints"""
        # Test clearing non-existent session (should not fail)
        response = test_client.delete("/api/sessions/non_existent_session/clear")
        assert response.status_code == 200
        
        # Test with empty session ID in URL
        response = test_client.delete("/api/sessions//clear")
        # This might be a 404 or 422 depending on FastAPI routing
        assert response.status_code in [404, 422]