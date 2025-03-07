import io
import pandas as pd
from typing import Optional, List, Dict, Any
from pathlib import Path
from .utils import stream_terra_table
from .client import TerraClient
from forklift.forklift_logging import setup_logger

logger = setup_logger("terra_entities.py")

class TerraEntities:
    """Class meant to handle common data operations in Terra"""

    def __init__(self, client: TerraClient):
        self.client = client

    def download_table(
        self,
        entity_type: str,
        destination: Optional[Path] = None,
        attributes: Optional[List[str]] = None,
        model: str = "flexible",
        chunk_size: int = 8192,
        use_destination: bool = False,
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

        Returns:
            pandas DataFrame with table data
        """
        params = {"model": model}
        if attributes:
            params["attributeNames"] = ",".join(attributes)

        response = self.client._http_request(
            "GET",
            f"entities/{entity_type}/tsv",
            params=params,
            stream=True,
            use_destination=use_destination,
        )
        logger.info(f"Downloaded {entity_type} table from Terra with response; {response}")
        return stream_terra_table(
            response, destination=destination, chunk_size=chunk_size
        )

    def upload_entities(
        self,
        data: pd.DataFrame,
        target: str,
        model: str = "flexible",
        delete_empty: bool = False,
        use_destination: bool = True,
    ) -> pd.DataFrame:
        """
        Upload entities to Terra

        Args:
            data: DataFrame containing entities to upload
            target: Target entity type name
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
        first_col = upload_data.columns[0]
        base_target = target[:-3] if target.endswith("_id") else target
        target_col = f"entity:{base_target}_id"

        # Rename first column for upload
        column_mapping = {first_col: target_col}
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
        logger.info("Successfully uploaded entities to Terra")
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

        logger.info("POST new entity set to Terra")

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
            logger.info(f"PATCH request sent to update {update['attributeName']} to {update['addUpdateAttribute']}")

        return self.client.patch(
            f"entities/{entity_type}/{entity_id}",
            data=updates,
            use_destination=use_destination,
        ).json()
