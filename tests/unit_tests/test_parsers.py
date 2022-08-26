"""
These are unit tests for functions within parsers.py:
"""
import pytest
import pandas as pd

import crema


def test_read_crux(real_crux_txt):
    """Test that we parse crux files correctly"""
    psms = crema.read_crux(real_crux_txt)
    assert isinstance(psms.data, pd.DataFrame)
    assert psms.data.shape == (21818, 12)
    assert list(psms.spectra.columns) == ["file", "scan"]

    scores = {
        "refactored xcorr",
        "combined p-value",
        "exact p-value",
        "sp score",
        "delta_cn",
        "delta_lcn",
        "res-ev p-value",
    }
    assert set(psms.score_columns) == scores
    assert psms.scores.shape == (21818, len(scores))
    assert psms.targets.shape == (21818,)
    assert psms.targets.sum() == 10909
    assert (~psms.targets).sum() == 10909


def test_read_crux_peptide_pairing(mod_target_crux_txt, mod_decoy_crux_txt):
    """Test that peptide pairing is correctly created when parsing crux files"""
    expected_peptide_pairing = {
        "ALLSLR": "ALLLSR",
        "QTPPAR": "QTAPPR",
        "GEVPN[0.98]R": "GN[0.98]PEVR",
        "GGHMDR": "GDMGHR",
    }
    psms = crema.read_crux(
        [mod_decoy_crux_txt, mod_target_crux_txt],
    )
    assert expected_peptide_pairing == psms.peptide_pairing


def test_read_comet_peptide_pariring(mod_comet_txt):
    """Test that peptide paiing is correctly create when parsing comet file"""
    expected_peptide_pairing = {
        "A[15.9949]PPLE": "A[15.9949]LPPE",
        "BANANA": "BNANAA",
        "CH[15.9949]E[15.9949]RRY": "CRRE[15.9949]H[15.9949]Y",
        "DURIAN": "DAIRUN",
        "EGGPLANT": "ENALPGGT",
        "FIGS": "FGIS",
        "GRAPE": "GPARE",
        "H[15.9949]ONEYDE[15.9949]W": "H[15.9949]E[15.9949]DYENOW",
        "IC[15.9949]ES": "IEC[15.9949]S",
        "JAMS": "JMAS",
    }
    psms = crema.read_comet(mod_comet_txt)
    for key in expected_peptide_pairing:
        print(key, expected_peptide_pairing[key], psms.peptide_pairing[key])
    assert expected_peptide_pairing == psms.peptide_pairing


def test_read_txt(basic_crux_csv):
    """Test that we can read generic delimited files"""
    psms = crema.read_txt(
        basic_crux_csv,
        target_column="target/decoy",
        spectrum_columns="scan",
        score_columns=["combined p-value", "x"],
        peptide_column="sequence",
        protein_column="protein id",
        protein_delim=",",
        sep=",",
    )
    assert isinstance(psms.data, pd.DataFrame)
    assert psms.data.shape == (10, 6)
    assert psms.spectra.columns == ["scan"]
    assert set(psms.score_columns) == {"combined p-value", "x"}
    assert psms.peptides.name == "sequence"
    assert psms.proteins.name == "protein id"
    assert psms.targets.shape == (10,)
    assert psms.targets.sum() == 6
    assert (~psms.targets).sum() == 4


def test_read_mztab(real_mztab):
    # This test suposed to raise error as mzID file does not
    # contain decoy PSMs
    with pytest.raises(ValueError):
        psms = crema.read_mztab(real_mztab)


def test_read_pepxml(real_pepxml):
    try:
        psms = crema.read_pepxml(real_pepxml, "decoy_")
    except Exception as exc:
        assert False, f"'test_read_pepxml' raised an exception {exc}"
