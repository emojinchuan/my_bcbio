import argparse
import sys,os,yaml
import contextlib
from six.moves import urllib
import collections

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
    project_name, metadata, global_vars, md_file = _pname_and_metadata(args.metadata)
    remotes = {}
    inputs = args.input_files
    raw_items = [_add_metadata(item, metadata, remotes, args.only_metadata)
                 for item in _prep_items_from_base(base_item, inputs, metadata,
                                                   args.separators.split(","), args.force_single)]

def _add_metadata(item, metadata, remotes, only_metadata=False):
    """Add metadata information from CSV file to current item.

    Retrieves metadata based on 'description' parsed from input CSV file.
    Adds to object and handles special keys:
    - `description`: A new description for the item. Used to relabel items
       based on the pre-determined description from fastq name or BAM read groups.
    - Keys matching supported names in the algorithm section map
      to key/value pairs there instead of metadata.
    """
    for check_key in [item["description"]] + _get_file_keys(item) + _get_vrn_keys(item):
        item_md = metadata.get(check_key)
        if item_md:
            break
    if not item_md:
        item_md = _find_glob_metadata(item["files"], metadata)
    if remotes.get("region"):
        item["algorithm"]["variant_regions"] = remotes["region"]
    TOP_LEVEL = set(["description", "genome_build", "lane", "vrn_file", "files", "analysis"])
    keep_sample = True
    if item_md and len(item_md) > 0:
        if "metadata" not in item:
            item["metadata"] = {}
        for k, v in item_md.items():
            if v:
                if k in TOP_LEVEL:
                    item[k] = v
                elif k in run_info.ALGORITHM_KEYS:
                    v = _handle_special_yaml_cases(v)
                    item["algorithm"][k] = v
                else:
                    v = _handle_special_yaml_cases(v)
                    item["metadata"][k] = v
    elif len(metadata) > 0:
        warn = "Dropped sample" if only_metadata else "Added minimal sample information"
        print("WARNING: %s: metadata not found for %s, %s" % (warn, item["description"],
                                                              [os.path.basename(f) for f in item["files"]]))
        keep_sample = not only_metadata
    if tz.get_in(["metadata", "ped"], item):
        item["metadata"] = _add_ped_metadata(item["description"], item["metadata"])
    return item if keep_sample else None


def _prep_items_from_base(base, in_files, metadata, separators, force_single=False):
    """Prepare a set of configuration items for input files.
    """
    details = []
    # in_files = _expand_dirs(in_files, KNOWN_EXTS) ##将in_files 里边的目录转换成KNOWN_EXTS后缀的文件
    # in_files = _expand_wildcards(in_files)

    ext_groups = collections.defaultdict(list)
    for ext, files in itertools.groupby(
            in_files, lambda x: KNOWN_EXTS.get(utils.splitext_plus(x)[-1].lower())):
        ext_groups[ext].extend(list(files))
    for ext, files in ext_groups.items():
        if ext == "bam":
            for f in files:
                details.append(_prep_bam_input(f, base))
        elif ext in ["fastq", "fq", "fasta"]:
            files, glob_files = _find_glob_matches(files, metadata)
            for fs in glob_files:
                details.append(_prep_fastq_input(fs, base))
            for fs in fastq.combine_pairs(files, force_single, separators=separators):
                details.append(_prep_fastq_input(fs, base))
        elif ext in ["vcf"]:
            for f in files:
                details.append(_prep_vcf_input(f, base))
        else:
            print("Ignoring unexpected input file types %s: %s" % (ext, list(files)))
    return details

def _pname_and_metadata(in_file):
    """Retrieve metadata and project name from the input metadata CSV file.

    Uses the input file name for the project name and for back compatibility,
    accepts the project name as an input, providing no metadata.
    """


    if in_file.endswith(".csv"):
        raise ValueError("Did not find input metadata file: %s" % in_file)
    base, md, global_vars = in_file, {}, {}
    md_file = None
    return base, md, global_vars, md_file

def name_to_config(template):
    """Read template file into a dictionary to use as base for all samples.

    Handles well-known template names, pulled from GitHub repository and local
    files.
    """

    base_url = "https://raw.github.com/bcbio/bcbio-nextgen/master/config/templates/%s.yaml"
    if os.path.isfile(template):
        if template.endswith(".csv"):
            raise ValueError("Expected YAML file for template and found CSV, are arguments switched? %s" % template)
        with open(template) as in_handle:
            txt_config = in_handle.read()
        with open(template) as in_handle:
            config = yaml.safe_load(in_handle)
    else:
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
