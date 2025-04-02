import pandas as pd
import pytest
from unittest.mock import MagicMock, patch
from google.cloud import storage
from forklift.file_transfers.gcs_transfer import GCSTransferClient

class TestGCSTransferClient:
    """Tests for the GCSTransferClient class"""
    
    @pytest.fixture
    def mock_storage_client(self):
        """Create a mock storage client"""
        mock_client = MagicMock(spec=storage.Client)
        with patch('google.cloud.storage.Client', return_value=mock_client):
            yield mock_client
    
    @pytest.fixture
    def test_dataframe(self):
        """Create a test dataframe with sequence file paths"""
        return pd.DataFrame({
            'id': ['sample1', 'sample2', 'sample3'],
            'read1': [
                'gs://source-bucket/path/to/file1.fastq.gz',
                'gs://source-bucket/path/to/file2.fastq.gz',
                'gs://source-bucket/path/to/file3.fastq.gz'
            ],
            'read2': [
                'gs://source-bucket/path/to/file1_r2.fastq.gz',
                'gs://source-bucket/path/to/file2_r2.fastq.gz',
                'gs://source-bucket/path/to/file3_r2.fastq.gz'
            ],
            'other_column': [1, 2, 3]
        })
    
    def test_init_with_bucket_name(self, mock_storage_client):
        """Test initialization with a simple bucket name"""
        client = GCSTransferClient('test-bucket')
        
        assert client.bucket_name == 'test-bucket'
        assert client.folder_prefix == ''
        assert client.max_workers == 8
        
    def test_init_with_gs_path(self, mock_storage_client):
        """Test initialization with a full gs:// path"""
        client = GCSTransferClient('gs://test-bucket/folder/path')
        
        assert client.bucket_name == 'test-bucket'
        assert client.folder_prefix == 'folder/path/'
        assert client.max_workers == 8
    
    def test_parse_gcs_path(self, mock_storage_client):
        """Test parsing GCS paths into bucket and object components"""
        client = GCSTransferClient('test-bucket')
        
        # Test with full path
        bucket, obj = client._parse_gcs_path('gs://some-bucket/path/to/file.txt')
        assert bucket == 'some-bucket'
        assert obj == 'path/to/file.txt'
        
        # Test with just bucket
        bucket, obj = client._parse_gcs_path('gs://some-bucket')
        assert bucket == 'some-bucket'
        assert obj == ''
        
        # Test with invalid path
        with pytest.raises(ValueError):
            client._parse_gcs_path('not-a-gs-path')
    
    @patch('concurrent.futures.ThreadPoolExecutor')
    def test_execute_transfers(self, mock_storage_client):
        """Test executing transfers in parallel"""
        client = GCSTransferClient('test-bucket')
        
        # Mock _transfer_file to return success
        client._transfer_file = MagicMock(return_value={'success': True})
        
        # Create test transfer jobs
        transfer_jobs = [
            {'source': 'gs://source/file1.txt', 'destination': 'gs://dest/file1.txt'},
            {'source': 'gs://source/file2.txt', 'destination': 'gs://dest/file2.txt'}
        ]
        
        # Mock ThreadPoolExecutor completely
        with patch('concurrent.futures.ThreadPoolExecutor') as mock_executor_class:
            # Create a mock for the executor instance
            mock_executor = MagicMock()
            mock_executor_class.return_value.__enter__.return_value = mock_executor
            
            # Set up mock futures
            mock_futures = [MagicMock() for _ in range(len(transfer_jobs))]
            for future in mock_futures:
                future.result.return_value = {'success': True}
            
            # Make submit return the mock futures
            mock_executor.submit.side_effect = mock_futures
            
            # Make as_completed return the futures
            with patch('concurrent.futures.as_completed', return_value=mock_futures):
                # Execute transfers
                results = client._execute_transfers(transfer_jobs)
        
        # Verify results
        assert len(results) == 2
        assert all(result.get('success', False) for result in results)
    
    def test_transfer_file(self, mock_storage_client):
        """Test transferring a single file"""
        # Set up mock buckets and blobs
        mock_source_bucket = MagicMock()
        mock_dest_bucket = MagicMock()
        mock_source_blob = MagicMock()
        mock_dest_blob = MagicMock()
        
        mock_storage_client.bucket.side_effect = lambda name: {
            'source-bucket': mock_source_bucket,
            'dest-bucket': mock_dest_bucket
        }[name]
        
        mock_source_bucket.blob.return_value = mock_source_blob
        mock_dest_bucket.blob.return_value = mock_dest_blob
        
        # Create client and test transfer
        client = GCSTransferClient('dest-bucket')
        result = client._transfer_file(
            'gs://source-bucket/file.txt',
            'gs://dest-bucket/file.txt'
        )
        
        # Verify rewrite was called
        mock_dest_blob.rewrite.assert_called_once_with(mock_source_blob)
        
        # Verify result
        assert result['success'] is True
        assert result['source'] == 'gs://source-bucket/file.txt'
        assert result['destination'] == 'gs://dest-bucket/file.txt'
    
    def test_transfer_sequence_files(self, mock_storage_client, test_dataframe):
        """Test transferring sequence files from a dataframe"""
        # Set up client with mocked transfer method
        client = GCSTransferClient('dest-bucket')
        client._execute_transfers = MagicMock(return_value=[
            {'success': True, 'source': src, 'destination': dst}
            for src, dst in [
                ('gs://source-bucket/path/to/file1.fastq.gz', 'gs://dest-bucket/path/to/file1.fastq.gz'),
                ('gs://source-bucket/path/to/file2.fastq.gz', 'gs://dest-bucket/path/to/file2.fastq.gz'),
                ('gs://source-bucket/path/to/file3.fastq.gz', 'gs://dest-bucket/path/to/file3.fastq.gz'),
                ('gs://source-bucket/path/to/file1_r2.fastq.gz', 'gs://dest-bucket/path/to/file1_r2.fastq.gz'),
                ('gs://source-bucket/path/to/file2_r2.fastq.gz', 'gs://dest-bucket/path/to/file2_r2.fastq.gz'),
                ('gs://source-bucket/path/to/file3_r2.fastq.gz', 'gs://dest-bucket/path/to/file3_r2.fastq.gz')
            ]
        ])
        
        # Test transfer
        result_df = client.transfer_sequence_files(
            test_dataframe,
            ['read1', 'read2'],
            preserve_path_structure=True
        )
        
        # Verify transfer jobs were created
        transfer_call = client._execute_transfers.call_args[0][0]
        assert len(transfer_call) == 6  # 3 samples x 2 reads
        
        # Verify dataframe was updated correctly
        assert all('dest-bucket' in path for path in result_df['read1'])
        assert all('dest-bucket' in path for path in result_df['read2'])
        assert all(result_df['other_column'] == test_dataframe['other_column'])
    
    def test_transfer_sequence_files_with_empty_columns(self, mock_storage_client, test_dataframe):
        """Test transferring with non-existent columns"""
        client = GCSTransferClient('dest-bucket')
        
        # Test with empty column list
        result_df = client.transfer_sequence_files(test_dataframe, [])
        assert result_df.equals(test_dataframe)
        
        # Test with non-existent column
        result_df = client.transfer_sequence_files(test_dataframe, ['non_existent_column'])
        assert result_df.equals(test_dataframe)
    
    def test_transfer_sequence_files_without_path_structure(self, mock_storage_client, test_dataframe):
        """Test transferring sequence files without preserving path structure"""
        client = GCSTransferClient('dest-bucket')
        client._execute_transfers = MagicMock(return_value=[
            {'success': True, 'source': src, 'destination': dst}
            for src, dst in [
                ('gs://source-bucket/path/to/file1.fastq.gz', 'gs://dest-bucket/file1.fastq.gz'),
                ('gs://source-bucket/path/to/file2.fastq.gz', 'gs://dest-bucket/file2.fastq.gz'),
                ('gs://source-bucket/path/to/file3.fastq.gz', 'gs://dest-bucket/file3.fastq.gz'),
                ('gs://source-bucket/path/to/file1_r2.fastq.gz', 'gs://dest-bucket/file1_r2.fastq.gz'),
                ('gs://source-bucket/path/to/file2_r2.fastq.gz', 'gs://dest-bucket/file2_r2.fastq.gz'),
                ('gs://source-bucket/path/to/file3_r2.fastq.gz', 'gs://dest-bucket/file3_r2.fastq.gz')
            ]
        ])
        
        # Test transfer without preserving path
        result_df = client.transfer_sequence_files(
            test_dataframe,
            ['read1', 'read2'],
            preserve_path_structure=False
        )
        
        # Check that path structure was not preserved in job creation
        transfer_call = client._execute_transfers.call_args[0][0]
        for job in transfer_call:
            # Target should not contain the original path structure
            assert 'path/to' not in job['destination']
            assert '.fastq.gz' in job['destination']