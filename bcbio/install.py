from __future__ import print_function
import os,sys
import utils
import yaml
import contextlib
import subprocess

REMOTES = {
    "requirements": "https://raw.githubusercontent.com/bcbio/bcbio-nextgen/master/requirements-conda.txt",
    "gitrepo": "https://github.com/bcbio/bcbio-nextgen.git",
    "cloudbiolinux": "https://github.com/chapmanb/cloudbiolinux/archive/master.tar.gz",
    "genome_resources": "https://raw.github.com/bcbio/bcbio-nextgen/master/config/genomes/%s-resources.yaml",
    "snpeff_dl_url": ("http://downloads.sourceforge.net/project/snpeff/databases/v{snpeff_ver}/"
                      "snpEff_v{snpeff_ver}_{genome}.zip")}
SUPPORTED_GENOMES = ["GRCh37", "hg19", "hg38", "hg38-noalt", "mm10", "mm9",
                     "rn6", "rn5", "canFam3", "dm3", "galGal4", "phix",
                     "pseudomonas_aeruginosa_ucbpp_pa14", "sacCer3", "TAIR10",
                     "WBcel235", "xenTro3", "GRCz10", "GRCz11", "Sscrofa11.1", "BDGP6"]
TARBALL_DIRECTORIES = ["bwa", "rtg", "hisat2"]
SUPPORTED_INDEXES = TARBALL_DIRECTORIES + ["bbmap", "bowtie", "bowtie2", "minimap2", "novoalign", "twobit",
                                           "snap", "star", "seq"]

def add_subparser(subparser):
    parser = subparser.add_parser("upgrade", help = "Install or upgrade bcbio-nextgen")
    parser.add_argument("--tooldir",
                        help="Directory to install 3rd party software tools. Leave unspecified for no tools",
                        type=lambda x: (os.path.abspath(os.path.expanduser(x))), default=None)
    parser.add_argument("--genomes", help="Genomes to download",
                        action="append", default=[], choices=SUPPORTED_GENOMES)
    parser.add_argument("--aligners", help="Aligner indexes to download",
                        action="append", default=[],
                        choices=SUPPORTED_INDEXES)
    parser.add_argument("--data", help="Upgrade data dependencies",
                        dest="install_data", action="store_true", default=False)
    parser.add_argument("-u", "--upgrade", help="Code version to upgrade",
                        choices=["stable", "development", "system", "deps", "skip"], default="skip")
    parser.add_argument("--tools",
                        help="Boolean argument specifying upgrade of tools. Uses previously saved install directory",
                        action="store_true", default=False)
    parser.add_argument("--datatarget", help="Data to install. Allows customization or install of extra data.",
                        action="append", default=[],
                        choices=["variation", "rnaseq", "smallrna", "gemini", "cadd", "vep", "dbnsfp", "dbscsnv", "battenberg", "kraken", "ericscript", "gnomad"])
    parser.add_argument("--isolate", help="Created an isolated installation without PATH updates",
                        dest="isolate", action="store_true", default=False)
def upgrade_bcbio(args):
    print("Upgrading bcbio")
    args = add_install_defaults(args)

    if args.tooldir:
        with bcbio_tmpdir():
            print("Upgrading third party tools to latest versions")
            _symlink_bcbio(args, script="bcbio_nextgen.py")
            _symlink_bcbio(args, script="bcbio_setup_genome.py")
            _symlink_bcbio(args, script="bcbio_prepare_samples.py")
            _symlink_bcbio(args, script="bcbio_fastq_umi_prep.py")
            if args.cwl:
                _symlink_bcbio(args, "bcbio_vm.py", "bcbiovm")
                _symlink_bcbio(args, "python", "bcbiovm", "bcbiovm")
            upgrade_thirdparty_tools(args, REMOTES)
            print("Third party tools upgrade complete.")

def upgrade_thirdparty_tools(args, remotes):
    cbl = get_cloudbiolinux(remotes)
    package_yaml = os.path.join(cbl["dir"], "contrib", "flavor",
                            "ngs_pipeline_minimal", "packages-conda.yaml")
    sys.path.insert(0,cbl['dir'])
    cbl_conda = __import__("cloudbio.package.conda", fromlist=['conda'])
    cbl_conda.install_in(_get_conda_bin(),args.tooldir, package_yaml)
    manifest_dir = os.path.join(_get_data_dir(), 'manifest')
    print("Creating manifest of installed packages in %s" % manifest_dir)
    cbl_manifest = __import__("cloudbio.manifest", fromlist=["manifest"])
    if os.path.exists(manifest_dir):
        for fname in os.listdir(manifest_dir):
            if not fname.startswith("toolplus"):
                os.remove(os.path.join(manifest_dir, fname))
    cbl_manifest.create(manifest_dir, args.tooldir)


