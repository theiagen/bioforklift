import csv

import pytest

from bioforklift.basespace.basespace_dataset_operations import (
    concatenate_dataset_files,
    filter_dataset_types,
    match_datasets_by_sample,
    read1_files,
    read2_files,
    validate_paired_end_datasets,
    write_dataset_sample_sheet,
)
from bioforklift.basespace.basespace_exceptions import (
    BaseSpaceDatasetError,
    BaseSpaceMissingReadError,
)


class TestReadHelpers:
    @pytest.mark.parametrize(
        "name, is_r1, is_r2",
        [
            ("Sample_S1_L001_R1_001.fastq.gz", True, False),
            ("Sample_S1_L002_R2_001.fastq.gz", False, True),
            # No lane token -> still a valid read.
            ("Sample_R1_001.fastq.gz", True, False),
            # Hyphenated read token is accepted too.
            ("Sample-R2.fastq.gz", False, True),
            # Index/other reads are not R1/R2.
            ("Sample_S1_L001_I1_001.fastq.gz", False, False),
            ("random_file.txt", False, False),
        ],
    )
    def test_read_classification(self, make_file, name, is_r1, is_r2):
        # read1_files/read2_files drive the private _is_valid_read1/_is_valid_read2 predicates.
        files = [make_file("1", name)]
        assert bool(read1_files(files)) is is_r1
        assert bool(read2_files(files)) is is_r2


class TestReadPartitioning:
    def test_partitions_r1_and_r2(self, make_file):
        files = [
            make_file("1", "Sample_L001_R1_001.fastq.gz"),
            make_file("2", "Sample_L001_R2_001.fastq.gz"),
        ]
        assert [file.name for file in read1_files(files)] == ["Sample_L001_R1_001.fastq.gz"]
        assert [file.name for file in read2_files(files)] == ["Sample_L001_R2_001.fastq.gz"]

    def test_aggregates_across_lanes(self, make_file):
        # Two lanes' R1/R2 files aggregate into balanced partitions.
        files = [
            make_file("1", "S_L001_R1_001.fastq.gz"),
            make_file("2", "S_L001_R2_001.fastq.gz"),
            make_file("3", "S_L002_R1_001.fastq.gz"),
            make_file("4", "S_L002_R2_001.fastq.gz"),
        ]
        assert len(read1_files(files)) == 2
        assert len(read2_files(files)) == 2


class TestFilterDatasetTypes:
    def test_matches_by_id(self, make_dataset):
        ds = make_dataset("ds.a", "sampleA", type_id="common.fastq")
        assert filter_dataset_types([ds], ["common.fastq"]) == [ds]

    def test_matches_by_conformance(self, make_dataset):
        # Id is a typed variant, but it conforms to the requested common.fastq.
        ds = make_dataset(
            "ds.a", "sampleA", type_id="illumina.fastq.v1.8",
            conforms_to=("common.files", "common.fastq"),
        )
        assert filter_dataset_types([ds], ["common.fastq"]) == [ds]

    def test_drops_non_matching_type(self, make_dataset):
        ds = make_dataset("ds.a", "sampleA", type_id="common.bam", conforms_to=("common.files",))
        assert filter_dataset_types([ds], ["common.fastq"]) == []

    def test_none_keeps_all_types(self, make_dataset):
        ds = make_dataset("ds.a", "sampleA", type_id="common.bam", conforms_to=("common.files",))
        assert filter_dataset_types([ds], None) == [ds]

    def test_empty_list_matches_nothing(self, make_dataset):
        ds = make_dataset("ds.a", "sampleA", type_id="common.fastq")
        assert filter_dataset_types([ds], []) == []


class TestMatchDatasetsBySample:
    def _lane_datasets(self, make_dataset):
        # Four lane-split sibling datasets for the group "NA12878-3_4".
        return [make_dataset(f"ds.l{lane}", f"NA12878-3_4_L00{lane}") for lane in (1, 2, 3, 4)]

    def test_exact_match(self, make_dataset):
        ds = make_dataset("ds.a", "sampleA")
        assert match_datasets_by_sample("sampleA", [ds]) == [ds]

    def test_unmatched_raises(self, make_dataset):
        ds = make_dataset("ds.a", "sampleA")
        with pytest.raises(BaseSpaceDatasetError, match="No exact dataset match"):
            match_datasets_by_sample("sampleC", [ds])

    def test_ambiguous_exact_raises(self, make_dataset):
        ds_a = make_dataset("ds.a", "sampleA")
        ds_a2 = make_dataset("ds.a2", "sampleA")
        with pytest.raises(BaseSpaceDatasetError, match="Multiple datasets"):
            match_datasets_by_sample("sampleA", [ds_a, ds_a2])

    def test_expands_lane_group_when_enabled(self, make_dataset):
        # group_by_lane=True: a lane-less name with no exact match expands to its L00# siblings.
        lanes = self._lane_datasets(make_dataset)
        assert match_datasets_by_sample("NA12878-3_4", lanes, group_by_lane=True) == lanes

    def test_lane_only_raises_when_grouping_disabled(self, make_dataset):
        # With group_by_lane=False (default), a lane-less name matching only siblings raises.
        lanes = self._lane_datasets(make_dataset)
        with pytest.raises(BaseSpaceDatasetError, match="Lane grouping disabled"):
            match_datasets_by_sample("NA12878-3_4", lanes, group_by_lane=False)

    def test_exact_wins_and_warns_on_siblings(self, make_dataset, caplog):
        # An exact dataset-name match wins over lane siblings; ignored siblings are warned about.
        exact = make_dataset("ds.exact", "NA12878-3_4")
        lanes = self._lane_datasets(make_dataset)

        with caplog.at_level("WARNING"):
            result = match_datasets_by_sample("NA12878-3_4", [exact, *lanes], group_by_lane=True)

        assert result == [exact]
        assert "will not be grouped together" in caplog.text

    def test_dataset_can_feed_two_outputs(self, make_dataset):
        # The group name resolves to every sibling; a member-lane name resolves to just that lane,
        # so one dataset (L001) can feed both a group output and a lane output.
        lanes = self._lane_datasets(make_dataset)
        assert match_datasets_by_sample("NA12878-3_4", lanes, group_by_lane=True) == lanes
        assert match_datasets_by_sample("NA12878-3_4_L001", lanes) == [lanes[0]]


