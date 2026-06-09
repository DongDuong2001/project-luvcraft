import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import uuid

from app.main import app
from app.db.session import get_db
from app.models.orchestration import ResearchRun
from app.tasks.analyze import execute_analysis_job

# Create a mock session to replace the real PostgreSQL connection
mock_session = MagicMock()

def override_get_db():
    yield mock_session

# Override the FastAPI dependency so endpoints use the mock database
app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset the mock session history before each test."""
    mock_session.reset_mock()

@pytest.fixture
def client():
    """Provide the FastAPI TestClient."""
    return TestClient(app)

# --- TEST CASES ---

def test_analyze_successful_enqueue(client):
    """Test successful API behavior when Celery accepts the job."""
    class MockTask:
        id = "mock-task-id"
        
    with patch("app.main.execute_analysis_job.delay", return_value=MockTask()):
        response = client.post("/analyze?keyword=Test&days=7")
        
        assert response.status_code == 200
        assert response.json()["task_id"] == "mock-task-id"
        
        # Verify the API endpoint added the record to the mock DB
        mock_session.add.assert_called_once()
        added_run = mock_session.add.call_args[0][0]
        assert added_run.keyword == "Test"
        assert added_run.status == "pending"
        mock_session.commit.assert_called()

def test_analyze_broker_failure(client):
    """Test that the application safely marks the run as 'failed' if RabbitMQ is down."""
    with patch("app.main.execute_analysis_job.delay", side_effect=Exception("RabbitMQ connection refused")):
        response = client.post("/analyze?keyword=Test&days=7")
        assert response.status_code == 500
        assert response.json()["detail"] == "Broker enqueue failed"
        
        # Verify DB properly caught the exception and persisted 'failed'
        added_run = mock_session.add.call_args[0][0]
        assert added_run.status == "failed"
        mock_session.commit.assert_called()

def test_worker_missing_run_record():
    """Test worker behavior when the passed run_id no longer exists."""
    with patch("app.tasks.analyze.SessionLocal", return_value=mock_session):
        # Mock the query chain: db.query().filter().first() -> returns None
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        # FIX: __wrapped__ is a bound method, so 'self' is injected automatically.
        # We only need to pass the run_id parameter!
        result = execute_analysis_job.__wrapped__(str(uuid.uuid4())) 
        assert result == {"error": "Run record not found"}

def test_worker_task_failure():
    """Test worker safely updates the DB to 'failed' if scraping or LLM throws an error."""
    run_id = uuid.uuid4()
    # Create a real Python object so we can modify its attributes like the real DB would
    mock_run = ResearchRun(run_id=run_id, keyword="Test", status="pending", timeframe_start=None, timeframe_end=None)

    with patch("app.tasks.analyze.SessionLocal", return_value=mock_session):
        # Setup the mock query to return our fake run
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run

        with patch("app.tasks.analyze.asyncio.run", side_effect=Exception("Scraping error")):
            with pytest.raises(Exception, match="Scraping error"):
                # FIX: Removed the 'None' parameter
                execute_analysis_job.__wrapped__(str(run_id))
                
            # Verify the worker caught the failure and updated state
            assert mock_run.status == "failed"
            mock_session.commit.assert_called()

def test_worker_success():
    """Test the happy-path execution of a worker task."""
    run_id = uuid.uuid4()
    mock_run = ResearchRun(run_id=run_id, keyword="Test", status="pending", timeframe_start=None, timeframe_end=None)

    with patch("app.tasks.analyze.SessionLocal", return_value=mock_session):
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run

        with patch("app.tasks.analyze.asyncio.run", return_value={"mock": "data"}):
            # FIX: Removed the 'None' parameter
            result = execute_analysis_job.__wrapped__(str(run_id))
            
            assert result["status"] == "completed"
            assert result["result"] == {"mock": "data"}
            
            # Verify DB transitions properly
            assert mock_run.status == "completed"
            mock_session.commit.assert_called()