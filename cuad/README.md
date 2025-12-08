# CUAD Sample Contracts

Sample contracts from the [CUAD dataset](https://www.atticusprojectai.org/cuad) for testing the extraction pipeline.

## Structure

```
cuad/
├── train/                  # 10 contracts for development
│   ├── contracts/          # PDF files
│   ├── metadata.json       # Ground truth labels
│   └── metadata.csv
├── test/                   # 10 contracts for evaluation
│   ├── contracts/
│   ├── metadata.json
│   └── metadata.csv
├── train_2/                # 10 additional contracts (expanded types)
│   └── contracts/
├── fake_data/              # Synthetic test contract
│   └── fake_contract.txt
├── contract_types.json     # Full enum of 26 CUAD contract types
├── contracts_to_extract.json
└── extract_metadata.py     # Script to regenerate from CUAD source
```

## Contract Types

**train/** and **test/** contain 3 types relevant to fintech/asset management:
- Service Agreement (4 each)
- License Agreement (4 each)
- Outsourcing Agreement (2 each)

**train_2/** expands to additional types:
- License, Distributor, Development, Maintenance, Outsourcing

## Metadata Fields

| Field | Description |
|-------|-------------|
| `Parties` | Contracting parties |
| `Agreement Date` | Date contract was signed |
| `Effective Date` | When contract takes effect |
| `Expiration Date` | When contract expires |
| `Renewal Term` | Auto-renewal terms |
| `Notice Period To Terminate Renewal` | Notice required |
| `Governing Law` | Jurisdiction |

## Regenerating from Source

If you need to regenerate the contracts from the original CUAD dataset:

1. Download `CUAD_v1.zip` from https://www.atticusprojectai.org/cuad
2. Place in this folder (it's gitignored)
3. Run:

```bash
python cuad/extract_metadata.py
```

## Source

CUAD v1 (510 contracts, 41 annotation categories)
- Paper: https://arxiv.org/abs/2103.06268
- License: CC BY 4.0
