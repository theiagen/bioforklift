import fnmatch
import argparse
import pandas as pd
from pathlib import Path
from google.cloud import storage
from bioforklift.terra import Terra
from bioforklift.scripts.configure import CLIConfig
from bioforklift.forklift_logging import setup_logger


logger = setup_logger(__name__)


def download_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Define command-line arguments for download subcommand"""
    d_parser = parser.add_argument_group("Data Parameters")
    d_parser.add_argument(
        "table", type=str, nargs="+",help="Terra entity table name(s) (space-delimited)"
    )
    d_parser.add_argument(
        "-c", "--column", type=str, nargs="+", default=[], help="Column name(s) to include in the download (space-delimited); DEFAULT: all columns"
    )
    d_parser.add_argument(
        "-s", "--sample", type=str, nargs="+", default=[], help="Sample name(s) to filter the download (space-delimited); DEFAULT: all samples"
    )

    ws_parser = parser.add_argument_group("Terra Workspace Parameters")
    ws_parser.add_argument("-ws", "--workspace", type=str, help="Terra workspace name")
    ws_parser.add_argument("-p", "--project", type=str, help="Terra project name")

    run_parser = parser.add_argument_group("Runtime Parameters")
    run_parser.add_argument(
        "-f",
        "--files",
        action="store_true",
        help="Download GSURIs; DEFAULT: False",
    )
    run_parser.add_argument(
        "-o",
        "--output_path",
        type=str,
        help="Path to save downloaded data; DEFAULT: current directory",
    )
    return parser


def glob_entities(terra_entities: list, table: str) -> list:
    """Glob-like pattern matching for Terra entity tables"""
    fn_tables = fnmatch.filter(terra_entities, table)
    # exclude the _set suffix
    if any(t.endswith("_set") for t in fn_tables):
        logger.debug(f"Excluding '_set' tables from matches for pattern '{table}'")
        fn_tables = [t for t in fn_tables if not t.endswith("_set")]
    logger.debug(f"Pattern '{table}' matched tables: {fn_tables}")
    if not fn_tables:
        raise ValueError(f"No tables match '{table}' in the Terra workspace.")

    return fn_tables


def extract_df(df: pd.DataFrame, columns: list = None, samples: list = None, sample_col: str = None) -> pd.DataFrame:
    """Extract specified columns and samples from the downloaded DataFrame"""
    # extract columns
    if columns:
        # ensure sample column is included and appears first if specified
        columns = [sample_col] + sorted(set(columns).difference({sample_col}))
        missing_cols = [col for col in columns if col not in df.columns]
        if missing_cols:
            logger.warning(f"Columns {missing_cols} not found")
            columns = [col for col in columns if col not in set(missing_cols)]
        df = df[columns]

    # extract samples 
    if samples:
        if sample_col not in df.columns:
            raise ValueError(f"No '{sample_col}' column found in the table for filtering.")
        missing_samples = [s for s in samples if s not in df[sample_col].unique()]
        if missing_samples:
            raise ValueError(f"Samples {missing_samples} not found in the '{sample_col}' column.")
        df = df[df[sample_col].isin(samples)]
    
    return df


def download_gsuri(storage_client: storage.Client, gs_uri: str, output_dir: Path) -> None:
    """Download a file from a Google Storage URI to the specified output directory"""
    # Parse the gs_uri to extract bucket name and blob name
    if not gs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GSURI '{gs_uri}': must start with 'gs://'")
    
    path_parts = gs_uri[5:].split("/", 1)
    if len(path_parts) != 2:
        raise ValueError(f"Invalid GSURI '{gs_uri}': must be in the format 'gs://bucket_name/blob_name'")
    
    bucket_name, blob_name = path_parts
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    # Download the blob to the output directory
    output_path = output_dir / Path(blob_name).name
    blob.download_to_filename(output_path)
    logger.debug(f"Downloaded {gs_uri} to {output_path}")


def file_download_mngr(df: pd.DataFrame, output_dir: Path, prefixes: set = {"gs://"}) -> None:
    """Manage file downloads for prefixes in the specified DataFrame columns"""
    storage_client = storage.Client()
    for col in df.columns:
        for prefix in prefixes:
            if df[col].str.startswith(prefix).any():
                download_dir = output_dir / col
                download_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Downloading files from '{col}'")
                for uri in df[col].dropna().unique():
                    if uri.startswith(prefix):
                        try:
                            logger.debug(f"Downloading {uri}")
                            download_gsuri(storage_client, uri, download_dir)
                        except Exception as e:
                            logger.error(f"Failed to download file from {uri}: {e}")


def download(args: argparse.Namespace, config: CLIConfig = CLIConfig()) -> None:
    """Download data from Terra workspace"""
    config.update(vars(args))

    # Initialize Terra client
    terra = Terra(
        source_workspace=config.workspace,
        source_project=config.project,
        destination_workspace=config.workspace,
        destination_project=config.project,
    )

    # Create output directory if it doesn't exist
    if args.output_path:
        output_dir = Path(args.output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
    # organize neatly for file downloads
    elif args.files:
        cur_date = pd.Timestamp.now().strftime("%Y%m%d")
        output_dir = Path.cwd() / f"bioforklift_{cur_date}"
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = Path.cwd()

    terra_entities = terra.entities.list_entity_types(include_attributes=False)
    # unpack the matches via glob-like pattern matching
    tables = []
    for table in args.table:
        tables.extend(glob_entities(terra_entities, table))

    for table in tables:
        df = terra.entities.download_table(table)
        # Extract specified columns and samples if provided
        if args.column or args.sample:
            # assume the first column is sample column
            sample_col = df.columns[0]
            df = extract_df(df, columns=args.column, samples=args.sample, sample_col=sample_col)
        # Save the downloaded table to defined output path or current directory
        output_path = output_dir / f"{table}.tsv"
        df.to_csv(output_path, index=False, sep="\t")
        logger.info(f"Downloaded table '{table}' to {output_path}")
        # download files
        if args.files:
            logger.info(f"Initiating file downloads for table '{table}'")
            # output files to a subdirectory named after the table within the main output directory
            file_dir = output_dir / table
            file_dir.mkdir(parents=True, exist_ok=True)
            file_download_mngr(df, file_dir)