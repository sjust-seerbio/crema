"""A parser for the crux tab-delimited format"""
import re
import logging

import pandas as pd

from .txt import read_txt
from .. import utils

LOGGER = logging.getLogger(__name__)


def read_crux(txt_files, pairing_file_name=None, copy_data=True):
    """Read peptide-spectrum matches (PSMs) from Crux tab-delimited files.

    Parameters
    ----------
    txt_files : str, pandas.DataFrame or tuple of str
        One or more collection of PSMs in the Crux tab-delimited format.
    pairing_file_name : str, optional
        A tab-delimited file that explicity pairs target and decoy peptide
        sequences. Requires one column labled 'target' that contains target
        sequences and a second colun labeled 'decoy' that contains decoy
        sequences. This file can be generated by setting --peptide-list=T
        in tide-index.
    copy_data : bool, optional
        If true, a deep copy of the data is created. This uses more memory, but
        is safer because it prevents accidental modification of the underlying
        data. This argument only has an effect when `txt_files` is a
        :py:class:`pandas.DataFrame`

    Returns
    -------
    PsmDataset
        A :py:class:`~crema.dataset.PsmDataset` object containing the parsed
        PSMs.
    """
    target = "target/decoy"
    peptide = "sequence"
    spectrum = ["file", "scan"]
    pairing = "original target sequence"
    protein = "protein id"
    protein_delim = ","

    # Possible score columns output by Crux.
    scores = {
        "sp score",
        "delta_cn",
        "delta_lcn",
        "xcorr score",
        "exact p-value",
        "refactored xcorr",
        "res-ev p-value",
        "combined p-value",
        "tailor score",
    }

    # Keep only crux scores that exist in all of the files.
    if isinstance(txt_files, pd.DataFrame):
        scores = scores.intersection(set(txt_files.columns))
    else:
        txt_files = utils.listify(txt_files)
        for txt_file in txt_files:
            with open(txt_file) as txt_ref:
                cols = txt_ref.readline().rstrip().split("\t")
                scores = scores.intersection(set(cols))

    if not scores:
        raise ValueError(
            "Could not find any of the Crux score columns in all of the files."
            f"The columns crema looks for are {', '.join(list(scores))}"
        )

    scores = list(scores)

    # Read in the files:
    fields = spectrum + [peptide] + [target] + scores + [pairing] + [protein]
    if isinstance(txt_files, pd.DataFrame):
        data = txt_files.copy(deep=copy_data).loc[:, fields]
    else:
        data = pd.concat([_parse_psms(f, fields) for f in txt_files])

    psms = read_txt(
        data,
        target_column=target,
        spectrum_columns=spectrum,
        score_columns=scores,
        peptide_column=peptide,
        protein_column=protein,
        protein_delim=protein_delim,
        sep="\t",
        copy_data=False,
    )

    # always pair target and decoys for Crux
    if pairing_file_name == None:  # implicit pairing
        psms._peptide_pairing = _create_pairing(data)
    else:  # explicit pairing
        psms._peptide_pairing = utils.create_pairing_from_file(
            pairing_file_name
        )

    # Remove the start position of peptide in protein if present
    # This looks like "protName(XX)"
    # Remove decoy prefix from protein ID
    protein_column = psms.data[protein]
    new_protein_column = protein_column.str.replace(
        "\\([^()]*\\)", "", regex=True
    )
    new_protein_column = new_protein_column.str.replace(
        "decoy_", "", regex=True
    )
    psms.set_protein_column(new_protein_column)
    print(psms)

    return psms


def _parse_psms(txt_file, cols, log=True):
    """Parse a single Crux tab-delimited file

    Parameters
    ----------
    txt_file : str
        The crux tab-delimited file to read.
    cols : list of str
        The columns to parse.

    Returns
    -------
    pandas.DataFrame
        A :py:class:`pandas.DataFrame` containing the parsed PSMs
    """
    if log:
        LOGGER.info("Reading PSMs from %s...", txt_file)
    return pd.read_csv(txt_file, sep="\t", usecols=lambda c: c in cols)


def _create_pairing(pairing_data):
    """Parse a single Crux tab-delimited file

    Parameters
    ----------
    pairing_data : pandas.DataFrame
        A collection of PSMs with the necessary columns to create a
        target/decoy peptide pairing. Required columns are "peptide mass",
        "sequence", "target/decoy", "original target sequence"

    Returns
    -------
    pairing : dict
        A map of target and decoy peptide sequence pairings. Targets with
        missing decoys will not be included among the keys.

    """
    # ensure pairing_data dataframe contains all necessary columns
    seq = "original target sequence"
    req_fields = [
        "sequence",
        "target/decoy",
        "original target sequence",
    ]

    if not set(req_fields).issubset(pairing_data.columns):
        miss = ", ".join(set(req_fields) - set(pairing_data.columns))
        raise ValueError(
            f"Required columns for peptide pairing were not detected: {miss}"
        )

    pairing_data = pairing_data.loc[:, req_fields]
    pairing_data = (
        pairing_data.sample(frac=1)
        .drop_duplicates(["sequence"])
        .reset_index(drop=False)
    )

    # Add a column of the sorted peptide:
    pairing_data["mods"] = (
        pairing_data["sequence"]
        .str.split("(?=[A-Z])")
        .apply(lambda x: "".join(sorted(x)))
    )

    # Split targets and decoys:
    is_decoy = pairing_data["target/decoy"] == "decoy"
    pairing_data = pairing_data.drop("target/decoy", axis=1)
    targets = pairing_data.loc[~is_decoy, :].copy()
    decoys = pairing_data.loc[is_decoy, :].copy()

    # Strip the target sequence modifications:
    targets[seq] = targets["sequence"].str.replace(r"\[.*?\]", "", regex=True)

    # Add an 'ord' column to disambiguate multiple matches per peptide:
    targets["ord"] = targets.groupby([seq, "mods"])["sequence"].rank("first")
    decoys["ord"] = decoys.groupby([seq, "mods"])["sequence"].rank("first")

    # Inner join the DataFrames to induce a pairing.
    # Targets with a missing decoy will be dropped.
    # Decoys with a missing target will be dropped.
    merged = pd.merge(
        targets,
        decoys,
        how="inner",
        on=[seq, "mods", "ord"],
        suffixes=["_t", "_d"],
    )

    return merged.set_index("sequence_t").loc[:, "sequence_d"].to_dict()
