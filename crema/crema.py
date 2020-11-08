"""
This is the command line interface for crema
"""
import os
import sys
import time
import logging

from parsers import *
from params import Params
from methods import calculate_tdc


def main():
    """The CLI entry point"""
    start_time = time.time()

    # Creates the parser for parse args and reads in command line arguments
    params = Params().parser
    args = params.parse_args()

    if args.logging is not None:
        logging.basicConfig(
            filename=os.path.join(args.logging, "crema.logfile.log"),
            level=logging.INFO,
            format="%(asctime)s %(message)s",
        )

    logging.info("crema")
    logging.info("Written by Donavan See (seed99@cs.washington.edu) in the")
    logging.info(
        "Department of Genome Sciences at the University of " "Washington."
    )
    logging.info("Command issued:")
    logging.info("%s", " ".join(sys.argv))
    logging.info("")
    logging.info("Starting Analysis")
    logging.info("=================")

    # Create dataset object
    logging.info("Creating dataset object...")
    if args.crux:
        psms = read_crux(args.input_files)
    else:
        psms = read_file(
            args.input_files, args.spectrum, args.score, args.target
        )

    # Run confidence estimate method
    logging.info("Calculating confidence estimate...")
    result = calculate_tdc(psms)

    # Write result to file
    logging.info("Writing to file...")
    out_file = "crema.psm_results.txt"
    if args.file_root is not None:
        out_file = args.file_root + out_file
    result.write_csv(os.path.join(args.output_dir, out_file))

    # Calculate how long the confidence estimation took
    end_time = time.time()
    total_time = end_time - start_time

    logging.info("=== DONE! ===")
    logging.info("Time Taken:" + str(total_time))


if __name__ == "__main__":
    main()
