import argparse
import sys,yaml
import contextlib
from six.moves import urllib

class HelpArgParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('error: %s\n' % message)
        self.print_help()
        sys.exit(2)


def parse_args(inputs):
    parser = HelpArgParser(
        description="Create a bcbio_sample.yaml file from a standard template and inputs")
    parser = setup_args(parser)
    args = parser.parse_args(inputs)
    if args.template.endswith("csv"):
        parser.print_help()
        print("\nError: Looks like you've swapped the order of the metadata CSV and template YAML arguments, it should go YAML first, CSV second.")
        sys.exit(1)
    return parser.parse_args(inputs)

def setup_args(parser):
    parser.add_argument("template", help=("Template name or path to template YAML file. "
                                          "Built in choices: freebayes-variant, gatk-variant, tumor-paired, "
                                          "noalign-variant, illumina-rnaseq, illumina-chipseq"))
    parser.add_argument("metadata", help="CSV file with project metadata. Name of file used as project name.")
    parser.add_argument("input_files", nargs="*", help="Input read files, in BAM or fastq format")
    parser.add_argument("--only-metadata", help="Ignore samples not present in metadata CSV file",
                        action="store_true", default=False)
    parser.add_argument("--force-single", help="Treat all files as single reads",
                        action="store_true", default=False)
    parser.add_argument("--separators", help="semicolon separated list of separators that indicates paired files.",
                        default="R,_,-,.")
    # setup_script_logging()
    return parser

def setup(args):
    template, template_txt = name_to_config(args.template)
    base_item = template["details"][0]

def name_to_config(template):
    """Read template file into a dictionary to use as base for all samples.

    Handles well-known template names, pulled from GitHub repository and local
    files.
    """

    base_url = "https://raw.github.com/bcbio/bcbio-nextgen/master/config/templates/%s.yaml"
    try:
        with contextlib.closing(urllib.request.urlopen(base_url % template)) as in_handle:
            txt_config = in_handle.read().decode()
        with contextlib.closing(urllib.request.urlopen(base_url % template)) as in_handle:
            config = yaml.safe_load(in_handle)
    except (urllib.error.HTTPError, urllib.error.URLError):
        raise ValueError("Could not find template '%s' locally or in standard templates on GitHub"
                         % template)
    return config, txt_config

def setup_script_logging():
    """
    Use this logger for standalone scripts, or script-like subcommands,
    such as bcbio_prepare_samples and bcbio_nextgen.py -w template.
    """
    #handlers = [logbook.NullHandler()]
    format_str = ("[{record.time:%Y-%m-%dT%H:%MZ}] "
                  "{record.level_name}: {record.message}")

    #handler = logbook.StreamHandler(sys.stderr, format_string=format_str,
      #                              level="DEBUG")
    #handler.push_thread()
    #return handler
