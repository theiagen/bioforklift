from bioforklift.basespace import (
    BaseSpace,
    BaseSpaceClient,
)
from pathlib import Path

def main():

    access_token = "abc123"
    collection_id = "MiSeq: Nextera DNA Flex (replicates of E.coli, B.cereus, and R.sphaeroides)"
    samples = ['E-coli_1ng_input-rep02_L001', 'R-sphaeroides_100ng_input-rep18_L001', 'R-sphaeroides_1ng_input-rep15_L001']

    bs_client = BaseSpaceClient(access_token)
    bs = BaseSpace.from_client(bs_client)

    bs.methods.fetch_sample_fastqs(
        collection_id=collection_id,
        samples=samples,
        dest_dir=None,                 # default = None (Path)
        concatenate=True,              # default = True
        remove_sources=True,           # default = True
        validate_paired_end=True,      # default = True
        validate_lane_naming=False,    # default = False
        group_by_lane=False,           # default = False
        dry_run=True,                  # default = False
    )

    # bs.methods.build_sample_sheet(
    #     collection_id=collection_id, # None returns all datasets from a given basespace account
    #     dest_dir=None,               # None writes to cwd
    # )


if __name__ == "__main__":
    main()