def _get_conda_bin():
    conda_bin = os.path.join(os.path.dirname(os.path.realpath(sys.executable)), "conda")
    if os.path.exists(conda_bin):
        return conda_bin

def get_cloudbiolinux(remotes):
    base_dir = os.path.join(os.getcwd(),"cloudbiolinux")
    if not os.path.exists(base_dir):
        subprocess.check_call("wget --progress=dot:mega --no-check-certificate -O- %s | tar xz && "
                              "(mv cloudbiolinux-master cloudbiolinux || mv master cloudbiolinux)"
                              % remotes["cloudbiolinux"], shell=True)
    return {"biodata": os.path.join(base_dir, "config", "biodata.yaml"),
            "dir": base_dir}


def _symlink_bcbio(args, script="bcbio_nextgen.py", env_name=None, prefix=None):
    """Ensure a bcbio-nextgen script symlink in final tool directory.
    """
    if env_name:
        bcbio_anaconda = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(sys.executable))),
                                      "envs", env_name, "bin", script)
    else:
        bcbio_anaconda = os.path.join(os.path.dirname(os.path.realpath(sys.executable)), script)
    bindir = os.path.join(args.tooldir, "bin")
    if not os.path.exists(bindir):
        os.makedirs(bindir)
    if prefix:
        script = "%s_%s" % (prefix, script)
    bcbio_final = os.path.join(bindir, script)
    if not os.path.exists(bcbio_final):
        if os.path.lexists(bcbio_final):
            subprocess.check_call(["rm", "-f", bcbio_final])
        subprocess.check_call(["ln", "-s", bcbio_anaconda, bcbio_final])

def add_install_defaults(args):

    if len(args.genomes) > 0 or len(args.aligners) > 0 or len(args.datatarget) > 0:
        args.install_data = True

    install_config = _get_install_config()
    if install_config is None or not utils.file_exists(install_config):
        default_args = {}
    else:
        with open(install_config) as in_handle:
            default_args = yaml.safe_load(in_handle)

    if args.upgrade in ['development'] and (args.tooldir or "tooldir" in default_args):
        args.tooldir = True

    if args.tools and args.tooldir is None:
        if "tooldir" in default_args:
            args.tooldir = str(default_args['tooldir'])
        else:
            raise ValueError("Default tool directory not yet saved in config defaults. "
                             "Specify the '--tooldir=/path/to/tools' to upgrade tools. "
                             "After a successful upgrade, the '--tools' parameter will "
                             "work for future upgrades.")
    for attr in ['genomes', 'aligners']:
        if attr == "genomes" and len(args.genomes) > 0:
            continue
        for x in default_args.get(attr, []):
            x = str(x)
            new_val = getattr(args, attr)
            if x not in getattr(args, attr):
                new_val.append(x)
            setattr(args, attr, new_val)

    ###here
    args = _datatarget_defaults(args, default_args)
    if "isolate" in default_args and args.isolate is not True:
        args.isolate = default_args["isolate"]
    return args
def _datatarget_defaults(args, default_args):
    """Set data installation targets, handling defaults.

    Sets variation, rnaseq, smallrna as default targets if we're not
    isolated to a single method.

    Provides back compatibility for toolplus specifications.
    """
    default_data = default_args.get("datatarget", [])
    # back-compatible toolplus specifications
    for x in default_args.get("toolplus", []):
        val = None
        if x == "data":
            val = "gemini"
        elif x in ["cadd", "dbnsfp", "dbscsnv", "kraken", "gnomad"]:
            val = x
        if val and val not in default_data:
            default_data.append(val)
    new_val = getattr(args, "datatarget")
    for x in default_data:
        if x not in new_val:
            new_val.append(x)
    has_std_target = False
    std_targets = ["variation", "rnaseq", "smallrna"]
    for target in std_targets:
        if target in new_val:
            has_std_target = True
            break
    if not has_std_target:
        new_val = new_val + std_targets
    setattr(args, "datatarget", new_val)
    return args

def _get_install_config():
    try:
        data_dir = _get_data_dir()
    except ValueError:
        return None
    config_dir = os.path.join(data_dir, "config")
    # config_dir = utils.safe_makedir(os.path.join(data_dir, "config"))
    return os.path.join(config_dir, "install-params.yaml")

def _get_data_dir():
    print(sys.executable)
    base_dir = os.path.realpath(os.path.dirname(os.path.dirname(os.path.realpath(sys.executable))))
    return os.path.dirname(base_dir)

@contextlib.contextmanager
def bcbio_tmpdir():
    orig_dir = os.getcwd()
    work_dir = os.path.join(os.getcwd(), "tmpbcbio-install")
    if not os.path.exists(work_dir):
        os.makedirs(work_dir)
    os.chdir(work_dir)
    yield work_dir
    os.chdir(orig_dir)
    shutil.rmtree(work_dir)