class TestValidatePairedEndDatasets:
    def test_valid_paired_end_does_not_raise(self, make_dataset, make_file):
        ds_items = [make_dataset("ds.1", "Sample", paired_end=True)]
        ds_files = [
            make_file("1", "Sample_L001_R1_001.fastq.gz"),
            make_file("2", "Sample_L001_R2_001.fastq.gz"),
        ]
        # A valid set returns None without raising.
        assert validate_paired_end_datasets(ds_items, ds_files) is None

    def test_non_paired_end_flag_raises_and_names_dataset(self, make_dataset, make_file):
        # Balanced files, but the dataset isn't flagged paired-end -> rejected, dataset named.
        ds_items = [make_dataset("ds.1", "MySample", paired_end=False)]
        ds_files = [
            make_file("1", "MySample_L001_R1_001.fastq.gz"),
            make_file("2", "MySample_L001_R2_001.fastq.gz"),
        ]
        with pytest.raises(BaseSpaceMissingReadError, match="only paired-end") as exc:
            validate_paired_end_datasets(ds_items, ds_files)
        assert "`MySample`" in str(exc.value)

    def test_non_paired_end_group_member_raises(self, make_dataset, make_file):
        # If any dataset in the group isn't flagged paired-end, the unit is rejected.
        ds_items = [
            make_dataset("ds.l1", "S_L001", paired_end=True),
            make_dataset("ds.l2", "S_L002", paired_end=False),
        ]
        ds_files = [
            make_file("1", "S_L001_R1_001.fastq.gz"),
            make_file("2", "S_L001_R2_001.fastq.gz"),
            make_file("3", "S_L002_R1_001.fastq.gz"),
            make_file("4", "S_L002_R2_001.fastq.gz"),
        ]
        with pytest.raises(BaseSpaceMissingReadError, match="only paired-end") as exc:
            validate_paired_end_datasets(ds_items, ds_files)
        assert "`S_L002`" in str(exc.value)

    @pytest.mark.parametrize(
        "names",
        [
            ("Sample_L001_R1_001.fastq.gz",),  # R1 only
            ("Sample_L001_R1_001.fastq.gz", "Sample_L002_R1_001.fastq.gz"),  # two R1s, no R2
            (
                "Sample_L001_R1_001.fastq.gz",
                "Sample_L001_R2_001.fastq.gz",
                "Sample_L001_I1_001.fastq.gz",
            ),  # extra non-read file
        ],
    )
    def test_unbalanced_reads_raise(self, make_dataset, make_file, names):
        ds_items = [make_dataset("ds.1", "Sample", paired_end=True)]
        ds_files = [make_file(str(index), name) for index, name in enumerate(names)]
        with pytest.raises(BaseSpaceMissingReadError, match="Unbalanced R1/R2"):
            validate_paired_end_datasets(ds_items, ds_files)


