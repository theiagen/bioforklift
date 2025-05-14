import concurrent.futures
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
from google.cloud import storage
from google.oauth2 import service_account
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class GCSTransferClient:
    def __init__(
        self,
        destination_bucket: str,
        credentials: Optional[str] = None,
        max_workers: int = 8,
    ):
        """
        Initialize GCS transfer client.

        Args:
            destination_bucket: Destination bucket name
            credentials: Optional path to service account credentials JSON
            max_workers: Maximum number of concurrent transfer workers (default: 8)
        """

        if destination_bucket.startswith("gs://"):
            # Remove 'gs://' prefix
            path = destination_bucket[5:]
            # Split into bucket and folder path
            parts = path.split("/", 1)
            self.bucket_name = parts[0]
            self.folder_prefix = parts[1] + "/" if len(parts) > 1 else ""
        else:
            # Just a bucket name, no folder
            self.bucket_name = destination_bucket
            self.folder_prefix = ""

        self.max_workers = max_workers

        if credentials:
            # If explicit credentials are provided, use them
            self.credentials = service_account.Credentials.from_service_account_file(
                credentials
            )
            self.client = storage.Client(credentials=self.credentials)
        else:
            # Otherwise try to use default credentials like gsutil does
            try:
                self.client = storage.Client()
                # Test if we can access a Terra bucket
                try:
                    test_bucket = self.client.bucket(self.bucket_name)
                    test_bucket.exists()
                    logger.debug(
                        f"Successfully verified access to bucket: {self.bucket_name}"
                    )
                except Exception as access_exc:
                    logger.warning(f"Could not verify bucket access: {str(access_exc)}")
            except Exception as client_exc:
                logger.error(f"Error creating storage client: {str(client_exc)}")
                raise

        logger.info(
            f"Initialized GCS transfer client (destination: {destination_bucket})"
        )

    def _parse_gcs_path(self, path: str) -> Tuple[str, str]:
        """Parse a GCS path into bucket and object components."""
        if not path.startswith("gs://"):
            raise ValueError(f"Not a GCS path: {path}")

        # Remove 'gs://'
        path = path[5:]

        # Split into bucket and object path
        parts = path.split("/", 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

    def _execute_transfers(
        self, transfer_jobs: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Execute file transfers in parallel."""
        transfer_job_results = []

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            future_to_job = {
                executor.submit(
                    self._transfer_file, job["source"], job["destination"]
                ): job
                for job in transfer_jobs
            }

            for future in concurrent.futures.as_completed(future_to_job):
                job = future_to_job[future]
                try:
                    transfer_result = future.result()
                    logger.info(f"Transfer result: {transfer_result}")
                    transfer_job_results.append(transfer_result)
                except Exception as exc:
                    logger.error(
                        f"Transfer failed for {job['source']} to {job['destination']}: {exc}"
                    )
                    transfer_job_results.append(
                        {
                            "success": False,
                            "source": job["source"],
                            "destination": job["destination"],
                            "error": str(exc),
                        }
                    )

        return transfer_job_results

    def _transfer_file(self, source_path: str, destination_path: str) -> Dict[str, Any]:
        """Transfer a single file between GCS buckets."""
        try:
            source_bucket, source_object = self._parse_gcs_path(source_path)
            dest_bucket, dest_object = self._parse_gcs_path(destination_path)

            # Get bucket references
            source = self.client.bucket(source_bucket)
            destination = self.client.bucket(dest_bucket)

            # Get blob references
            source_blob = source.blob(source_object)
            destination_blob = destination.blob(dest_object)

            # Server side copy to avoid downloading and re-uploading
            destination_blob.rewrite(source_blob)

            return {
                "success": True,
                "source": source_path,
                "destination": destination_path,
            }

        except Exception as exc:
            return {
                "success": False,
                "source": source_path,
                "destination": destination_path,
                "error": str(exc),
            }

    def transfer_sequence_files(
        self,
        dataframe: pd.DataFrame,
        sequence_file_columns: List[str],
        preserve_path_structure: bool = False,
    ) -> pd.DataFrame:
        """
        Transfer sequence files listed in dataframe columns to destination bucket.

        Args:
            dataframe: DataFrame containing GCS file paths
            sequence_file_columns: Column names containing sequence file paths
            preserve_path_structure: If True, preserve the original path structure
                                     If False, place files directly in bucket root

        Returns:
            Updated dataframe with new file paths written to destination bucket
        """
        if not sequence_file_columns:
            return dataframe

        # Collect all file transfers to perform
        transfer_jobs = []
        # Dictionary to map source paths to destination paths, will be used for updateing dataframe
        source_to_dest_mapping = {}

        for column in sequence_file_columns:
            if column not in dataframe.columns:
                continue

            for idx, path in enumerate(dataframe[column]):
                # Skip if path is NaN or not a string or not a GCS path
                # (e.g., gs://bucket/path/to/file)
                if (
                    pd.isna(path)
                    or not isinstance(path, str)
                    or not path.startswith("gs://")
                ):
                    continue

                try:
                    # Parse source path for bucket and object
                    source_bucket, object_path = self._parse_gcs_path(path)

                    # A bit of redundancy here, but we need to ensure the destination path is correct
                    if preserve_path_structure:
                        # Preserve the full path structure
                        if self.bucket_name.startswith("gs://"):
                            destination_path = (
                                f"{self.bucket_name}/{self.folder_prefix}{object_path}"
                            )
                        else:
                            destination_path = f"gs://{self.bucket_name}/{self.folder_prefix}{object_path}"
                    else:
                        # Extract just the filename and place directly in bucket root
                        filename = object_path.split("/")[-1]
                        if self.bucket_name.startswith("gs://"):
                            destination_path = (
                                f"{self.bucket_name}/{self.folder_prefix}{filename}"
                            )
                        else:
                            destination_path = f"gs://{self.bucket_name}/{self.folder_prefix}{filename}"

                    logger.info(f"Preparing to transfer {path} to {destination_path}")

                    # Skip if already in destination bucket, don' want to duplicate
                    if source_bucket == self.bucket_name:
                        logger.warning(
                            f"Source and destination buckets are the same: {source_bucket}"
                        )
                        continue

                    transfer_jobs.append(
                        {"source": path, "destination": destination_path}
                    )

                    # Remember mapping for dataframe update
                    source_to_dest_mapping[path] = destination_path

                except ValueError:
                    logger.warning(f"Invalid GCS path: {path}")

        # Execute transfers in parallel up to max_workers
        if not transfer_jobs:
            logger.info("No transfer jobs found.")
            return dataframe
        logger.info(f"Found {len(transfer_jobs)} transfer jobs.")

        _ = self._execute_transfers(transfer_jobs)

        # Update dataframe with new paths
        updated_df = dataframe.copy()

        # For each column, update the paths using the mapping created above
        # Mapping to new paths
        for column in sequence_file_columns:
            if column in updated_df.columns:
                # 1. If the value (fp) is not NaN (pd.notna(fp)):
                #    a. Look up fp in source_to_dest_mapping dictionary
                #    b. If found, replace fp with its mapped destination path
                #    c. If not found, keep fp as is (source_to_dest_mapping.get(fp, fp))
                # 2. If the value is NaN, keep it as is (else fp)
                updated_df[column] = updated_df[column].apply(
                    lambda fp: source_to_dest_mapping.get(fp, fp)
                    if pd.notna(fp)
                    else fp
                )

        return updated_df
