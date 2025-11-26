# CUAD Sample Contracts

10 sample contracts from the [CUAD dataset](https://www.atticusprojectai.org/cuad) for testing the AI Legal & Compliance platform.

## Selection Criteria

1. **3 contract types** most relevant to fintech/asset management:
   - Service Agreement (vendor services)
   - License Agreement (software, data, trademarks)
   - Outsourcing Agreement (operational functions)

2. **Metadata richness**: Contracts with annotated fields in CUAD ground truth

3. **Diversity**: Multiple contracts per type to test extraction consistency

## Contents

```
cuad/
├── README.md
├── contract_types.json   # Full enum of 25 CUAD contract types
├── metadata.json         # Ground truth labels (structured)
├── metadata.csv          # Ground truth labels (spreadsheet)
└── contracts/
    ├── 01_service_gpaq.pdf
    ├── 02_service_reynolds.pdf
    ├── 03_service_verizon.pdf
    ├── 04_service_integrity.pdf
    ├── 05_license_gopage.pdf
    ├── 06_license_morganstanley.pdf
    ├── 07_license_cytodyn.pdf
    ├── 08_license_artara.pdf
    ├── 09_outsourcing_photronics.pdf
    └── 10_outsourcing_paratek.pdf
```

## Contracts by Type

| # | File | Type | Original |
|---|------|------|----------|
| 1 | `01_service_gpaq.pdf` | Service Agreement | GPAQ Acquisition Holdings |
| 2 | `02_service_reynolds.pdf` | Service Agreement | Reynolds Consumer Products |
| 3 | `03_service_verizon.pdf` | Service Agreement | Verizon ABS LLC |
| 4 | `04_service_integrity.pdf` | Service Agreement | Integrity Funds |
| 5 | `05_license_gopage.pdf` | License Agreement | Gopage Corp |
| 6 | `06_license_morganstanley.pdf` | License Agreement | Morgan Stanley Direct Lending |
| 7 | `07_license_cytodyn.pdf` | License Agreement | CytoDyn Inc |
| 8 | `08_license_artara.pdf` | License Agreement | Artara Therapeutics |
| 9 | `09_outsourcing_photronics.pdf` | Outsourcing Agreement | Photronics Inc |
| 10 | `10_outsourcing_paratek.pdf` | Outsourcing Agreement | Paratek Pharmaceuticals |

## Metadata Fields

| Field | Description |
|-------|-------------|
| `file` | Renamed PDF filename |
| `original_filename` | Original CUAD filename |
| `contract_type` | One of 3 types (see above) |
| `Document Name` | Title from contract text |
| `Parties` | Contracting parties |
| `Agreement Date` | Date contract was signed |
| `Effective Date` | When contract takes effect |
| `Expiration Date` | When contract expires |
| `Renewal Term` | Auto-renewal terms |
| `Notice Period To Terminate Renewal` | Notice required |
| `Governing Law` | Jurisdiction |

## Source

CUAD v1 (510 contracts, 41 annotation categories)
- Paper: https://arxiv.org/abs/2103.06268
- License: CC BY 4.0
