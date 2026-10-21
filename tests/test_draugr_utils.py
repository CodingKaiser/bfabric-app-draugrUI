from utils.draugr_utils import build_draugr_args


def _value(args, flag):
    """The value of a --flag=value argument."""
    (match,) = [a for a in args if a.startswith(flag + "=")]
    return match[len(flag) + 1 :]


def test_defaults_only_reprocess_the_orders():
    args = build_draugr_args(run_folder="261016_X570", order_list=[43291, 43383])
    assert args[args.index("--run-folder") + 1] == "/export/local/data/261016_X570"
    assert args[-2:] == ["--reprocess-orders", "43291,43383"]
    assert not any(a.startswith("--skip") or a == "-xq" for a in args)


def test_switches_map_to_draugr_flags():
    args = build_draugr_args(
        run_folder="R",
        order_list=[1],
        skip_gstore=True,
        skip_postprocessing=True,
        skip_demux=True,
        disable_wizard=True,
        skip_raw_qc=True,
    )
    for flag in ["--skip-gstore-copy", "--skip-post-demux", "--skip-demux", "--disable-wizard", "-xq"]:
        assert flag in args


def test_flag_values_are_one_argument_each_and_unquoted():
    # Each value is one argv element; shell quoting is the job script's business now.
    args = build_draugr_args(
        run_folder="R",
        order_list=[1],
        bclconvert_flags='"--tiles s_1_2201+s_1_2202;--num-unknown-barcodes-reported 20"',
        bases2fastq_flags="'--force-index-orientation'",
        bases_mask="-y36n*,I8n*",
        barcode_mismatches="0",
    )
    assert _value(args, "--custom-bclconvert-flags") == (
        "--tiles s_1_2201+s_1_2202;--num-unknown-barcodes-reported 20"
    )
    # Without --flag=value, argparse reads a lone "--force-index-orientation" as a flag.
    assert _value(args, "--custom-bases2fastq-flags") == "--force-index-orientation"
    assert _value(args, "--bases-mask") == "-y36n*,I8n*"
    assert _value(args, "--barcode-mismatches") == "0"


def test_empty_inputs_add_nothing():
    args = build_draugr_args(
        run_folder="R", order_list=[1], bclconvert_flags="", bases_mask="", barcode_mismatches=""
    )
    assert not any(a.startswith(("--custom", "--bases-mask", "--barcode-mismatches")) for a in args)
