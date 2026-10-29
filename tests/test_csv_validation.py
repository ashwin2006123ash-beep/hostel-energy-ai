import io
import pytest
from services.data_processor import validate_csv_data

def test_valid_csv_validation():
    valid_csv = """timestamp,block_id,power_kw,occupancy,temperature
2026-10-01 10:00:00,Block-A,8.5,120,27.5
2026-10-01 11:00:00,Block-A,7.2,40,29.0
"""
    result = validate_csv_data(io.StringIO(valid_csv))
    assert result["valid"] is True
    assert result["summary"]["total_rows"] == 2
    assert len(result["errors"]) == 0

def test_missing_required_columns():
    # Missing occupancy and temperature
    invalid_csv = """timestamp,block_id,power_kw
2026-10-01 10:00:00,Block-A,8.5
"""
    result = validate_csv_data(io.StringIO(invalid_csv))
    assert result["valid"] is False
    assert any("Missing required columns" in err for err in result["errors"])

def test_negative_power_rejection():
    invalid_power_csv = """timestamp,block_id,power_kw,occupancy,temperature
2026-10-01 10:00:00,Block-A,-5.2,100,28.0
"""
    result = validate_csv_data(io.StringIO(invalid_power_csv))
    assert result["valid"] is False
    assert any("Negative power" in err for err in result["errors"])

def test_invalid_timestamp_rejection():
    invalid_ts_csv = """timestamp,block_id,power_kw,occupancy,temperature
not-a-real-date,Block-A,6.2,100,28.0
"""
    result = validate_csv_data(io.StringIO(invalid_ts_csv))
    assert result["valid"] is False
    assert any("invalid timestamp format" in err for err in result["errors"])

def test_empty_file_rejection():
    empty_csv = ""
    result = validate_csv_data(io.StringIO(empty_csv))
    assert result["valid"] is False
    assert any("empty" in err for err in result["errors"])
