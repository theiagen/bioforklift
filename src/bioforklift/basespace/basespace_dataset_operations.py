import re
import csv

from pathlib import Path
from typing import List, Optional, Tuple

from .basespace_exceptions import (
    BaseSpaceMissingReadError,
    BaseSpaceDatasetError,
)
from .basespace_models import (
    DatasetFileItem,
    DatasetItem,
)
from .basespace_file_operations import (
    concatenate_files,
    mib_to_mb,
)
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)

# The lane pattern is `_L` (or `-L`) plus 1-3 digits, case-insensitive
# So `_L1`, `_L01`, and `_L001` all count. The location of the lane token must be:
#
#   1. at the END of a dataset name          `NA1200-3_4_L001`         -> `NA1200-3_4`
#   2. directly BEFORE the R1/2 in a FASTQ   `S1_L001_R1_001.fastq.gz` -> `S1_R1_001.fastq.gz`
#
# Example Matches (stripped):
#   NA1200-3_4_L1 / _L01 / _L001 / _l001 / -L001   -> `NA1200-3_4`   (1-3 digits, either separator, either case)
#   sample_L0001_S1_L001_R1_001.fastq.gz           -> `sample_L0001_S1_R1_001.fastq.gz` (the 4-digit token survives)
#
# Non-matches (returned unchanged):
#   CA-2024-001_L1_extra                           -> neither at the end nor before a R1/2 token
#   SampleL001, Sample_LANE001                     -> needs a `_`/`-` separator immediately before `L`
#   Sample_S1_L001_I1_001.fastq.gz                 -> lane # not before `R1`/`R2`

_LANE_PATTERN = re.compile(r"[_-]L\d{1,3}(?=[_-]R[12]|$)", re.IGNORECASE)

_R1_PATTERN = re.compile(r"[_-]R1.*\.fastq\.gz$", re.IGNORECASE)
_R2_PATTERN = re.compile(r"[_-]R2.*\.fastq\.gz$", re.IGNORECASE)

def _strip_lane_token(name: str) -> str:
    """
    Return `name` without its lane pattern (`NA1200-3_4_L001` -> `NA1200-3_4`,
    `S_L001_R1_001.fastq.gz` -> `S_R1_001.fastq.gz`). Returns the original name unchanged when
    there is no lane token; see `_LANE_PATTERN` for exactly what counts as one.

    Args:
        name: The dataset name or FASTQ filename to strip.
    """
    match = _LANE_PATTERN.search(name)
    return name[: match.start()] + name[match.end():] if match else name

def _is_valid_read1(name: str) -> bool:
    return bool(_R1_PATTERN.search(name))

def _is_valid_read2(name: str) -> bool:
    return bool(_R2_PATTERN.search(name))

def read1_files(ds_files: List[DatasetFileItem]) -> List[DatasetFileItem]:
    """Return the R1 files among `ds_files` (by filename pattern), sorted by filename."""
    return sorted(
        [file for file in ds_files if _is_valid_read1(file.name)],
        key=lambda file: file.name,
    )

def read2_files(ds_files: List[DatasetFileItem]) -> List[DatasetFileItem]:
    """Return the R2 files among `ds_files` (by filename pattern), sorted by filename."""
    return sorted(
        [file for file in ds_files if _is_valid_read2(file.name)],
        key=lambda file: file.name,
    )

def _is_paired_end(ds_item: DatasetItem) -> bool:
    """True only if the dataset is flagged paired-end (`attributes` is optional)."""
    return bool(ds_item.attributes and ds_item.attributes.is_paired_end)

def _is_balanced(ds_files: List[DatasetFileItem]) -> bool:
    """True if there is an equal, non-zero R1/R2 count across the group with no other files present."""
    r1, r2 = len(read1_files(ds_files)), len(read2_files(ds_files))
    return r1 != 0 and r1 == r2 and r1 + r2 == len(ds_files)

