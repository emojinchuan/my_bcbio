import os
import sys

def add_subparser(subparser):
    parser = subparser.add_parser("runfn", help=("Run a specific bcbio-nextgen function."
                                                  "Intended for distributed use."))
    parser.add_argument("name", help="Name of the function to run")
    parser.add_argument("argfile", help="JSON file with arguments to the function")
    parser.add_argument("moreargs", nargs="*", help="Additional arguments to pass in the case of raw input")
    parser.add_argument("--raw", action="store_true", default=False,
                        help="Treat the inputs as raw file arguments to the function, instead of parsing them.")
    parser.add_argument("-o", "--outfile", help="Output file to write, defaults to inputfile-out.yaml")