class TestConcatenateDatasetFiles:
    def _write_files(self, make_file, tmp_path, specs):
        # specs: list of (filename, data_or_None, size). Files with data are written under dest_dir.
        files = []
        for fname, data, size in specs:
            if data is not None:
                (tmp_path / fname).write_bytes(data)
            files.append(make_file(fname, fname, size=size))
        return files

    def test_concatenates_reads(self, make_file, tmp_path):
        # R1s merge into {name}_R1 and R2s into {name}_R2, in file order.
        files = self._write_files(
            make_file, tmp_path,
            [
                ("Sample_S1_L001_R1_001.fastq.gz", b"11", 2),
                ("Sample_S1_L002_R1_001.fastq.gz", b"22", 2),
                ("Sample_S1_L001_R2_001.fastq.gz", b"aa", 2),
                ("Sample_S1_L002_R2_001.fastq.gz", b"bb", 2),
            ],
        )

        concatenate_dataset_files("Sample", files, dest_dir=tmp_path)

        assert (tmp_path / "Sample_R1.fastq.gz").read_bytes() == b"1122"
        assert (tmp_path / "Sample_R2.fastq.gz").read_bytes() == b"aabb"

    def test_dry_run_writes_nothing(self, make_file, tmp_path):
        files = self._write_files(
            make_file, tmp_path,
            [
                ("Sample_S1_L001_R1_001.fastq.gz", None, None),
                ("Sample_S1_L001_R2_001.fastq.gz", None, None),
            ],
        )

        concatenate_dataset_files("Sample", files, dest_dir=tmp_path, dry_run=True)

        assert list(tmp_path.iterdir()) == []

    def test_empty_read_side_is_skipped(self, make_file, tmp_path):
        # Only R1 files present: R1 is written, the empty R2 side is skipped (no output).
        files = self._write_files(
            make_file, tmp_path,
            [
                ("Sample_S1_L001_R1_001.fastq.gz", b"11", 2),
                ("Sample_S1_L002_R1_001.fastq.gz", b"22", 2),
            ],
        )

        concatenate_dataset_files("Sample", files, dest_dir=tmp_path)

        assert (tmp_path / "Sample_R1.fastq.gz").read_bytes() == b"1122"
        assert not (tmp_path / "Sample_R2.fastq.gz").exists()

    def test_validate_lane_naming_raises_on_mismatch(self, make_file, tmp_path):
        # With validate_lane_naming, R1 files that don't share one lane-stripped name raise.
        files = self._write_files(
            make_file, tmp_path,
            [
                ("Sample_S1_L001_R1_001.fastq.gz", b"11", 2),
                ("OTHER_S1_L002_R1_001.fastq.gz", b"22", 2),
                ("Sample_S1_L001_R2_001.fastq.gz", b"aa", 2),
                ("OTHER_S1_L002_R2_001.fastq.gz", b"bb", 2),
            ],
        )

        with pytest.raises(BaseSpaceDatasetError, match="multiple lane-stripped filenames"):
            concatenate_dataset_files("Sample", files, dest_dir=tmp_path, validate_lane_naming=True)

    def test_group_spanning_lanes_concatenates(self, make_file, tmp_path):
        # One sample spanning four lanes merges all R1s (and all R2s), in file order.
        files = self._write_files(
            make_file, tmp_path,
            [
                ("NA12878-3_4_L001_R1_001.fastq.gz", b"1", 1),
                ("NA12878-3_4_L002_R1_001.fastq.gz", b"2", 1),
                ("NA12878-3_4_L003_R1_001.fastq.gz", b"3", 1),
                ("NA12878-3_4_L004_R1_001.fastq.gz", b"4", 1),
                ("NA12878-3_4_L001_R2_001.fastq.gz", b"a", 1),
                ("NA12878-3_4_L002_R2_001.fastq.gz", b"b", 1),
                ("NA12878-3_4_L003_R2_001.fastq.gz", b"c", 1),
                ("NA12878-3_4_L004_R2_001.fastq.gz", b"d", 1),
            ],
        )

        concatenate_dataset_files("NA12878-3_4", files, dest_dir=tmp_path)

        assert (tmp_path / "NA12878-3_4_R1.fastq.gz").read_bytes() == b"1234"
        assert (tmp_path / "NA12878-3_4_R2.fastq.gz").read_bytes() == b"abcd"


class TestWriteDatasetSampleSheet:
    def test_writes_csv_with_row_per_dataset(self, make_dataset, make_file, tmp_path):
        ds_paired = make_dataset("ds.1", "PairedSample", paired_end=True)
        paired_files = [
            make_file("1", "PairedSample_L001_R1_001.fastq.gz", size=1024 * 1024),
            make_file("2", "PairedSample_L001_R2_001.fastq.gz", size=2 * 1024 * 1024),
        ]
        ds_single = make_dataset("ds.2", "SingleSample", paired_end=False)
        single_files = [make_file("3", "SingleSample_L001_R1_001.fastq.gz", size=1024 * 1024)]

        output_path = tmp_path / "sheet.csv"
        result = write_dataset_sample_sheet(
            [(ds_paired, paired_files), (ds_single, single_files)],
            output_path,
        )

        assert result == output_path

        with output_path.open(newline="") as csvfile:
            rows = list(csv.DictReader(csvfile))

        assert [row["dataset_name"] for row in rows] == ["PairedSample", "SingleSample"]

        paired_row = rows[0]
        assert paired_row["dataset_id"] == "ds.1"
        assert paired_row["num_files"] == "2"
        assert paired_row["dataset_type"] == "common.fastq"
        assert paired_row["is_paired_end"] == "True"
        assert paired_row["is_balanced"] == "True"
        assert paired_row["read1_concat_size_mb"] == "1.00 MB"
        assert paired_row["read2_concat_size_mb"] == "2.00 MB"

        single_row = rows[1]
        assert single_row["is_paired_end"] == "False"
        assert single_row["is_balanced"] == "False"