def validate_paired_end_datasets(
    ds_items: List[DatasetItem],
    ds_files: List[DatasetFileItem],
) -> None:
    """
    Raise unless the datasets and their files form a balanced paired-end set: every dataset
    flagged paired-end, and an equal, non-zero number of R1 and R2 files with nothing else
    present. Mirrors the `_is_paired_end` / `_is_balanced` predicates.

    Args:
        ds_items: The dataset(s) feeding one output.
        ds_files: Every file across those dataset(s).

    Raises:
        BaseSpaceMissingReadError: If any dataset is not flagged paired-end, or the R1/R2
            files are unbalanced.
    """
    not_paired = [
        ds_item.name for ds_item in ds_items
        if not _is_paired_end(ds_item)
    ]
    if not_paired:
        raise BaseSpaceMissingReadError(
            f"DatasetItem(s) `{', '.join(not_paired)}` not flagged paired-end; only paired-end datasets are supported."
        )

    not_balanced = not _is_balanced(ds_files)
    if not_balanced:
        raise BaseSpaceMissingReadError(
            f"Unbalanced R1/R2 files for dataset(s) `{', '.join(ds_item.name for ds_item in ds_items)}` "
            f"(R1={len(read1_files(ds_files))}, R2={len(read2_files(ds_files))}, total={len(ds_files)}). "
            f"Every file must be an R1 or R2 read."
        )

    logger.info(f"Validated {len(ds_files)} FASTQ files across {len(ds_items)} matching datasets")


def filter_dataset_types(
    ds_items: List[DatasetItem],
    dataset_types: Optional[List[str]] = None,
) -> List[DatasetItem]:
    """
    If `dataset_types` is None (match all types) or the dataset matches any requested
    type by `DatasetType.Id` or conformance (`ConformsToIds`). Conformance catches
    typed variants like `illumina.fastq.v1.8`, which conform to `common.fastq`.

    Args:
        ds_items: List of DatasetItems to filter from.
        dataset_types: Dataset types to keep (e.g. `["common.fastq"]`); default `None` keeps all types.

    Returns:
        List[DatasetItem]: List of DatasetItems filtered by `dataset_types`
    """

    # `None` means "match every type"; an empty list matches nothing.
    if dataset_types is None:
        return ds_items

    filtered = []
    requested = set(dataset_types)
    for ds_item in ds_items:
        if ds_item.dataset_type is not None and (
            ds_item.dataset_type.id in requested
            or requested.intersection(ds_item.dataset_type.conforms_to_ids)
        ):
            filtered.append(ds_item)

    logger.info(
        f"Filtered {len(filtered)} dataset(s) of type {dataset_types} (out of {len(ds_items)} total)"
    )
    return filtered

def _dataset_exact_match(
    sample: str,
    ds_items: List[DatasetItem],
) -> List[DatasetItem]:
    """Return the single DatasetItem whose name exactly matches `sample`, or None."""

    match = [ds_item for ds_item in ds_items if ds_item.name == sample]
    if len(match) > 1:
        raise BaseSpaceDatasetError(
            f"Multiple datasets (n={len(match)}) found for sample `{sample}`. "
            f"Provide a more specific sample name."
        )
    return match

def _dataset_laned_siblings(
    sample: str,
    ds_items: List[DatasetItem],
) -> List[DatasetItem]:
    """Return `{sample}_L###` datasets, excluding any dataset whose name already equals `sample`."""

    # Lane-split siblings: `{sample}_L###` datasets that would group together. The lane token
    # must be the trailing portion of the dataset name, so an in-sample `L#` isn't stripped.
    # Don't consider it a sibling if the original ds_item.name already matches
    return [
        ds_item for ds_item in ds_items if (
            _strip_lane_token(ds_item.name) == sample
            and ds_item.name != sample
        )
    ]

