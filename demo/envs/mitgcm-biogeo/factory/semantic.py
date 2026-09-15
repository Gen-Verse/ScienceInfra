"""Semantic round: DATA-led biogeochemistry fits plus stateful protocols."""

import argparse
from collections import Counter
import json
import os
import re

import config


def candidate(cid, tree, relpath, old, new, family, tier, rationale, note,
              vein, target_checks=None):
    """Make an exact, invertible candidate and grow ambiguous anchors."""
    path = os.path.join(config.BASE, relpath)
    text = open(path, encoding="utf-8").read()
    if text.count(old) != 1:
        raise RuntimeError(
            f"{cid}: old occurs {text.count(old)} times in {relpath}")
    if old == new:
        raise RuntimeError(f"{cid}: ineffective edit")
    broken = text.replace(old, new, 1)
    if broken.count(new) != 1:
        pos = text.index(old)
        lo = text.rfind("\n", 0, pos) + 1
        hi = text.find("\n", pos + len(old))
        hi = len(text) if hi < 0 else hi + 1
        for _ in range(16):
            old_context = text[lo:hi]
            new_context = old_context.replace(old, new, 1)
            if text.count(old_context) == 1 and broken.count(new_context) == 1:
                old, new = old_context, new_context
                break
            lo = text.rfind("\n", 0, max(0, lo - 1)) + 1
            next_nl = text.find("\n", hi)
            hi = len(text) if next_nl < 0 else next_nl + 1
        else:
            raise RuntimeError(f"{cid}: inverse anchor cannot be made unique")
    line = text[:text.index(old)].count("\n") + 1
    return {
        "id": cid,
        "source": "semantic",
        "family": family,
        "tree": tree,
        "note": note,
        "break": {"edits": [{"file": relpath, "old": old, "new": new}]},
        "fix": {"edits": [{"file": relpath, "old": new, "new": old}]},
        "meta": {
            "file": relpath,
            "line": line,
            "predicted_tier": tier,
            "prediction_rationale": rationale,
            "semantic": True,
            "vein": vein,
            "target_checks": target_checks or [],
        },
    }


def line_edit(cid, tree, relpath, locator, before, after, family, tier,
              rationale, note, vein, occurrence=0, target_checks=None):
    text = open(os.path.join(config.BASE, relpath), encoding="utf-8").read()
    lines = text.splitlines(keepends=True)
    matches = [idx for idx, line in enumerate(lines) if locator in line]
    if occurrence >= len(matches):
        raise RuntimeError(f"{cid}: locator has only {len(matches)} matches")
    idx = matches[occurrence]
    old = lines[idx]
    if old.count(before) != 1:
        raise RuntimeError(f"{cid}: token occurs {old.count(before)} times in line")
    new = old.replace(before, after, 1)
    # Repeated source lines are disambiguated with nearby exact context.
    lo, hi = idx, idx + 1
    while text.count("".join(lines[lo:hi])) != 1 and (lo > 0 or hi < len(lines)):
        if lo > 0:
            lo -= 1
        if hi < len(lines):
            hi += 1
    old = "".join(lines[lo:hi])
    new = old.replace(before, after, 1)
    return candidate(cid, tree, relpath, old, new, family, tier, rationale,
                     note, vein, target_checks)


def swap_sections(cid, tree, relpath, first_start, first_end,
                  second_start, second_end, family, rationale, note,
                  target_checks):
    text = open(os.path.join(config.BASE, relpath), encoding="utf-8").read()
    a0 = text.index(first_start)
    a1 = text.index(first_end, a0) + len(first_end)
    b0 = text.index(second_start, a1)
    b1 = text.index(second_end, b0) + len(second_end)
    if not a0 < a1 <= b0 < b1:
        raise RuntimeError(f"{cid}: section order is not as expected")
    old = text[a0:b1]
    first, middle, second = text[a0:a1], text[a1:b0], text[b0:b1]
    new = second + middle + first
    return candidate(cid, tree, relpath, old, new, family, "hard", rationale,
                     note, "protocol", target_checks)


