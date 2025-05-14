from pathlib import Path
from typing import Optional
import requests
import pandas as pd
import io
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


def stream_terra_table(
    response: requests.Response,
    destination: Optional[Path] = None,
    chunk_size: int = 8192,
    low_memory: bool = True,
) -> pd.DataFrame:
    """
    Stream Terra table data from response to file or memory with optimized performance

    Args:
        response: Response object from Terra Firecloud API
        destination: Optional path to save TSV file
        chunk_size: Size of chunks for streaming
        low_memory: Whether to use low_memory mode for pandas read_csv (default: True)

    Returns:
        DataFrame containing table data
    """

    if destination:
        # Stream directly to file
        with open(destination, "wb") as f:
            logger.info(f"Streaming data to {destination}")
            # Use shutil.copyfileobj for more efficient file copying
            import shutil

            shutil.copyfileobj(response.raw, f)

        logger.info("Streaming data complete, reading into DataFrame")
        # Use efficient pandas options
        return pd.read_csv(
            destination,
            sep="\t",
            dtype=str,
            low_memory=low_memory,
            engine="c",
        )
    else:
        # Stream to memory more efficiently using a BytesIO buffer
        logger.info("Streaming data to memory")

        # Use a more efficient approach to concatenate binary data
        buffer = io.BytesIO()

        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                buffer.write(chunk)

        # Rewind the buffer
        buffer.seek(0)

        logger.info("Streaming data complete, reading into DataFrame")

        # Use efficient pandas options, I've added engine='c' for faster performance
        # https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_csv.html
        return pd.read_csv(
            buffer,
            sep="\t",
            dtype=str,
            low_memory=low_memory,
            engine="c",
        )
