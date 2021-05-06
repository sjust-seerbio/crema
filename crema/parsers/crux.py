"""A parser for the crux tab-delimited format"""
import logging
import re

import time
import pandas as pd
from .txt import read_txt
from ..utils import listify

LOGGER = logging.getLogger(__name__)


def read_crux(txt_files, copy_data=True):
    """Read peptide-spectrum matches (PSMs) from Crux tab-delimited files.

    Parameters
    ----------
    txt_files : str, pandas.DataFrame or tuple of str
        One or more collection of PSMs in the Crux tab-delimited format.
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
    spectrum = ["scan", "spectrum precursor m/z"]

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
    }

    # Keep only crux scores that exist in all of the files.
    if isinstance(txt_files, pd.DataFrame):
        scores = scores.intersection(set(txt_files.columns))
    else:
        txt_files = listify(txt_files)
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
    fields = spectrum + [peptide] + [target] + scores
    pairing_fields = ["peptide mass", "sequence", "target/decoy", "original target sequence"]
    if isinstance(txt_files, pd.DataFrame):
        data = txt_files.copy(deep=copy_data).loc[:, fields]
        pairing_data = txt_files.copy(deep=copy_data).loc[:, pairing_fields]
    else:
        data = pd.concat([_parse_psms(f, fields) for f in txt_files])
        pairing_data = pd.concat([_parse_psms(f, pairing_fields) for f in txt_files])

    psms = read_txt(
        data,
        target_column=target,
        spectrum_columns=spectrum,
        score_columns=scores,
        peptide_column=peptide,
        sep="\t",
        copy_data=False,
    )
    psms.add_peptide_pairing(_create_pairing(pairing_data))
    return psms


def _parse_psms(txt_file, cols):
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
    LOGGER.info("Reading PSMs from %s...", txt_file)
    return pd.read_csv(txt_file, sep="\t", usecols=lambda c: c in cols)


def _create_pairing(pairing_data):
    """Parse a single Crux tab-delimited file

    Parameters
    ----------
    pairing_data : pandas.DataFrame
        A collection of PSMs with the necessary columns to create a target/decoy peptide pairing.
        Required columns are "peptide mass", "sequence", "target/decoy", "original target sequence"

    Returns
    -------
    pairing : dict
        A map of target and decoy peptide sequence pairings
    """
    # split pairing_data into targets and decoys
    targets = pairing_data[pairing_data["target/decoy"] == "target"]\
        .drop_duplicates(["peptide mass", "sequence"])\
        .sample(frac=1).reset_index(drop=True)
    decoys = pairing_data[pairing_data["target/decoy"] == "decoy"]\
        .drop_duplicates(["peptide mass", "sequence"])\
        .sample(frac=1).sort_values("original target sequence")\
        .reset_index(drop=True)

    targets = pd.concat(
        [targets, targets["sequence"].str.replace(r"\[\d+.\d+\]", "", regex=True).rename("raw_sequence")], axis=1
    )

    pairing = {}
    del_row = set()
    for mass, sequence, raw_sequence in zip(targets["peptide mass"], targets["sequence"], targets["raw_sequence"]):
        if sequence in pairing:
            continue
        # try to make faster?
        left = decoys["original target sequence"].searchsorted(raw_sequence, side="left")
        right = decoys["original target sequence"].searchsorted(raw_sequence, side="right")
        sub_decoy = decoys.iloc[left:right]
        for d_index, d_mass, d_sequence in zip(sub_decoy.index, sub_decoy["peptide mass"], sub_decoy["sequence"]):
            if d_index in del_row:
                continue
            if _check_match(mass, sequence, d_mass, d_sequence):
                pairing[sequence] = d_sequence
                pairing[d_sequence] = d_sequence
                del_row.add(d_index)
                break
        if sequence not in pairing:
            pairing[sequence] = sequence
    return pairing


def _check_match(target_mass, target_sequence, decoy_mass, decoy_sequence):
    """Check if a target peptide and decoy peptide make a valid pair

    Parameters
    ----------
    target_mass : double
        The peptide mass of the given target peptide
    target_sequence : str
        The peptide sequence of the given target peptide
    decoy_mass : double
        The peptide mass of the given decoy peptide
    decoy_sequence : str
        The peptide sequence of the given decoy peptide

    Returns
    -------
    bool
        True if the peptides make a valid pair, false otherwise. Valid peptide pairs
        are shuffled versions of one another with identical mass and identical
        amino acid modification
    """
    # check that peptides have identical mass
    if target_mass != decoy_mass:
        return False
    # check that modifications are on the same amino acids
    target_mod = sorted(re.findall(r'\w\[\d+.\d+\]', target_sequence))
    decoy_mod = sorted(re.findall(r'\w\[\d+.\d+\]', decoy_sequence))
    return target_mod == decoy_mod
