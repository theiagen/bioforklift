import io
import math
import pandas as pd
from typing import Optional, List, Dict, Any
from pathlib import Path
from .utils import stream_terra_table
from .client import TerraClient
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


class TerraEntities:
    def __init__(self, client: TerraClient):
        self.client = client

    def list_entity_types(
        self,
        include_attributes: bool = False,
        use_destination: bool = False,
    ) -> List[str] | Dict[str, Any]:
        """
        Retrieve a list of entity types from the workspace

        Args:
            include_attributes: If True, returns a dictionary with entity types and their attributes
            use_destination: Whether to use destination workspace (True) or source workspace (False)

        Returns:
            If include_attributes is False, returns a list of entity type names
            If include_attributes is True, returns a dictionary with entity types and their attributes
        """
        response = self.client.get("entities", use_destination=use_destination)

        logger.info(f"Retrieved entity types from Terra workspace")

        if response.status_code != 200:
            logger.error(f"Failed to retrieve entity types: {response.text}")
            raise ValueError(f"Failed to retrieve entity types: {response.text}")

        entity_data = response.json()

        if not include_attributes:
            # Return just the entity type names
            return list(entity_data.keys())
        else:
            # Return the full entity data structure dictionary
            return entity_data
    
    def download_table(
        self,
        entity_type: str,
        destination: Optional[Path] = None,
        attributes: Optional[List[str]] = None,
        model: str = "flexible",
        chunk_size: int = 65553,
        use_destination: bool = False,
        timeout: Optional[tuple] = None,
        max_retries: int = 3,
        page_size: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Download table from Terra workspace

        Args:
            entity_type: Type of entity (e.g., 'specimen', 'sample')
            destination: Path to save TSV file
            attributes: Specific columns to download
            model: Data model type ('flexible' or 'strict')
            chunk_size: Size of chunks for streaming
            use_destination: Whether to use destination workspace (True) or source workspace (False)
            timeout: Request timeout as (connect_timeout, read_timeout) in seconds. Defaults to (30, 300)
            max_retries: Maximum number of retries for transient server errors. Defaults to 3
            page_size: If provided, uses paginated API with this page size (recommended for large tables >10k rows)

        Returns:
            pandas DataFrame with table data
        """
        
        # Use pagination if page_size is specified
        if page_size:
            return self._download_table_paginated(
                entity_type=entity_type,
                destination=destination,
                attributes=attributes,
                use_destination=use_destination,
                page_size=page_size,
                timeout=timeout,
                max_retries=max_retries,
            )

        params = {"model": model}
        if attributes:
            params["attributeNames"] = ",".join(attributes)

        response = self.client._http_request(
            "GET",
            f"entities/{entity_type}/tsv",
            params=params,
            stream=True,
            use_destination=use_destination,
            timeout=timeout,
            max_retries=max_retries,
        )
        logger.info(
            f"Downloaded {entity_type} table from Terra workspace {self.client.destination_workspace if use_destination else self.client.source_workspace}"
        )
        return stream_terra_table(
            response, destination=destination, chunk_size=chunk_size
        )

    def _download_table_paginated(
        self,
        entity_type: str,
        destination: Optional[Path] = None,
        attributes: Optional[List[str]] = None,
        use_destination: bool = False,
        page_size: int = 1000,
        timeout: Optional[tuple] = None,
        max_retries: int = 3,
    ) -> pd.DataFrame:
        """
        Download table using paginated API for large tables

        Args:
            entity_type: Type of entity (e.g., 'specimen', 'sample')
            destination: Path to save TSV file
            attributes: Specific columns to download
            use_destination: Whether to use destination workspace (True) or source workspace (False)
            page_size: Number of entities per page
            timeout: Request timeout as (connect_timeout, read_timeout) in seconds
            max_retries: Maximum number of retries for transient server errors

        Returns:
            pandas DataFrame with table data
        """
        # Get entity metadata to determine total count and available attributes
        entity_types = self.list_entity_types(
            include_attributes=True, use_destination=use_destination
        )

        if entity_type not in entity_types:
            raise ValueError(f"Entity type '{entity_type}' not found in workspace")

        entity_metadata = entity_types[entity_type]
        entity_count = entity_metadata["count"]
        entity_id_name = entity_metadata["idName"]
        all_attributes = entity_metadata["attributeNames"]

        # Determine which attributes to fetch
        if attributes:
            attribute_names = [attr for attr in all_attributes if attr in attributes]
        else:
            attribute_names = all_attributes

        # Always include the entity id
        if entity_id_name not in attribute_names:
            attribute_names.insert(0, f'entity:{entity_id_name}')

        logger.info(f"Downloading {entity_count} {entity_type}(s) using pagination")

        # Calculate number of pages
        num_pages = int(math.ceil(float(entity_count) / page_size))
        logger.info(f"Fetching {num_pages} pages with {page_size} entities per page")

        # Fetch all pages
        all_rows = []
        for page in range(1, num_pages + 1):
            logger.info(f"Fetching page {page}/{num_pages}")

            params = {
                "page": page,
                "pageSize": page_size,
                "sortDirection": "asc",
            }

            # Add fields parameter if specific attributes requested
            if attributes:
                params["fields"] = ",".join(attributes)

            # Use entityQuery endpoint for pagination
            response = self.client._http_request(
                "GET",
                f"entityQuery/{entity_type}",
                params=params,
                use_destination=use_destination,
                timeout=timeout,
                max_retries=max_retries,
            )

            page_data = response.json()
            
            # entityQuery returns a dict with "results" key
            entities = page_data.get("results", [])

            logger.info(f"Page {page} returned {len(entities)} entities")

            # Extract entity data from response
            for entity in entities:
                entity_attributes = entity.get("attributes", {})
                entity_name = entity.get("name", "")

                # Build row with entity ID and attributes
                row = {f'entity:{entity_id_name}': entity_name}
                for attr_name in attribute_names:
                    # Skip the entity ID column as it's already added above
                    if attr_name == f'entity:{entity_id_name}':
                        continue
                    # Use None instead of empty string for missing values to preserve data types
                    row[attr_name] = entity_attributes.get(attr_name)

                all_rows.append(row)

            logger.info(f"Progress: {len(all_rows)} entities fetched (page {page}/{num_pages})")

        entity_df = pd.DataFrame(all_rows, columns=attribute_names)
        

        # Save to file if destination provided
        if destination:
            logger.info(f"Writing {len(entity_df)} entities to {destination}")
            entity_df.to_csv(destination, sep="\t", index=False)

        logger.info(f"Successfully downloaded {len(entity_df)} {entity_type} entities")
        return entity_df

    def upload_entities(
        self,
        data: pd.DataFrame,
        target: str,
        entity_identifier_column: str = None,
        model: str = "flexible",
        delete_empty: bool = False,
        use_destination: bool = True,
    ) -> pd.DataFrame:
        """
        Upload entities to Terra, will use first column as entity identifier if not specified
        Otherwise will use specified column as entity identifier and preserve column order
        For Terra Upload

        Args:
            data: DataFrame containing entities to upload
            target: Target entity type name
            entity_identifier_column: Column to use as the entity identifier that target will map to (if None, uses first column)
            model: Data model type ('flexible' or 'strict')
            delete_empty: Whether to delete empty values
            use_destination: Whether to use destination workspace (True) or source workspace (False)

        Returns:
            DataFrame with uploaded entities
        """
        # Make sure DataFrame is not empty
        if len(data) == 0:
            logger.error("DataFrame has no rows")
            raise ValueError("DataFrame has no rows")

        # Create working copy
        upload_data = data.copy()

        # Get the first column name and format target column name for Terra
        base_target = target[:-3] if target.endswith("_id") else target
        target_col = f"entity:{base_target}_id"

        # Determine which column to use as the identifier
        if entity_identifier_column is not None:
            # If specified column exists, use it as the identifier
            if entity_identifier_column in upload_data.columns:
                # Create a new column order with the identifier column first for Terra
                new_columns = [entity_identifier_column] + [
                    col
                    for col in upload_data.columns
                    if col != entity_identifier_column
                ]
                # Reorder the columns
                upload_data = upload_data[new_columns]
                # Rename the first column (now the identifier column) for upload
                column_mapping = {entity_identifier_column: target_col}
                logger.info(
                    f"Using specified identifier column '{entity_identifier_column}' for upload"
                )
            else:
                logger.warning(
                    f"Specified identifier column '{entity_identifier_column}' not found. Using first column."
                )
                column_mapping = {upload_data.columns[0]: target_col}
        else:
            # Use the first column as before if no identifier column is specified
            column_mapping = {upload_data.columns[0]: target_col}
        # Rename first column for upload
        upload_data = upload_data.rename(columns=column_mapping)

        # Convert DataFrame to TSV content for upload to terra
        tsv_buffer = io.StringIO()
        upload_data.to_csv(tsv_buffer, sep="\t", index=False)
        tsv_content = tsv_buffer.getvalue()

        logger.info(f"Entities formatted for upload to {target}")

        endpoint = "flexibleImportEntities" if model == "flexible" else "importEntities"

        files = {"entities": ("entities.tsv", tsv_content, "text/tab-separated-values")}

        params = {"async": "false", "deleteEmptyValues": str(delete_empty).lower()}

        self.client.post(
            endpoint, files=files, params=params, use_destination=use_destination
        )
        logger.info(f"Successfully uploaded {len(upload_data)} entities to Terra")
        return upload_data

    def create_entity_set(
        self,
        set_name: str,
        entity_type: str,
        entities: pd.DataFrame | List[str],
        model: str = "flexible",
        use_destination: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a new entity set

        Args:
            set_name: Name for the new set
            entity_type: Type of entities in set
            entities: DataFrame or List of entity identifiers
            model: Data model type
            use_destination: Whether to use destination workspace (True) or source workspace (False)
        """
        # Convert entities to list if DataFrame
        if isinstance(entities, pd.DataFrame):
            entities = entities.iloc[:, 0].tolist()
        elif not isinstance(entities, list):
            logger.error("Entities must be a DataFrame or list")
            raise ValueError("Entities must be a DataFrame or list")

        if not entities:
            logger.error("No entities to add to set")
            raise ValueError("No entities to add to set")

        # Create set membership TSV
        membership_data = pd.DataFrame(
            {
                f"membership:{entity_type}_set_id": [set_name] * len(entities),
                entity_type: entities,
            }
        )

        # Convert to TSV string
        tsv_data = membership_data.to_csv(sep="\t", index=False)

        # Upload set
        files = {"entities": ("set.tsv", tsv_data, "text/tab-separated-values")}

        endpoint = "flexibleImportEntities" if model == "flexible" else "importEntities"

        logger.info(
            f"Posting new entity set {set_name} to Terra for {self.client.destination_workspace}"
        )

        return self.client.post(
            endpoint,
            files=files,
            params={"async": "false"},
            use_destination=use_destination,
        )

    def update_entity_attributes(
        self,
        entity_type: str,
        entity_id: str,
        attributes: Dict[str, Any],
        use_destination: bool = True,
    ) -> Dict[str, Any]:
        """
        Update attributes of an entity

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            attributes: Dictionary of attributes to update
            use_destination: Whether to destination workspace (True) or source workspace (False)
        """
        updates = [
            {
                "op": "AddUpdateAttribute",
                "attributeName": name,
                "addUpdateAttribute": value,
            }
            for name, value in attributes.items()
        ]

        for update in updates:
            logger.info(
                f"PATCH request sent to update {update['attributeName']} to {update['addUpdateAttribute']}"
            )

        return self.client.patch(
            f"entities/{entity_type}/{entity_id}",
            data=updates,
            use_destination=use_destination,
        ).json()
