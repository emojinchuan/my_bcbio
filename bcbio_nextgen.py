from __future__ import print_function
import sys,os
import argparse


from bcbio import install,utils,workflow
from bcbio.distributed import runfn,clargs


def parse_cl_args(in_args):

    sub_cmds = {
        "upgrade" : install.add_subparser,
        'runfn' : runfn.add_subparser
    }
    description = "Community developed high throughput sequencing analysis."
    parser = argparse.ArgumentParser(description= description)
    sub_cmd = None
    if len(in_args) > 0 and in_args[0] in sub_cmds:


        subparser_help = "bcbio-nextgen supplemental commands"
        subparsers = parser.add_subparsers(help= subparser_help)
        sub_cmds[in_args[0]](subparsers)
        # sub_cmds['runfn'](subparsers)
        sub_cmd = in_args[0]
    else:
        parser.add_argument("global_config", nargs="?",
                            help=("Global YAML configuration file specifying "
                                  "details about the system (optional, "
                                  "defaults to installed bcbio_system.yaml)"))
        parser.add_argument("fc_dir", nargs="?",
                            help=("A directory of Illumina output or fastq "
                                  "files to process (optional)"))
        parser.add_argument("run_config", nargs="*",
                            help=("YAML file with details about samples to "
                                  "process (required, unless using Galaxy "
                                  "LIMS as input)")),
        parser.add_argument("-n", "--numcores", type=int, default=1,
                            help="Total cores to use for processing")
        parser.add_argument("-t", "--paralleltype",
                            choices=["local", "ipython"],
                            default="local", help="Approach to parallelization")
        parser.add_argument("-w", "--workflow",
                            help=("Run a workflow with the given commandline "
                                  "arguments"))
        parser.add_argument("-q", "--queue",
                            help=("Scheduler queue to run jobs on, for "
                                  "ipython parallel"))
        parser.add_argument("--local_controller",
                            default=False,
                            action="store_true",
                            help="run controller locally")
        parser.add_argument("-s", "--scheduler",
                            choices=["lsf", "sge", "torque", "slurm", "pbspro"],
                            help="Scheduler to use for ipython parallel")
        parser.add_argument("-p", "--tag",
                            help="Tag name to label jobs on the cluster",
                            default="")
        parser.add_argument("-r", "--resources",
                            help=("Cluster specific resources specifications. "
                                  "Can be specified multiple times.\n"
                                  "Supports SGE, Torque, LSF and SLURM "
                                  "parameters."), default=[], action="append")
        parser.add_argument("--timeout", default=15, type=int,
                            help=("Number of minutes before cluster startup "
                                  "times out. Defaults to 15"))
        parser.add_argument("--retries", default=0, type=int,
                            help=("Number of retries of failed tasks during "
                                  "distributed processing. Default 0 "
                                  "(no retries)"))
        parser.add_argument("--workdir", default=os.getcwd(),
                            help=("Directory to process in. Defaults to "
                                  "current working directory"))
        parser.add_argument("--only-metadata", help=argparse.SUPPRESS, action="store_true", default=False)
        parser.add_argument("--force-single", help="Treat all files as single reads",
                            action="store_true", default=False)
        parser.add_argument("--separators", help="comma separated list of separators that indicates paired files.",
                            default="R,_,-,.")

    args = parser.parse_args(in_args)

    if hasattr(args, "workdir") and args.workdir:
        utils.safe_makedir(args.workdir)

    if hasattr(args, "global_config"):
        error_msg = _sanity_check_args(args)
        if error_msg:
            parser.error(error_msg)

        kwargs = {"parallel": clargs.to_parallel(args),
                  "workflow": args.workflow,
                  "workdir": args.workdir}
        kwargs = _add_inputs_to_kwargs(args, kwargs, parser)
        error_msg = _sanity_check_kwargs(kwargs)
        if error_msg:
            parser.error(error_msg)
    else:
        assert sub_cmd is not None
        kwargs = {
            "args" : args,
            "config_file" : None,
            sub_cmd : True
        }
    print(args)
    return kwargs