def generate():
    rows = []
    fit_rationale = (
        "The symptom is remote from this empirical multi-coefficient fit, and "
        "the exact incumbent entry is not derivable from neighboring arithmetic.")
    scalar_rationale = (
        "This calibrated ecosystem scalar is consumed nonlinearly downstream, "
        "while neither units nor neighboring defaults determine its exact value.")
    protocol_rationale = (
        "The end-state symptom is decoupled from a multi-stage state protocol, "
        "and local types do not encode the required ordering or phase.")

    # Carbonate-system empirical fits: classic DIC and SolveSAPHE paths.
    rel = "pkg/dic/carbon_chem.F"
    for args in [
        ("sem-data-dic-mehrbach-k1-invt", "ak1(i,j,bi,bj)=10.**", "3670.7", "3570.7",
         "perturb the inverse-temperature coefficient in the surface K1 fit"),
        ("sem-data-dic-mehrbach-k2-invt", "ak2(i,j,bi,bj)=10.**", "1394.7", "1494.7",
         "perturb the inverse-temperature coefficient in the surface K2 fit"),
        ("sem-data-dic-borate-invt", "akb(i,j,bi,bj)=exp((-8966.90", "-8966.90", "-8996.90",
         "perturb one coefficient in the boric-acid dissociation fit"),
    ]:
        cid, locator, before, after, note = args
        rows.append(line_edit(cid, "dic-carbonate", rel, locator, before, after,
                              "carbonate-fit-data", "hard", fit_rationale, note,
                              "data", target_checks=["global-dic"]))

    rel = "pkg/dic/dic_solvesaphe.F"
    for args in [
        ("sem-data-saphe-waters-k1-sqrt-s", "13.409160", "13.409160", "13.109160",
         "perturb the square-root salinity entry in the Waters K1 fit"),
        ("sem-data-saphe-waters-k1-temp-s", "-531.3642", "-531.3642", "-511.3642",
         "perturb the salinity-temperature cross term in the Waters K1 fit"),
        ("sem-data-saphe-waters-k2-sqrt-s", "21.225890", "21.225890", "21.525890",
         "perturb the square-root salinity entry in the Waters K2 fit"),
        ("sem-data-saphe-waters-k2-temp-s", "-779.3444", "-779.3444", "-749.3444",
         "perturb the salinity-temperature cross term in the Waters K2 fit"),
        ("sem-data-saphe-borate-logt", "137.1942", "137.1942", "135.1942",
         "perturb a coupled salinity entry in the SolveSAPHE borate fit"),
        ("sem-data-saphe-phosphate-k2", "172.1033", "172.1033", "174.1033",
         "perturb the leading entry in the SolveSAPHE phosphate K2 fit"),
    ]:
        cid, locator, before, after, note = args
        rows.append(line_edit(cid, "dic-solvesaphe", rel, locator, before, after,
                              "solvesaphe-fit-data", "hard", fit_rationale, note,
                              "data", target_checks=["so-box-obcs-saphe",
                                                       "so-box-calcite-naviaux"]))

    # Calcite dissolution regimes; these defaults intentionally differ from
    # the paper in places and therefore have high non-re-derivability.
    rel = "pkg/dic/dic_readparms.F"
    calcite = [
        ("sem-data-calcite-naviaux-rate-high", "calciteDissolRate(1) = 5.22", "5.22", "4.82"),
        ("sem-data-calcite-naviaux-rate-low", "calciteDissolRate(2) = 1.65", "1.65", "1.45"),
        ("sem-data-calcite-naviaux-exp-high", "calciteDissolExp(1) = 0.11", "0.11", "0.17"),
        ("sem-data-calcite-naviaux-exp-low", "calciteDissolExp(2) = 4.76", "4.76", "4.26"),
        ("sem-data-calcite-keir-rate", "calciteDissolRate(1) = 7.177", "7.177", "6.777"),
        ("sem-data-calcite-keir-exponent", "calciteDissolExp(1) = 4.54", "4.54", "4.24"),
    ]
    for cid, locator, before, after in calcite:
        target = (["so-box-calcite-naviaux"] if "naviaux" in cid
                  else ["so-box-calcite-keir"])
        rows.append(line_edit(
            cid, "dic-calcite", rel, locator, before, after,
            "calcite-rate-data", "hard",
            "The deck uses a locally calibrated rate-law tuple whose exact member "
            "cannot be reconstructed from the named publication alone.",
            "alter one calibrated member of the selected calcite dissolution law",
            "data", target_checks=target))

    # CFC Schmidt-number and solubility tables.
    rel = "pkg/cfc/cfc_param.F"
    for cid, locator, before, after, note in [
        ("sem-data-cfc11-schmidt-leading", "sca_11_1", "3501.8", "3451.8",
         "perturb the leading CFC-11 Schmidt-number coefficient"),
        ("sem-data-cfc11-schmidt-cubic", "sca_11_4", "-0.075139", "-0.071139",
         "perturb the cubic CFC-11 Schmidt-number coefficient"),
        ("sem-data-cfc11-solubility-a1", "A1_11", "-229.9261", "-226.9261",
         "perturb the first CFC-11 solubility coefficient"),
        ("sem-data-cfc11-solubility-b3", "B3_11", "-0.0157274", "-0.0147274",
         "perturb the third salinity coefficient in CFC-11 solubility"),
        ("sem-data-cfc12-schmidt-linear", "sca_12_2", "-228.95", "-224.95",
         "perturb the linear CFC-12 Schmidt-number coefficient"),
        ("sem-data-cfc12-solubility-a2", "A2_12", "298.9702", "294.9702",
         "perturb the second CFC-12 solubility coefficient"),
    ]:
        rows.append(line_edit(cid, "cfc-gas-exchange", rel, locator, before, after,
                              "cfc-fit-data", "hard", fit_rationale, note, "data",
                              target_checks=["cfc-online", "cfc-offline"]))

    # BLING stoichiometry, nutrient limitations, and iron-ligand chemistry.
    rel = "pkg/bling/bling_readparms.F"
    for cid, locator, before, after, family, note in [
        ("sem-data-bling-redfield-cton", "CtoN                 =", "6.75", "6.45",
         "redfield-data", "alter the default organic carbon-to-nitrogen ratio"),
        ("sem-data-bling-redfield-ctop", "CtoP                 =", "106.", "102.",
         "redfield-data", "alter the default organic carbon-to-phosphorus ratio"),
        ("sem-data-bling-iron-half-sat", "k_Fe                 = 1.6", "1.6", "2.1",
         "bling-limitation-data", "alter the phytoplankton iron half-saturation constant"),
        ("sem-data-bling-diaz-iron-half-sat", "k_Fe_diaz            =", "7.", "6.",
         "bling-limitation-data", "alter the diazotroph iron half-saturation constant"),
        ("sem-data-bling-nitrate-half-sat", "k_NO3                =", "2.", "3.",
         "bling-limitation-data", "alter the nitrate half-saturation constant"),
        ("sem-data-bling-phosphate-half-sat", "k_PO4                = 1.", "1.", "1.5",
         "bling-limitation-data", "alter the phosphate half-saturation constant"),
        ("sem-data-bling-ligand-stability-max", "kFe_eq_lig_max       =", "8.0", "6.0",
         "bling-iron-ligand-data", "alter the light-dependent upper ligand stability constant"),
    ]:
        rows.append(line_edit(cid, "bling-biogeochemistry", rel, locator, before,
                              after, family, "hard", scalar_rationale, note, "data",
                              target_checks=["global-bling"]))

    # Stateful protocols: bracketing, tendency ownership, mixing/advection,
    # offline time windows, open boundaries, and the saturation column pass.
    rel = "pkg/dic/dic_solvesaphe.F"
    rows.append(line_edit(
        "sem-protocol-saphe-initial-clamp", "dic-solvesaphe", rel,
        "zh = MAX(MIN(zh_max, zh_ini), zh_min)",
        "MAX(MIN(zh_max, zh_ini), zh_min)",
        "MIN(MAX(zh_max, zh_ini), zh_min)", "solvesaphe-bracket-protocol",
        "hard", protocol_rationale,
        "invert the nested bound operations when clamping the initial hydrogen estimate",
        "protocol", occurrence=0,
        target_checks=["so-box-obcs-saphe", "so-box-calcite-naviaux"]))
    bracket_old = ("        IF(zeqn .GT. 0. _d 0) THEN\n"
                   "           zh_min = zh_prev\n"
                   "        ELSEIF(zeqn .LT. 0. _d 0) THEN\n"
                   "           zh_max = zh_prev\n")
    bracket_new = ("        IF(zeqn .GT. 0. _d 0) THEN\n"
                   "           zh_max = zh_prev\n"
                   "        ELSEIF(zeqn .LT. 0. _d 0) THEN\n"
                   "           zh_min = zh_prev\n")
    rows.append(candidate(
        "sem-protocol-saphe-bracket-sign", "dic-solvesaphe", rel,
        bracket_old, bracket_new, "solvesaphe-bracket-protocol", "hard",
        protocol_rationale,
        "update the opposite hydrogen bracket after evaluating the residual sign",
        "protocol", ["so-box-obcs-saphe"]))

    rows.append(line_edit(
        "sem-protocol-gchem-tracer-window", "gchem-dispatch",
        "pkg/gchem/gchem_add_tendency.F", "iTr.LE.gchem_Tracer_num",
        "iTr.LE.gchem_Tracer_num", "iTr.LT.gchem_Tracer_num",
        "gchem-tendency-protocol", "hard", protocol_rationale,
        "exclude the final coupled tracer when adding the stored chemistry tendency",
        "protocol", target_checks=["cfc-online", "cfc-offline"]))
    rows.append(line_edit(
        "sem-protocol-ptracer-forcing-phase", "ptracer-transport",
        "pkg/ptracers/ptracers_integrate.F", "tracForcingOutAB.NE.1",
        "tracForcingOutAB.NE.1", "tracForcingOutAB.EQ.1",
        "ptracer-coupling-protocol", "hard", protocol_rationale,
        "apply the internal forcing in the wrong Adams-Bashforth phase",
        "protocol"))
    rows.append(line_edit(
        "sem-protocol-ptracer-implicit-gate", "ptracer-transport",
        "pkg/ptracers/ptracers_integrate.F",
        "PTRACERS_ImplVertAdv(iTracer) .OR. implicitDiffusion",
        ".OR. implicitDiffusion", ".AND. implicitDiffusion",
        "ptracer-mixing-protocol", "hard", protocol_rationale,
        "require both implicit vertical modes before running their coupled solve",
        "protocol", target_checks=["ptracer-advection-gyre"]))
    rows.append(line_edit(
        "sem-protocol-som-vertical-order", "ptracer-transport",
        "pkg/generic_advdiff/gad_som_advect.F", "DO k=Nr,1,-1",
        "DO k=Nr,1,-1", "DO k=1,Nr",
        "som-moment-protocol", "hard", protocol_rationale,
        "reverse the stateful vertical sweep over second-order tracer moments",
        "protocol", target_checks=["ptracer-advection-gyre"]))

    rel = "pkg/offline/offline_fields_load.F"
    old = ("             uVel(i,j,k,bi,bj) = bWght*uvel0(i,j,k,bi,bj)\n"
           "     &                         + aWght*uvel1(i,j,k,bi,bj)")
    new = ("             uVel(i,j,k,bi,bj) = aWght*uvel0(i,j,k,bi,bj)\n"
           "     &                         + bWght*uvel1(i,j,k,bi,bj)")
    rows.append(candidate(
        "sem-protocol-offline-u-time-window", "ptracer-transport", rel,
        old, new, "offline-window-protocol", "hard", protocol_rationale,
        "reverse the bracketing-record weights for offline zonal velocity",
        "protocol", ["cfc-offline"]))

    rows.append(swap_sections(
        "sem-protocol-obcs-corner-precedence", "ptracer-transport",
        "pkg/obcs/obcs_apply_ptracer.F",
        "#ifdef ALLOW_OBCS_NORTH\n", "#endif /* ALLOW_OBCS_NORTH */\n",
        "#ifdef ALLOW_OBCS_EAST\n", "#endif /* ALLOW_OBCS_EAST */\n",
        "obcs-application-protocol", protocol_rationale,
        "apply east-boundary values before north-boundary values at shared corners",
        ["so-box-obcs-saphe"]))

    rel = "pkg/dic/calcite_saturation.F"
    first = ("        CALL DIC_COEFFS_SURF(\n"
             "     I                       locTemp, locSalt,\n"
             "     I                       bi,bj,iMin,iMax,jMin,jMax,myThid)\n")
    second = ("        CALL DIC_COEFFS_DEEP(\n"
              "     I                       locTemp, locSalt,\n"
              "     I                       bi,bj,iMin,iMax,jMin,jMax,\n"
              "     I                       k,myThid)\n")
    text = open(os.path.join(config.BASE, rel), encoding="utf-8").read()
    start, stop = text.index(first), text.index(second) + len(second)
    old = text[start:stop]
    between = text[start + len(first):text.index(second)]
    new = second + between + first
    rows.append(candidate(
        "sem-protocol-calcite-pressure-pass", "dic-calcite", rel,
        old, new, "calcite-column-protocol", "hard", protocol_rationale,
        "apply deep pressure corrections before initializing surface coefficients",
        "protocol", ["so-box-calcite-keir", "so-box-calcite-naviaux"]))

    # Easy controls: their intended values remain explicit in nearby comments
    # or represent a conventional solver tolerance rather than hidden data.
    rows.append(line_edit(
        "sem-control-dic-phosphate-ph-scale", "dic-carbonate",
        "pkg/dic/carbon_chem.F", "115.525 _d 0 -", "115.525", "115.540",
        "locally-rederivable-control", "easy",
        "Easy control: the adjacent comment names both pH-scale constants and the selected scale.",
        "use the seawater-scale alternative in the total-scale phosphate fit",
        "control", occurrence=0, target_checks=["global-dic", "so-box-dic"]))
    rows.append(line_edit(
        "sem-control-calcite-naviaux-breakpoint", "dic-calcite",
        "pkg/dic/car_flux_omega_top.F", ".GT. 0.8272", "0.8272", "0.8000",
        "locally-rederivable-control", "easy",
        "Easy control: the neighboring comment records the incumbent breakpoint and its paper alternative.",
        "replace the locally tuned Naviaux regime breakpoint with the paper value",
        "control", target_checks=["so-box-calcite-naviaux"]))
    rows.append(line_edit(
        "sem-control-saphe-convergence", "dic-solvesaphe",
        "pkg/dic/dic_solvesaphe.F",
        "pp_rdel_ah_target = 1. _d -8", "1. _d -8", "1. _d -7",
        "locally-rederivable-control", "easy",
        "Easy control: this isolated numerical tolerance is visible at the convergence predicate.",
        "loosen the general SolveSAPHE relative convergence target by one decade",
        "control", occurrence=1,
        target_checks=["so-box-obcs-saphe", "so-box-calcite-naviaux"]))

    if not 25 <= len(rows) <= 40:
        raise RuntimeError(f"semantic round must contain 25--40 tasks, got {len(rows)}")
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate semantic ids")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(config.WORK,
                                                       "cand-semantic.jsonl"))
    args = parser.parse_args()
    rows = generate()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    stats = {
        "emitted": len(rows),
        "families": dict(Counter(row["family"] for row in rows)),
        "predicted_tiers": dict(Counter(
            row["meta"]["predicted_tier"] for row in rows)),
        "veins": dict(Counter(row["meta"]["vein"] for row in rows)),
    }
    with open(args.out + ".stats.json", "w", encoding="utf-8") as handle:
        json.dump(stats, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print(json.dumps(stats, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
