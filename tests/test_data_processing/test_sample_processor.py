"""
Tests for SampleDataProcessor class.
"""

import pytest
import pandas as pd
import tempfile
import yaml
from unittest.mock import patch, MagicMock
from bioforklift.data_processing import SampleDataProcessor


@pytest.fixture
def sample_schema_yaml():
    """Create a temporary YAML schema file for testing"""
    schema_content = {
        "fields": {
            "id": {
                "type": "string",
                "required": True,
                "primary_key": True,
                "system_value": True
            },
            "sample_id": {
                "type": "string",
                "required": True,
                "sample_identifier": True,
                "pattern": "^SMP[0-9]{4}$"
            },
            "batch_id": {
                "type": "string",
                "pattern": "^BATCH_[A-Z]{2}[0-9]{3}$"
            },
            "read1": {
                "type": "string",
                "sequence_file": True
            },
            "read2": {
                "type": "string",
                "sequence_file": True
            },
            "metadata_field": {
                "type": "string",
                "column_mappings": ["source_metadata", "alt_metadata"]
            },
            "created_at": {
                "type": "datetime",
                "system_value": True
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(schema_content, f)
        return f.name


@pytest.fixture
def sample_processor(sample_schema_yaml):
    """Create a SampleDataProcessor instance for testing"""
    return SampleDataProcessor(sample_schema_yaml)


@pytest.fixture
def sample_dataframe():
    """Sample DataFrame for testing"""
    return pd.DataFrame({
        "sample_id": ["SMP0001", "SMP0002", "INVALID", "SMP0003"],
        "batch_id": ["BATCH_AB123", "BATCH_CD456", "INVALID_BATCH", "BATCH_EF789"],
        "read1": ["file1.fastq", "file2.fastq", None, "file4.fastq"],
        "read2": ["file1_r2.fastq", None, "file3_r2.fastq", "file4_r2.fastq"],
        "source_metadata": ["meta1", "meta2", "meta3", "meta4"],  # Will be mapped
        "extra_column": ["extra1", "extra2", "extra3", "extra4"]  # Will be filtered out
    })


class TestSampleDataProcessor:
    """Test the SampleDataProcessor class"""

    def test_initialization(self, sample_processor):
        """Test processor initialization"""
        assert sample_processor is not None
        assert len(sample_processor.schema) > 0
        assert len(sample_processor.field_attributes) > 0

    def test_get_sample_identifier_field(self, sample_processor):
        """Test getting sample identifier field"""
        identifier_field = sample_processor.get_sample_identifier_field()
        assert identifier_field == "sample_id"

    def test_get_sequence_file_fields(self, sample_processor):
        """Test getting sequence file fields"""
        seq_fields = sample_processor.get_sequence_file_fields()
        assert "read1" in seq_fields
        assert "read2" in seq_fields
        assert len(seq_fields) == 2

    def test_map_field_names(self, sample_processor, sample_dataframe):
        """Test field name mapping"""
        mapped_df = sample_processor._map_field_names(sample_dataframe)

        # Should have mapped source_metadata to metadata_field
        assert "metadata_field" in mapped_df.columns
        assert "source_metadata" not in mapped_df.columns

        # Values should be preserved
        assert mapped_df["metadata_field"].tolist() == ["meta1", "meta2", "meta3", "meta4"]

    def test_filter_columns(self, sample_processor):
        """Test column filtering"""
        df_with_extra = pd.DataFrame({
            "sample_id": ["SMP0001"],
            "read1": ["file1.fastq"],
            "extra_column": ["extra"],
            "another_extra": ["more_extra"]
        })

        filtered_df = sample_processor._filter_columns(df_with_extra)

        # Should keep schema fields
        assert "sample_id" in filtered_df.columns
        assert "read1" in filtered_df.columns

        # Should remove extra columns
        assert "extra_column" not in filtered_df.columns
        assert "another_extra" not in filtered_df.columns

    def test_filter_existing_samples(self, sample_processor):
        """Test filtering existing samples"""
        df = pd.DataFrame({
            "sample_id": ["SMP0001", "SMP0002", "SMP0003"],
            "read1": ["file1.fastq", "file2.fastq", "file3.fastq"]
        })

        existing_ids = {"SMP0001", "SMP0003"}
        filtered_df = sample_processor._filter_existing_samples(df, existing_ids)

        # Should only keep SMP0002
        assert len(filtered_df) == 1
        assert filtered_df.iloc[0]["sample_id"] == "SMP0002"

    def test_validate_sequence_files(self, sample_processor):
        """Test sequence file validation"""
        df = pd.DataFrame({
            "sample_id": ["SMP0001", "SMP0002", "SMP0003"],
            "read1": ["file1.fastq", None, "file3.fastq"],
            "read2": [None, None, "file3_r2.fastq"]
        })

        validated_df = sample_processor._validate_sequence_files(df)

        # Should keep samples with at least one sequence file (SMP0001, SMP0003)
        # Should filter out SMP0002 (no sequence files)
        assert len(validated_df) == 2
        assert "SMP0002" not in validated_df["sample_id"].values

    def test_validate_field_patterns(self, sample_processor):
        """Test pattern validation"""
        df = pd.DataFrame({
            "sample_id": ["SMP0001", "INVALID", "SMP0003"],
            "batch_id": ["BATCH_AB123", "INVALID_BATCH", "BATCH_CD456"]
        })

        validated_df = sample_processor._validate_field_patterns(df)

        # Should only keep rows with valid patterns (SMP0001, SMP0003)
        assert len(validated_df) == 2
        assert "INVALID" not in validated_df["sample_id"].values

    def test_add_system_values(self, sample_processor):
        """Test adding system values"""
        df = pd.DataFrame({
            "sample_id": ["SMP0001", "SMP0002"],
            "read1": ["file1.fastq", "file2.fastq"]
        })

        df_with_system = sample_processor._add_system_values(df)

        # Should have added id and created_at
        assert "id" in df_with_system.columns
        assert "created_at" in df_with_system.columns

        # IDs should be unique UUIDs
        ids = df_with_system["id"].tolist()
        assert len(set(ids)) == len(ids)  # All unique
        assert all(len(id_val) == 36 for id_val in ids)  # UUID format

    def test_process_samples_full_pipeline(self, sample_processor, sample_dataframe):
        """Test the complete processing pipeline"""
        existing_ids = {"SMP0001"}  # Will filter out first sample

        processed_df = sample_processor.process_samples(sample_dataframe, existing_ids)

        # Should have processed and filtered data
        assert len(processed_df) > 0
        assert len(processed_df) < len(sample_dataframe)

        # Should have system fields
        assert "id" in processed_df.columns
        assert "created_at" in processed_df.columns

        # Should have mapped fields
        assert "metadata_field" in processed_df.columns
        assert "source_metadata" not in processed_df.columns

        # Should not have extra columns
        assert "extra_column" not in processed_df.columns

    def test_process_samples_empty_dataframe(self, sample_processor):
        """Test processing empty DataFrame"""
        empty_df = pd.DataFrame()
        result = sample_processor.process_samples(empty_df)

        assert len(result) == 0
        assert result.equals(empty_df)

    def test_invalid_regex_pattern(self, sample_schema_yaml):
        """Test handling of invalid regex patterns"""
        # Modify schema with invalid regex
        with open(sample_schema_yaml, 'r') as f:
            schema = yaml.safe_load(f)

        schema["fields"]["sample_id"]["pattern"] = "[invalid_regex"  # Missing closing bracket

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(schema, f)
            temp_schema = f.name

        processor = SampleDataProcessor(temp_schema)

        df = pd.DataFrame({
            "sample_id": ["SMP0001"],
            "read1": ["file1.fastq"]
        })

        with pytest.raises(ValueError, match="Invalid regex pattern"):
            processor._validate_field_patterns(df)