def match_datasets_by_sample(
    sample: str,
    ds_items: List[DatasetItem],
    group_by_lane: bool = False,
) -> List[DatasetItem]:
    """
    Resolve one requested sample name to the dataset(s) that feed its output.

      - an exact `DatasetItem.Name` match always wins (a warning is logged if `{sample}_L###`
          siblings also exist, since they won't be grouped in)
      - otherwise, when `group_by_lane` is True, any `{sample}_L###` sibling datasets are
          returned together for downstream concatenation across lanes
      - when `group_by_lane` is False, a name matching only `{sample}_L###` siblings raises
          rather than silently grouping

    Args:
        sample: The requested sample name to match.
        ds_items: DatasetItems to match against.
        group_by_lane: If True, group a lane-less sample name with its `{sample}_L###` siblings.
            Defaults to False (an exact match is required).

    Returns:
        The matched DatasetItem(s): a single-item list for an exact match, or the lane-sibling
        group when `group_by_lane` is True.

    Raises:
        BaseSpaceDatasetError: If the sample matches multiple exact datasets, matches only lane
            siblings while `group_by_lane` is False, or matches nothing.
    """
    exact_match = _dataset_exact_match(
        sample=sample,
        ds_items=ds_items,
    )

    siblings = _dataset_laned_siblings(
        sample=sample,
        ds_items=ds_items,
    )

    # An exact dataset-name match always wins
    if exact_match:
        # warn if siblings also exist so the user knows those lanes won't be grouped into these datasets.
        if siblings:
            logger.warning(
                f"Exact dataset match for `{sample}` found; {len(siblings)} laned sibling(s) "
                f"({', '.join(s.name for s in siblings)}) exist, but will not be grouped together"
            )
        else:
            logger.info(f"Exact dataset match for `{sample}` found")
        return exact_match

    elif siblings and group_by_lane:
        logger.info(
            f"Partial dataset match for `{sample}` found; {len(siblings)} laned sibling(s) "
            f"({', '.join(s.name for s in siblings)}) exist and will be grouped together"
        )
        return siblings

    elif siblings and not group_by_lane:
        raise BaseSpaceDatasetError(
            f"Partial dataset match for `{sample}` found; {len(siblings)} laned sibling(s) "
            f"({', '.join(s.name for s in siblings)}) exist, but will not be grouped together (group_by_lane=False)"
        )
    else:
        raise BaseSpaceDatasetError(
            f"No exact dataset match for `{sample}` found."
        )

