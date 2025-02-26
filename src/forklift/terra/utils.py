from pathlib import Path
from typing import Optional
import requests
import pandas as pd
import io


def stream_terra_table(
    response: requests.Response,
    destination: Optional[Path] = None,
    chunk_size: int = 8192,
) -> pd.DataFrame:
    """
    Stream Terra table data from response to file or memory

    Args:
        response: Response object from Terra Firecloud API
        destination: Optional path to save TSV file
        chunk_size: Size of chunks for streaming

    Returns:
        DataFrame containing table data
    """
    if destination:
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)

        return pd.read_csv(destination, sep="\t", dtype=str)
    else:
        content = b""
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                content += chunk

        return pd.read_csv(io.BytesIO(content), sep="\t", dtype=str)