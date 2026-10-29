"""
Command builders for the Draugr and Sushi pipelines.

Neither function executes anything directly.

  build_draugr_args()        — builds draugr's own arguments for a run. They are
                                handed to draugr's SLURM submit script (see
                                utils/slurm_queue.py), which owns the ssh hop,
                                the environment on the server and all quoting.

  generate_sushi_command()   — locates the run's dataset file on fgcz-h-082,
                                then returns two commands: one to grep the selected
                                order IDs into a Sushi bash script, and one to
                                execute that script via nohup.

  check_if_file_exists()     — helper that runs an SSH ls via subprocess and
                                returns True/False; used internally by
                                generate_sushi_command() to find the dataset file.
"""

import subprocess


def _format_flag_value(value):
    """
    Strip one layer of quotes a user wrapped around a custom flag value.

    Users often wrap their input in quotes (the documentation shows quoted
    examples), which would otherwise end up as literal quote characters inside
    the argument value. No shell quoting happens here: the value travels as one
    argv element, and draugr's job script quotes it for the server's shell.
    """
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ('"', "'"):
        stripped = stripped[1:-1].strip()
    return stripped


def build_draugr_args(
    run_folder,
    order_list,
    skip_gstore=False,
    skip_postprocessing=False,
    skip_demux=False,
    disable_wizard=False,
    skip_raw_qc=False,
    bases2fastq_flags=None,
    bclconvert_flags=None,
    bases_mask=None,
    barcode_mismatches=None
):
    """
    Build draugr's arguments for reprocessing orders of a run.

    Args:
        run_folder (str): Run folder name.
        order_list (list): List of order IDs to process.
        skip_gstore (bool): Skip the Gstore copy step.
        skip_postprocessing (bool): Skip post-demultiplexing processing.
        skip_demux (bool): Skip demultiplexing step.
        disable_wizard (bool): Disable the wizard.
        skip_raw_qc (bool): Skip generation of RawQC report.
        bases2fastq_flags (str): Custom Bases2fastq flags.
        bclconvert_flags (str): Custom bclconvert flags.
        bases_mask (str): Illumina-only bases mask override (--bases-mask).
        barcode_mismatches (str): Illumina-only barcode mismatch override, "0"/"1"/"2".

    Returns:
        list[str]: draugr's argv, one element per argument.
    """
    args = [
        "--login-config", "/home/illumina/bfabric_cred/.bfabricpy.yml",
        "--run-folder", f"/export/local/data/{run_folder}",
        "--analysis-folder", "/export/local/analyses",
        "--logger-rep", "/srv/GT/analysis/falkonoe/dmx_logs/prod",
        "--scripts-destination", "/srv/GT/analysis/datasets",
    ]

    if skip_gstore:
        args.append("--skip-gstore-copy")
    if skip_postprocessing:
        args.append("--skip-post-demux")
    if skip_demux:
        args.append("--skip-demux")
    if disable_wizard:
        args.append("--disable-wizard")
    if skip_raw_qc:
        args.append("-xq")
    # --flag=value, because a custom flags string starts with '-' and argparse
    # would otherwise read it as the next flag rather than as this flag's value.
    if bases2fastq_flags:
        args.append("--custom-bases2fastq-flags=" + _format_flag_value(bases2fastq_flags))
    if bclconvert_flags:
        args.append("--custom-bclconvert-flags=" + _format_flag_value(bclconvert_flags))
    # --bases-mask and --barcode-mismatches are separate top-level flags as of
    # draugr v2.8.0. Same --flag=value form: the mask can legitimately start with '-'.
    if bases_mask:
        args.append("--bases-mask=" + _format_flag_value(bases_mask))
    if barcode_mismatches:
        args.append("--barcode-mismatches=" + _format_flag_value(barcode_mismatches))

    args += ["--reprocess-orders", ",".join(str(elt) for elt in order_list)]
    return args

def check_if_file_exists(ssh_command):
    try:
        subprocess.check_output(ssh_command, shell=True)
        return True
    except subprocess.CalledProcessError:
        return False

def generate_sushi_command(
        order_list,
        run_name
):

    """
    Generate a command string for the Sushi pipeline.

    Args:
        order_list (list): List of order IDs to process.
        run_name (str): Run name.

    Returns:
        str: Command string for the Sushi pipeline.
    """

    ssh_login = "trxcopy@fgcz-h-082"
    remote_path = "/srv/GT/analysis/datasets"

    check_file_command_original = f"ssh {ssh_login} 'ls {remote_path}/{run_name}*'"
    check_file_command_processed = f"ssh {ssh_login} 'ls {remote_path}/processed/{run_name}*'"
    check_file_command_iseq = f"ssh {ssh_login} 'ls {remote_path}/ISeq/{run_name}*'"

    in_orig = check_if_file_exists(check_file_command_original)
    in_proc = check_if_file_exists(check_file_command_processed)
    in_iseq = check_if_file_exists(check_file_command_iseq)

    if not in_orig and not in_proc and not in_iseq:
        return False, False

    order_string = "|".join([str(elt) for elt in order_list]).replace("|", "\\|")

    if in_orig:
        generate_bash_script = f'''ssh {ssh_login} "grep '{order_string}' /srv/GT/analysis/datasets/{run_name}* | uniq -u > /srv/GT/analysis/datasets/draugrUI/{run_name}_orders.sh"'''
    elif in_iseq:
        generate_bash_script = f'''ssh {ssh_login} "grep '{order_string}' /srv/GT/analysis/datasets/ISeq/{run_name}* | uniq -u > /srv/GT/analysis/datasets/draugrUI/{run_name}_orders.sh"'''
    else:
        generate_bash_script = f'''ssh {ssh_login} "grep '{order_string}' /srv/GT/analysis/datasets/processed/{run_name}* | uniq -u > /srv/GT/analysis/datasets/draugrUI/{run_name}_orders.sh"'''

    execute_bash_script = f'''ssh {ssh_login} "nohup bash -lc 'cd /srv/sushi/production/master && bash /srv/GT/analysis/datasets/draugrUI/{run_name}_orders.sh &> /srv/GT/analysis/datasets/draugrUI/output.log &' &> output.log"'''

    # if in_orig:
    #     ssh_command = f'''ssh trxcopy@fgcz-h-031 "nohup bash -lc 'cd /srv/sushi/production/master && grep '{order_string}' /srv/GT/analysis/datasets/{run_name}* | uniq -u | bash -s &> /srv/GT/analysis/datasets/draugrUI/output.log &' &> output.log"'''
    # else:
    #     ssh_command = f'''ssh trxcopy@fgcz-h-031 "nohup bash -lc 'cd /srv/sushi/production/master && grep '{order_string}' /srv/GT/analysis/datasets/processed/{run_name}* | uniq -u | bash -s &> /srv/GT/analysis/datasets/draugrUI/output.log &' &> output.log"'''

    return generate_bash_script, execute_bash_script
