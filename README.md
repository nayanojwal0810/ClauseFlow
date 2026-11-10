# ClauseFlow

ClauseFlow is an AI-assisted contract policy exception and approval engine.

## Data Preparation

To prepare the contract dataset and official splits:

```bash
python scripts/prepare_contracts.py --archive data/raw/CUAD_v1.zip --split-archive data/raw/cuad_official_splits.zip --seed 42
```

## Dataset Attribution

This project uses the Contract Understanding Atticus Dataset (CUAD v1):
- Attribution: The Atticus Project (CC BY 4.0)
- Dataset: [CUAD v1 on Zenodo](https://zenodo.org/records/4595826)
- Code & Splits Repository: [The-Atticus-Project/cuad](https://github.com/The-Atticus-Project/cuad)