def _sanity_check_kwargs(args):
    """Sanity check after setting up input arguments, handling back compatibility
    """
    if not args.get("workflow") and not args.get("run_info_yaml"):
        return ("Require a sample YAML file describing inputs: "
                "https://bcbio-nextgen.readthedocs.org/en/latest/contents/configuration.html")


def _add_inputs_to_kwargs(args, kwargs, parser):
    """Convert input system config, flow cell directory and sample yaml to kwargs.

    Handles back compatibility with previous commandlines while allowing flexible
    specification of input parameters.
    """
    inputs = [x for x in [args.global_config, args.fc_dir] + args.run_config
              if x is not None]
    global_config = "bcbio_system.yaml"  # default configuration if not specified
    if kwargs.get("workflow", "") == "template":
        if args.only_metadata:
            inputs.append("--only-metadata")
        if args.force_single:
            inputs.append("--force-single")
        if args.separators:
            inputs.extend(["--separators", args.separators])
        kwargs["inputs"] = inputs
        return kwargs
    elif len(inputs) == 1:
        if os.path.isfile(inputs[0]):
            fc_dir = None
            run_info_yaml = inputs[0]
        else:
            fc_dir = inputs[0]
            run_info_yaml = None
    elif len(inputs) == 2:
        if os.path.isfile(inputs[0]):
            global_config = inputs[0]
            if os.path.isfile(inputs[1]):
                fc_dir = None
                run_info_yaml = inputs[1]
            else:
                fc_dir = inputs[1]
                run_info_yaml = None
        else:
            fc_dir, run_info_yaml = inputs
    elif len(inputs) == 3:
        global_config, fc_dir, run_info_yaml = inputs
    elif args.version:
        print(version.__version__)
        sys.exit()
    else:
        print("Incorrect input arguments", inputs)
        parser.print_help()
        sys.exit()
    if fc_dir:
        fc_dir = os.path.abspath(fc_dir)
    if run_info_yaml:
        run_info_yaml = os.path.abspath(run_info_yaml)
    if kwargs.get("workflow"):
        kwargs["inputs"] = inputs
    kwargs["config_file"] = global_config
    kwargs["fc_dir"] = fc_dir
    kwargs["run_info_yaml"] = run_info_yaml
    return kwargs

def _sanity_check_args(args):
    """Ensure dependent arguments are correctly specified
    """
    if "scheduler" in args and "queue" in args:
        if args.scheduler and not args.queue:
            if args.scheduler != "sge":
                return "IPython parallel scheduler (-s) specified. This also requires a queue (-q)."
        elif args.queue and not args.scheduler:
            return "IPython parallel queue (-q) supplied. This also requires a scheduler (-s)."
        elif args.paralleltype == "ipython" and (not args.queue or not args.scheduler):
            return "IPython parallel requires queue (-q) and scheduler (-s) arguments."

if __name__ == '__main__':
    # sys.argv.extend(['upgrade' ,  '--tooldir', '/usr/local', '--genomes', 'GRCh37', '--aligners', 'bwa', '--aligners', 'bowtie2', '--data'])

    sys.argv.extend(['-w', 'template', r'D:\python-projects\my_bcbio\config\gatk-variant.yaml', 'project1', 'sample1.bam', 'sample2_1.fq', 'sample2_2.fq'])
    # sys.argv.extend([ '-h'])

    kwargs = parse_cl_args(sys.argv[1:])
    if "upgrade" in kwargs and kwargs['upgrade']:
        install.upgrade_bcbio(kwargs['args'])
    else:
        if kwargs.get("workflow"):
            setup_info = workflow.setup(kwargs['workflow'], kwargs.pop("inputs"))
    print (kwargs)