def concatenate_dataset_files(
    samplename: str,
    ds_files: List[DatasetFileItem],
    dest_dir: Path,
    dry_run: bool = False,
    validate_lane_naming: bool = False,
    remove_sources: bool = True,
) -> None:
    """
    Concatenate one sample's per-lane files into clean `{samplename}_R1.fastq.gz` /
    `{samplename}_R2.fastq.gz` outputs under `dest_dir`.

    Source paths are derived as `dest_dir / file.name` — the same deterministic location the
    files were downloaded to — so this step carries no state over from download. Assumes the
    files have been validated (balanced paired-end); a read side with no files is skipped. Within
    each read, the lane files are joined at the byte level.

    Args:
        samplename: Names the output files (`{samplename}_R1/_R2.fastq.gz`).
        ds_files: Every FASTQ file for the sample, already on disk under `dest_dir`.
        dest_dir: The directory the files were downloaded to.
        dry_run: If True, log the outputs that would be written without reading or writing files.
        validate_lane_naming: If True, verify that all FASTQ files being concatenated share the
            same lane-stripped filename (per `_LANE_PATTERN`) before merging.
        remove_sources: If True (default), delete each output's per-lane source files once the
            concatenated output has been size-verified and written.

    Raises:
        BaseSpaceDownloadError: If a concatenated output's size does not match the combined
            `Size` of its source files.
        BaseSpaceDatasetError: If `validate_lane_naming` and a read's files don't share one
            lane-stripped name.
    """
    # Track only outputs we actually process (past both guards) so the summary
    # reflects real writes rather than every candidate output.
    output_count = 0
    source_file_count = 0

    # Concatenation only occurs within one sample's dataset files. Assuming the files were validated,
    # there should be no empty, unbalanced, or invalid reads. Both helpers return filename-sorted
    # lists, so R1/R2 are concatenated in matching lane order no matter what order the API returned.
    for output_filename, read_files in (
        (f"{samplename}_R1.fastq.gz", read1_files(ds_files)),
        (f"{samplename}_R2.fastq.gz", read2_files(ds_files)),
    ):

        # Shouldn't happen for a validated sample.
        if not read_files:
            continue

        if validate_lane_naming:
            # filter for "laned" (`_LANE_PATTERN`) fastq files
            laned_files = [
                _strip_lane_token(file_item.name)
                for file_item in read_files
            ]

            # Cannot resolve R1/R2 lane concatenation if differently-named fastq files exist.
            if len(set(laned_files)) > 1:
                raise BaseSpaceDatasetError(
                    f"Cannot concatenate FASTQ files for sample {samplename}; "
                    f"unable to resolve multiple lane-stripped filenames: {sorted(set(laned_files))}."
                )

        source_paths = [dest_dir / file_item.name for file_item in read_files]
        output_path = dest_dir / output_filename

        output_count += 1
        source_file_count += len(source_paths)

        if dry_run:
            removal_note = " (removing the source file(s) afterward)" if remove_sources else ""
            logger.info(
                f"[dry-run] Would concatenate {len(source_paths)} FASTQ file(s) into "
                f"`{output_path}`{removal_note}:\n" +
                "\n".join([path.name for path in source_paths])
            )
            continue

        logger.info(
            f"Concatenating {len(source_paths)} FASTQ file(s) into `{output_path}`:\n" +
            "\n".join([path.name for path in source_paths])
        )

        # Verify against the combined size the API reported (skipped if any source lacks a Size).
        sizes = [file_item.size for file_item in read_files]
        expected_total_size = (
            sum(size for size in sizes if size is not None)
            if all(size is not None for size in sizes)
            else None
        )

        # The absolute lane order doesn't matter as long as it's consistent between R1/R2
        concatenate_files(
            sources=source_paths,
            destination=output_path,
            expected_total_size=expected_total_size,
            remove_sources=remove_sources,
        )

    verb = "would generate" if dry_run else "generated"
    logger.info(
        f"In total, {verb} {output_count} concatenated FASTQ output(s) "
        f"from {source_file_count} total FASTQ file(s)"
    )

def write_dataset_sample_sheet(
    grouped_datasets: List[Tuple[DatasetItem, List[DatasetFileItem]]],
    output_path: Path,
) -> Path:
    """
    Write a CSV summarizing each dataset and its files: per-read concatenated sizes, file count,
    dataset type, and whether it forms a paired-end / balanced set.

    Args:
        grouped_datasets: `(DatasetItem, [DatasetFileItem, ...])` pairs, one per dataset.
        output_path: Destination CSV path.

    Returns:
        The written CSV path.
    """

    header = [
        "dataset_name",
        "dataset_id",
        "read1_concat_size_mb",
        "read2_concat_size_mb",
        "num_files",
        "dataset_type",
        "is_paired_end",
        "is_balanced",
    ]

    with open(output_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)

        for ds_item, ds_files in grouped_datasets:
            total_r1_mib = sum(file_item.size or 0 for file_item in read1_files(ds_files)) / (1024 * 1024)
            total_r2_mib = sum(file_item.size or 0 for file_item in read2_files(ds_files)) / (1024 * 1024)
            writer.writerow([
                ds_item.name,
                ds_item.id,
                f"{mib_to_mb(total_r1_mib):.2f} MB",
                f"{mib_to_mb(total_r2_mib):.2f} MB",
                len(ds_files),
                ds_item.dataset_type.id if ds_item.dataset_type else "",
                _is_paired_end(ds_item),
                _is_balanced(ds_files),
            ])
        logger.info(
            f"Wrote sample sheet with {len(grouped_datasets)} dataset(s) to `{output_path}`"
        )
        return output_path
